                                                                                    
import asyncio
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app import MatchSession
from cloud_contract import encode, decode, digest, MAX_BODY
from ingress import FunctionTransport, IngressConflict, IngressUnavailable, JsonEndpoint
from journal import EventJournal
from observability import Observability


class Clock:
    def __init__(self):self.now=0
    def __call__(self):return self.now


class Relay:
    def __init__(self):self.session=None;self.calls=[];self.drop=False;self.down=False
    def submit(self,payload):
        self.calls.append(deepcopy(payload))
        if self.down:raise OSError('Network down')
        result=self.session.receive_ingress(decode(encode(payload)))
        if self.drop:self.drop=False;raise OSError('Lost reply after commit')
        return result


class IngressTests(unittest.TestCase):
    def make(self,journal=None):
        self.clock=Clock();self.relay=Relay()
        live=MatchSession(wall_clock=self.clock,journal=journal,transport=self.relay)
        self.relay.session=live
        return live

    def test_delayed_delivery_catches_up_in_batches_without_skipping_ticks(self):
        live=self.make();self.clock.now=5
        live.pump()
        self.assertEqual(len(self.relay.calls),1)
        self.assertEqual(live.pipeline.tick,100)
        local=MatchSession(wall_clock=lambda:0);local.pump(5)
        self.assertEqual(live.confirmed_frame,local.confirmed_frame)
        self.assertEqual(live.pipeline.events,local.pipeline.events)
        self.assertEqual(live.generator_checks.checked_frames,101)

    def test_batch_preserves_every_camera_frame_and_pixel_metrics(self):
        live=self.make()
        from camera import SyntheticCamera
        live.camera=SyntheticCamera();live.camera.advance(live.match)
        self.clock.now=2;live.pump()
        local=MatchSession(wall_clock=lambda:0,vision_enabled=True);local.pump(2)
        self.assertEqual(live.camera.recognizer.snapshot(),local.camera.recognizer.snapshot())
        self.assertEqual(live.camera.evaluation.snapshot(),local.camera.evaluation.snapshot())

    def test_batch_archive_failure_publishes_nothing_and_retries_exactly(self):
        with tempfile.TemporaryDirectory() as folder:
            journal=EventJournal(Path(folder)/'events.db')
            live=self.make(journal)
            calls=[]
            def archive(key,events):
                calls.append(deepcopy(events))
                if len(calls)==1:raise OSError('Archive unavailable')
                journal.append(key,events)
            journal.append_batch=archive
            self.clock.now=2;live.pump()
            self.assertEqual(live.pipeline.tick,0)
            self.assertEqual(live.confirmed_frame['clock'],0)
            self.clock.now=2.3;live.pump()
            self.assertEqual(live.pipeline.tick,40)
            self.assertEqual(calls[0],calls[1])
            self.assertEqual(journal.runs()[0]['event_count'],live.confirmed_count)
            journal.close()

    def test_batched_lost_ack_does_not_repeat_metrics(self):
        live=self.make();self.clock.now=2;self.relay.drop=True;live.pump()
        before=deepcopy(live.confirmed_frame)
        self.clock.now=2.3;live.pump()
        self.assertEqual(live.confirmed_frame,before)
        self.assertEqual(live.pipeline.tick,40)
        self.assertEqual(self.relay.calls[0],self.relay.calls[1])

    def test_network_outage_does_not_publish_future_frame(self):
        live=self.make();self.relay.down=True;self.clock.now=.05
        old=live.snapshot()
        live.pump()
        self.assertEqual(live.match.tick,1)
        self.assertEqual(live.pipeline.tick,0)
        self.assertEqual(live.snapshot()['clock'],old['clock'])
        self.assertEqual(live.confirmed_hash,old['event_hash'])
        live.pump();self.assertEqual(len(self.relay.calls),1)          
        self.relay.down=False;self.clock.now=.31;live.pump()
        self.assertEqual(live.pipeline.tick,1)
        self.assertIsNone(live.pending_ingress)
        self.assertEqual(self.relay.calls[0],self.relay.calls[1])

    def test_lost_ack_exact_redelivery_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as d:
            journal=EventJournal(Path(d)/'events.db')
            live=self.make(journal);self.relay.drop=True;self.clock.now=.05;live.pump()
            count=live.confirmed_count;fingerprint=live.confirmed_hash
            self.clock.now=.31;live.pump()
            self.assertEqual(live.pipeline.tick,1)
            self.assertEqual(live.confirmed_count,count)
            self.assertEqual(live.confirmed_hash,fingerprint)
            self.assertEqual(journal.runs()[0]['event_count'],count)
            self.assertIsNone(live.pending_ingress)
            journal.close()

    def test_transient_archive_failure_retries_before_metric_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            journal=EventJournal(Path(folder)/'events.db')
            live=self.make(journal)
            append=journal.append
            with patch.object(journal,'append',side_effect=OSError('Archive unavailable')):
                self.clock.now=.05;live.pump()
            self.assertIsNone(live.pipeline.last_error)
            self.assertEqual(live.pipeline.tick,0)
            self.assertTrue(live.ingress_error)
            self.clock.now=.31;live.pump()
            self.assertEqual(live.pipeline.tick,1)
            self.assertIsNone(live.pending_ingress)
            self.assertEqual(journal.runs()[0]['event_count'],live.confirmed_count)
            journal.close()

    def test_changed_payload_and_previous_match_rejected(self):
        live=self.make();self.relay.down=True;self.clock.now=.05;live.pump()
        source=deepcopy(self.relay.calls[0]);bad=deepcopy(source)
        bad['frame']['score']=[99,99]
        with self.assertRaises(IngressConflict):live.receive_ingress(bad)
        self.assertEqual(live.pipeline.tick,0)
        live.restart()
        with self.assertRaises(IngressConflict):live.receive_ingress(source)
        self.assertEqual(live.pipeline.tick,0)

    def test_same_confirmed_events_metrics_and_cards_as_local(self):
        live=self.make()
        local=MatchSession(wall_clock=lambda:0)
        for tick in range(1,1201):
            self.clock.now=tick*.05;live.pump()
        local.pump(60)
        self.assertEqual(live.confirmed_hash,local.confirmed_hash)
        self.assertEqual(live.confirmed_frame,local.confirmed_frame)
        self.assertEqual(live.pipeline.events,local.pipeline.events)
        self.assertEqual(set(live.insights.moments),set(local.insights.moments))
        self.assertEqual(len(live.materials.history),len(local.materials.history))
        self.assertEqual(live.pipeline.context.window(),local.pipeline.context.window())
                                                                        
        self.assertEqual(self.relay.calls[0]['events'][0]['id'],1)

    def test_false_ack_never_advances_pending_source(self):
        live=self.make();self.relay.submit=lambda _: {'accepted':True}
        self.clock.now=.05;live.pump()
        self.assertEqual(live.pipeline.tick,0)
        self.assertTrue(live.ingress_error)

    def test_restart_while_old_call_returns_preserves_new_run(self):
        live=self.make()
        def restart(payload):live.restart();return {'accepted':True}
        self.relay.submit=restart;self.clock.now=.05;live.pump()
        self.assertEqual(live.run_id,2);self.assertEqual(live.pipeline.tick,0)
        self.assertIsNone(live.pending_ingress)

    def test_wire_limits_duplicates_and_nonfinite(self):
        live=self.make();self.clock.now=.05;live.pump();source=encode(self.relay.calls[0])
        self.assertEqual(decode(source),self.relay.calls[0])
        for bad in (b'{"tick":1,"tick":2}', b'{"x":NaN}', b' '* (MAX_BODY+1), b'[]', source.replace(b'"tick":1',b'"tick":true')):
            with self.assertRaises(ValueError):decode(bad)

    def test_transport_requires_exact_ack_and_fixed_https(self):
        live=self.make();self.clock.now=.05;live.pump();source=self.relay.calls[0]
        for url in ('http://example.com/api/events','https://user:secret@example.com/path','https://example.com?code=secret','https://example.com/#secret'):
            with self.assertRaises(ValueError):JsonEndpoint(url)
        JsonEndpoint('http://127.0.0.1:1234/',allow_local=True).close()
        class Wrong:
            def post(self,*_):return {'accepted':True,'tick':1,'digest':'wrong'}
        with self.assertRaises(IngressUnavailable):FunctionTransport(Wrong()).submit(source)

    def test_operational_receipts_bounded_and_no_source_messages(self):
        recorder=Observability()
        for i in range(80):
            with recorder.span('analysis',run_key='private'):pass
        with self.assertRaises(ValueError):
            with recorder.span('verification'):raise ValueError('secret prompt')
        state=recorder.snapshot()
        self.assertEqual(len(state['recent']),64)
        self.assertEqual(state['counts']['verification:error'],1)
        self.assertNotIn('private',json.dumps(state));self.assertNotIn('secret',json.dumps(state))


try:
    import azure.functions
    HAS_AZURE=True
except ImportError:HAS_AZURE=False


@unittest.skipUnless(HAS_AZURE, 'Optional Azure SDK environment required')
class FunctionSdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import azure.functions as func
        cls.func=func
        path=Path(__file__).resolve().parents[1]/'azure/function/function_app.py'
        spec=importlib.util.spec_from_file_location('eh_function',path)
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)

    def request(self,body):return self.func.HttpRequest(method='POST',url='https://test/api/events',headers={'content-type':'application/json'},body=body)

    def test_actual_function_decorator_uses_function_auth(self):
        functions=self.module.app.get_functions()
        self.assertEqual(len(functions),1)
        binding=functions[0].get_bindings_dict()['bindings'][0]
        self.assertEqual(binding['authLevel'].value,'function')
        self.assertEqual(binding['route'],'events')

    def test_real_function_invocation_relay_and_backend_failure(self):
        clock=Clock();relay=Relay();live=MatchSession(wall_clock=clock,transport=relay);relay.session=live
        relay.down=True;clock.now=.05;live.pump();payload=relay.calls[0]
        class Backend:
            def post(self,data,*_):return live.receive_ingress(data)
        with patch.object(self.module,'backend',return_value=Backend()):
            result=self.module.events(self.request(encode(payload)))
            self.assertEqual(result.status_code,200)
            self.assertEqual(json.loads(result.get_body())['digest'],digest(payload))
            duplicate=self.module.events(self.request(encode(payload)))
            self.assertTrue(json.loads(duplicate.get_body())['duplicate'])
        with patch.object(self.module,'backend',side_effect=OSError('secret')):
            self.assertEqual(self.module.events(self.request(encode(payload))).status_code,503)
        self.assertEqual(self.module.events(self.request(b'{"bad":1}')).status_code,400)

    def test_blob_archive_uses_immutable_events(self):
        from azure_journal import BlobEventJournal
        from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
        class Download:
            def __init__(self,data):self.data=data
            def readall(self):return self.data
        class Container:
            def __init__(self):self.data={}
            def upload_blob(self,name,body,overwrite=False):
                if name in self.data:raise ResourceExistsError('exists')
                self.data[name]=body
            def download_blob(self,name):
                if name not in self.data:raise ResourceNotFoundError('missing')
                return Download(self.data[name])
            def close(self):pass
        journal=BlobEventJournal(Container());key=journal.start({'match':'test'})
        event={'id':1,'time':0,'kind':'kickoff'}
        journal.append(key,[event]);journal.append(key,[event])
        self.assertEqual(journal.find(key,1)['event'],event)
        self.assertIsNone(journal.find(key,2))
        with self.assertRaises(ValueError):journal.append(key,[{**event,'time':1}])

    def test_http_generator_function_application_roundtrip(self):
        import app as application
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        from urllib.request import urlopen, Request
        from urllib.error import HTTPError
        secret='test-ingest-token-'+'x'*32
        clock=Clock();previous=application.session
        app_server=ThreadingHTTPServer(('127.0.0.1',0),application.Handler)
        app_url=f'http://127.0.0.1:{app_server.server_port}'
        function_module=self.module
        func=self.func
        class FunctionHost(BaseHTTPRequestHandler):
            def do_POST(self):
                                                                              
                                                                             
                body=self.rfile.read(int(self.headers['Content-Length']))
                req=func.HttpRequest(method='POST',url='https://local/api/events',headers=dict(self.headers),body=body)
                result=function_module.events(req)
                self.send_response(result.status_code);self.end_headers();self.wfile.write(result.get_body())
            def log_message(self,*_):pass
        function_server=ThreadingHTTPServer(('127.0.0.1',0),FunctionHost)
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (app_server,function_server)]
        for t in threads:t.start()
        transport=FunctionTransport(JsonEndpoint(f'http://127.0.0.1:{function_server.server_port}/api/events',allow_local=True))
        backend=JsonEndpoint(app_url+'/ingest',{'Authorization':'Bearer '+secret},allow_local=True)
        try:
            with patch.dict(os.environ,{'EVENT_HORIZON_INGEST_TOKEN':secret,
                    'EVENT_HORIZON_BIND':'127.0.0.1','EVENT_HORIZON_PUBLIC_ORIGIN':'',
                    'EVENT_HORIZON_OPERATOR_PASSWORD':''}),patch.object(self.module,'backend',return_value=backend):
                live=MatchSession(wall_clock=clock,transport=transport);application.session=live
                for tick in range(1,101):clock.now=tick*.05;live.pump()
                local=MatchSession(wall_clock=lambda:0);local.pump(5)
                self.assertEqual(live.confirmed_frame,local.confirmed_frame)
                self.assertIsNone(live.pending_ingress)
                state=json.load(urlopen(app_url+'/operations'))
                self.assertEqual(state['confirmed_tick'],100)
                self.assertEqual(state['ingress'],'functions')
                self.assertEqual(json.load(urlopen(app_url+'/health/ready'))['status'],'ok')
                req=Request(app_url+'/ingest',data=b'{}',headers={'Content-Type':'application/json'})
                with self.assertRaises(HTTPError) as failure:urlopen(req)
                self.assertEqual(failure.exception.code,401)
                req=Request(app_url+'/ingest',data=b'{}',headers={'Content-Type':'application/json','Authorization':'Bearer '+secret})
                with self.assertRaises(HTTPError) as failure:urlopen(req)
                self.assertEqual(failure.exception.code,400)
                req=Request(app_url+'/restart',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://evil.example'})
                with self.assertRaises(HTTPError) as failure:urlopen(req)
                self.assertEqual(failure.exception.code,403)
        finally:
            application.session=previous
            backend.close();transport.close()
            for server in (app_server,function_server):server.shutdown();server.server_close()
            for thread in threads:thread.join(2)

    def test_opentelemetry_trace_correlation_and_error_redaction(self):
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        exporter=InMemorySpanExporter();provider=TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        recorder=Observability();recorder.tracer=provider.get_tracer('event_horizon')
        with recorder.span('eh.functions.receive') as parent:
            headers=recorder.headers()
            with recorder.incoming(headers):
                with recorder.span('eh.analysis.publish') as child:
                    self.assertEqual(parent.get_span_context().trace_id,child.get_span_context().trace_id)
        with self.assertRaises(ValueError):
            with recorder.span('eh.agent.fact_checking'):raise ValueError('secret prompt and key')
        spans=exporter.get_finished_spans()
        self.assertEqual(len(spans),3)
        self.assertFalse(spans[-1].events)
        self.assertNotIn('secret',str(spans[-1].attributes))
        self.assertEqual(spans[-1].attributes['error.type'],'ValueError')
        provider.shutdown()

    def test_three_real_framework_agents_with_mocked_foundry_http(self):
        import httpx
        from openai import AsyncOpenAI
        from agent_framework.foundry import FoundryChatClient
        from foundry_narrative import from_environment
        live=MatchSession(wall_clock=lambda:0);live.pump(300)
        moment=next(m for m in live.insights.moments.values() if m.complete)
        packet=live.insights.moment_data(moment)
        draft={key:packet[key] for key in ('what','why','change','evidence_ids')}
        responses=iter([{'evidence_ids':packet['evidence_ids'],'observations':[],'limitations':[]},draft,
                        {'approved':True,'unsupported_claims':[]}])
        requests=[]
        async def respond(request):
            requests.append(json.loads(request.content))
            text=json.dumps(next(responses),ensure_ascii=False)
            return httpx.Response(200,json={'id':f'resp_{len(requests)}','created_at':0,'object':'response',
                'model':'test','status':'completed','output':[{'id':f'msg_{len(requests)}','type':'message',
                'role':'assistant','status':'completed','content':[{'type':'output_text','text':text,'annotations':[]}]}],
                'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}})
        async def run():
            client=AsyncOpenAI(api_key='test-only',base_url='https://test.invalid',
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
            class Project:
                def get_openai_client(self,**_):return client
                async def close(self):pass
            foundry=FoundryChatClient(project_client=Project(),model='test')
            with patch.dict(os.environ,{'EVENT_HORIZON_NARRATIVE_PROVIDER':'foundry',
                'AZURE_AI_PROJECT_ENDPOINT':'https://test.services.ai.azure.com/api/projects/test',
                'AZURE_AI_MODEL_DEPLOYMENT_NAME':'test','EVENT_HORIZON_AZURE_CREDENTIAL':'cli'}),\
                patch('agent_framework.foundry.FoundryChatClient',return_value=foundry):
                narrator,status=from_environment()
            try:
                self.assertEqual([a.name for a in (narrator.analyst,narrator.writer,narrator.verifier)],
                                 ['MatchAnalyst','MatchStoryWriter','MatchFactVerifier'])
                self.assertEqual(await narrator.compose(packet),draft)
                self.assertEqual(len(requests),3)
                self.assertTrue(all(request['model']=='test' for request in requests))
                for request in requests:
                    fmt=request['text']['format']
                    self.assertEqual(fmt['type'],'json_schema')
                    self.assertTrue(fmt['strict'])
                    self.assertFalse(fmt['schema']['additionalProperties'])
                self.assertEqual(set(requests[2]['text']['format']['schema']['properties']),
                                 {'approved','unsupported_claims'})
            finally:await narrator.close()
        asyncio.run(run())


if __name__=='__main__':unittest.main()
