                                                                                
import base64
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import app
import operator_access
from demo_archive import validate

ROOT = Path(__file__).resolve().parents[1]


class OperatorHttpTests(unittest.TestCase):
    def setUp(self):
        self.password = __import__('secrets').token_urlsafe(32)
        self.environment = patch.dict(os.environ,{'EVENT_HORIZON_OPERATOR_PASSWORD':self.password,
            'EVENT_HORIZON_PUBLIC_ORIGIN':'','EVENT_HORIZON_BIND':'127.0.0.1'})
        self.environment.start()
        self.previous_lab=app.replay_lab
        app.replay_lab=app.ReplayLab(clock=lambda:0)
        self.previous_viewers=app.viewer_sessions
        app.viewer_sessions=app.ViewerSessions(app.create_viewer_match)
        self.previous = app.session
        app.session = app.MatchSession(wall_clock=lambda:0)
        self.server = ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.worker = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.worker.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join(2)
        app.viewer_sessions.close()
        app.viewer_sessions=self.previous_viewers
        app.session = self.previous
        app.replay_lab=self.previous_lab
        self.environment.stop()

    def request(self,path,body=None,password=None,origin=None,viewer=None):
        headers = {}
        if viewer is not None:headers['X-EH-Viewer-Session']=viewer
        if password is not None:
            headers['Authorization']='Basic '+base64.b64encode(('editor:'+password).encode()).decode()
        if body is not None:headers['Content-Type']='application/json'
        if origin is not None:headers['Origin']=origin
        request=Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:
            with urlopen(request,timeout=5) as response:return response.status,response.headers,response.read()
        except HTTPError as error:
            with error:return error.code,error.headers,error.read()

    def test_public_viewing_and_health_need_no_editor_password(self):
        for path in ('/','/live','/demo?start=1','/state?compact=1','/health/live','/health/ready'):
            status,_,body=self.request(path)
            self.assertEqual(status,200,path)
            self.assertNotIn(self.password.encode(),body)
        self.assertIn(b'data-operator-required="true"',self.request('/')[2])

    def test_personal_entry_keeps_live_dashboard_and_operator_protection(self):
        before=(app.session.run_key,app.session.run_id,app.session.match.clock)
        for path in ('/','/live','/demo?start=1'):
            status,_,body=self.request(path)
            self.assertEqual(status,200)
        self.assertNotIn(b"location.replace('/demo?start=1')",self.request('/')[2])
        self.assertIn(b'/enhanced-ui.js',self.request('/live')[2])
        self.assertIn(b'kickoff-overlay',self.request('/demo?start=1')[2])
        self.assertEqual((app.session.run_key,app.session.run_id,app.session.match.clock),before)
        self.assertEqual(self.request('/editor')[0],401)

    def test_personal_live_matches_start_paused_and_remain_independent(self):
        app.viewer_sessions.limit=2
        app.viewer_sessions.factory=lambda:app.MatchSession(wall_clock=lambda:0)
        original=app.session.run_key
        a=json.loads(self.request('/viewer-session',{})[2])['token']
        b=json.loads(self.request('/viewer-session',{})[2])['token']
        first=json.loads(self.request('/state?compact=1',viewer=a)[2])
        second=json.loads(self.request('/state?compact=1',viewer=b)[2])
        self.assertEqual(first['clock'],0)
        self.assertEqual(second['clock'],0)
        self.assertNotEqual(first['run_key'],second['run_key'])
        self.assertEqual(self.request('/viewer-session/start',{},viewer=a)[0],200)
        app.viewer_sessions.get(a).pump(3)
        self.assertEqual(json.loads(self.request('/state?compact=1',viewer=a)[2])['clock'],3)
        self.assertEqual(json.loads(self.request('/state?compact=1',viewer=b)[2])['clock'],0)
        self.assertEqual(app.session.run_key,original)
        self.assertEqual(self.request('/restart',{},viewer=a)[0],401)
        self.assertEqual(self.request('/editor',viewer=a)[0],401)

    def test_personal_session_capacity_release_and_expiry_fail_closed(self):
        app.viewer_sessions.limit=1
        token=json.loads(self.request('/viewer-session',{})[2])['token']
        self.assertEqual(self.request('/viewer-session',{})[0],429)
        self.assertEqual(self.request('/viewer-session/release',{},viewer=token)[0],200)
        self.assertEqual(self.request('/state?compact=1',viewer=token)[0],410)
        self.assertEqual(self.request('/viewer-session',{})[0],200)
        self.assertEqual(self.request('/viewer-session',{},origin='https://other.invalid')[0],403)
        self.assertEqual(self.request('/state?compact=1',viewer='bad-token')[0],410)

    def test_personal_evidence_links_resolve_the_same_run(self):
        token=json.loads(self.request('/viewer-session',{})[2])['token']
        key=app.viewer_sessions.get(token).run_key
        for route in ('/agent-trace','/generator','/operations'):
            status,_,body=self.request(route+'?viewer_session='+token)
            self.assertEqual(status,200)
            result=json.loads(body)
            if 'run_key' in result:self.assertEqual(result['run_key'],key)
        self.assertEqual(self.request('/agent-trace?viewer_session=bad')[0],410)

    def test_private_functions_callback_updates_only_its_own_match(self):
        from ingress import FunctionTransport, JsonEndpoint
        token=__import__('secrets').token_urlsafe(32)
        with patch.dict(os.environ,{'EVENT_HORIZON_INGEST_TOKEN':token}):
            app.session.transport=object()
            app.viewer_sessions.factory=lambda:app.MatchSession(wall_clock=lambda:0,transport=FunctionTransport(
                JsonEndpoint(self.base+'/ingest',{'Authorization':'Bearer '+token},allow_local=True)))
            viewer=json.loads(self.request('/viewer-session',{})[2])['token']
            private=app.viewer_sessions.get(viewer)
            private.pump(.05)
            self.assertEqual(private.pipeline.tick,1)
            self.assertEqual(app.session.pipeline.tick,0)
            self.assertIsNone(private.pending_ingress)

    def test_idle_viewer_is_released_and_assets_are_public(self):
        app.viewer_sessions.clock=lambda:0
        app.viewer_sessions.idle_seconds=1
        viewer=json.loads(self.request('/viewer-session',{})[2])['token']
        app.viewer_sessions.clock=lambda:2
        self.assertEqual(self.request('/state?compact=1',viewer=viewer)[0],410)
        for path in ('/viewer-session.js','/kickoff.css'):
            self.assertEqual(self.request(path)[0],200)

    def test_compact_bootstrap_preserves_event_sequence_without_full_event_payloads(self):
        from simulation import GeneratorSettings
        app.session = app.MatchSession(GeneratorSettings(2), wall_clock=lambda:0)
        app.session.pump(10)
        compact = json.loads(self.request('/state?compact=1')[2])
        full = json.loads(self.request('/state')[2])
        self.assertGreater(len(compact['events']), 0)
        self.assertEqual(compact['event_count'], full['event_count'])
        self.assertEqual(compact['events'], [{'id':e['id'],'time':e['time']} for e in full['events']])
        self.assertTrue(all(set(e)=={'id','time'} for e in compact['events']))
        self.assertTrue(any('kind' in e for e in full['events']))

    def test_journey_is_public_read_only_and_does_not_leak_draft_caption(self):
        from simulation import GeneratorSettings
        app.session = app.MatchSession(GeneratorSettings(2), wall_clock=lambda:0)
        for path in ('/journey', '/journey.js', '/journey/state'):
            status, _, body = self.request(path)
            self.assertEqual(status, 200, path)
            self.assertNotIn(self.password.encode(), body)
        self.assertEqual(json.loads(self.request('/journey/state')[2])['selected'], None)
        self.assertEqual(self.request('/journey/state?language=xx')[0], 400)
        self.assertEqual(self.request('/journey/state?team=0&team=1')[0], 400)
        self.assertEqual(self.request('/journey/state?episode=missing')[0], 404)
        self.assertEqual(self.request('/journey/state?run_key=old')[0], 409)
        app.session.pump(50)
        moment = next(iter(app.session.insights.moments.values()))
        app.session.desk.act(app.session.insights,moment.id,moment.revision,'review','Private draft review.')
        public = self.request('/journey/state')[2]
        self.assertNotIn(b'Private draft review.', public)
        self.assertEqual(app.session.match.clock, 50)

    def test_rehearsal_is_public_read_only_and_rejects_invalid_queries(self):
        before=app.session.run_key
        for path in ('/studio','/studio.js','/studio-core.js','/studio/scene?at=950&episode=moment-4773'):
            status,_,body=self.request(path)
            self.assertEqual(status,200,path)
            self.assertNotIn(self.password.encode(),body)
        for query in ('at=nan','at=inf','at=-1','at=5401','at=1&at=2','unexpected=1','episode='):
            self.assertEqual(self.request('/studio/scene?'+query)[0],400,query)
        self.assertEqual(self.request('/studio/scene?episode=unknown')[0],404)
        self.assertEqual(self.request('/studio/scene?run_key=other')[0],409)
        self.assertEqual(app.session.run_key,before)
        self.assertIsNone(app.session.desk.active_id)
        self.assertEqual(app.session.match.clock,0)

    def test_replay_lab_controls_are_protected_bounded_and_leave_live_match_unchanged(self):
        before=app.session.run_key
        for path in ('/replay-lab','/replay-lab.js','/replay-lab/state'):
            self.assertEqual(self.request(path)[0],200)
        self.assertIn(b'data-readonly="true"',self.request('/replay-lab')[2])
        self.assertEqual(self.request('/replay-lab/control')[0],401)
        self.assertEqual(self.request('/replay-lab/control',password=self.password)[0],200)
        body={'seed':42,'seconds':30,'speed':8}
        self.assertEqual(self.request('/replay-lab/start',body)[0],401)
        self.assertEqual(self.request('/replay-lab/start',body,self.password,'https://other.example')[0],403)
        self.assertEqual(self.request('/replay-lab/start',{**body,'seconds':5400},self.password,self.base)[0],400)
        status,_,raw=self.request('/replay-lab/start',body,self.password,self.base)
        self.assertEqual(status,200);key=json.loads(raw)['run_key']
        self.assertEqual(self.request('/replay-lab/start',body,self.password,self.base)[0],409)
        self.assertEqual(self.request('/replay-lab/receipt?run_key='+key)[0],409)
        self.assertEqual(self.request('/replay-lab/state?extra=1')[0],400)
        app.replay_lab.run.pump(31)
        while not app.replay_lab.run.complete:app.replay_lab.run.pump(31)
        status,_,raw=self.request('/replay-lab/receipt?run_key='+key)
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['status'],'passed')
        self.assertEqual(self.request('/replay-lab/receipt?run_key='+'a'*32)[0],409)
        self.assertEqual(self.request('/replay-lab/stop',{'run_key':key})[0],401)
        self.assertEqual(self.request('/replay-lab/stop',{'run_key':key},self.password,self.base)[0],200)
        self.assertEqual(app.session.run_key,before);self.assertEqual(app.session.match.tick,0)

    def test_editor_page_and_state_challenge_then_allow_authorized_user(self):
        for path in ('/editor','/state?view=editor&compact=1'):
            status,headers,_=self.request(path)
            self.assertEqual(status,401)
            self.assertIn('Basic',headers['WWW-Authenticate'])
            self.assertEqual(self.request(path,password=self.password)[0],200)
            self.assertEqual(self.request(path,password='incorrect')[0],401)

    def test_anonymous_or_wrong_password_cannot_restart_shared_match(self):
        before=app.session.run_id
        for password in (None,'incorrect'):
            self.assertEqual(self.request('/restart',{},password)[0],401)
        self.assertEqual(app.session.run_id,before)
        self.assertEqual(self.request('/restart',{},self.password,self.base)[0],200)
        self.assertEqual(app.session.run_id,before+1)

    def test_editorial_changes_require_login_and_still_validate_input(self):
        self.assertEqual(self.request('/editorial',{})[0],401)
        self.assertEqual(self.request('/editorial',{},self.password,self.base)[0],400)

    def test_editor_password_does_not_bypass_origin_or_ingress_authentication(self):
        before=app.session.run_id
        self.assertEqual(self.request('/restart',{},self.password,'https://other.example')[0],403)
        self.assertEqual(app.session.run_id,before)
        status,_,body=self.request('/ingest',{},self.password)
        self.assertEqual(status,401)
        self.assertIn(b'Unauthorized ingress',body)

    def test_local_workflow_remains_available_without_cloud_configuration(self):
        with patch.dict(os.environ,{'EVENT_HORIZON_OPERATOR_PASSWORD':''}):
            self.assertEqual(self.request('/state?view=editor')[0],200)
            self.assertEqual(self.request('/restart',{},origin=self.base)[0],200)


class DeploymentPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts=ROOT/'azure/scripts'
        sys.path.insert(0,str(scripts))
        try:
            spec=importlib.util.spec_from_file_location('eh_deploy_test',scripts/'deploy.py')
            cls.deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.deploy)
        finally:sys.path.remove(str(scripts))

    def test_public_bind_rejects_missing_or_short_editor_password(self):
        for password in ('','short'):
            with patch.dict(os.environ,{'EVENT_HORIZON_BIND':'0.0.0.0','EVENT_HORIZON_OPERATOR_PASSWORD':password}):
                with self.assertRaises(ValueError):operator_access.validate_configuration()

    def test_malformed_credentials_fail_closed(self):
        with patch.dict(os.environ,{'EVENT_HORIZON_OPERATOR_PASSWORD':'x'*40}):
            for header in ('','Bearer secret','Basic !!!','Basic eA==','Basic '+('x'*2000)):
                self.assertFalse(operator_access.authorized(header))

    def test_missing_or_unreadable_archive_blocks_deployment(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'full-match.sqlite3'
            with self.assertRaisesRegex(ValueError,'missing'):validate(path)
            path.write_text('not a SQLite match')
            with self.assertRaisesRegex(ValueError,'unreadable'):validate(path)

    def test_assignment_deployment_cannot_silently_omit_foundry(self):
        arguments=['deploy.py','--subscription','test','--resource-group','test','--location','test','--prefix','test','--apply']
        with patch.object(sys,'argv',arguments),patch.object(self.deploy,'az') as azure:
            with self.assertRaises(SystemExit) as failure:self.deploy.main()
            self.assertEqual(failure.exception.code,2)
            azure.assert_not_called()

    def test_editor_credentials_are_private_and_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'operator.json'
            self.deploy.write_private_json(path,{'password':'test-secret'})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(json.loads(path.read_text())['password'],'test-secret')
            link=Path(folder)/'link.json';link.symlink_to(path)
            with self.assertRaises(OSError):self.deploy.write_private_json(link,{'password':'changed'})
            self.assertEqual(json.loads(path.read_text())['password'],'test-secret')

    def test_private_output_replaces_a_hardlink_without_changing_its_target(self):
        with tempfile.TemporaryDirectory() as folder:
            original=Path(folder)/'original.json'
            original.write_text('original')
            output=Path(folder)/'output.json'
            os.link(original,output)
            self.deploy.write_private_json(output,{'password':'test-only'})
            self.assertEqual(original.read_text(),'original')
            self.assertEqual(stat.S_IMODE(output.stat().st_mode),0o600)

    def test_credentials_cannot_be_written_into_a_future_build_context(self):
        arguments=['deploy.py','--subscription','test','--resource-group','test','--location','test',
                   '--prefix','test','--operator-credentials',str(ROOT/'credentials.json')]
        with patch.object(sys,'argv',arguments),patch.object(self.deploy,'az') as azure:
            with self.assertRaises(SystemExit) as failure:self.deploy.main()
            self.assertEqual(failure.exception.code,2)
            azure.assert_not_called()

    def test_foundry_endpoint_rejects_markdown_link_before_azure_writes(self):
        endpoint='https://event-horizon-resource.services.ai.azure.com/api/projects/event-horizon'
        self.deploy.validate_foundry_endpoint(endpoint)
        for malformed in (f'[{endpoint}]({endpoint})','http://example.com/api/projects/event-horizon',
                          endpoint+'?key=secret'):
            with self.assertRaisesRegex(ValueError,'plain HTTPS project URL'):
                self.deploy.validate_foundry_endpoint(malformed)

    def test_free_credit_acr_block_and_missing_local_docker_fail_early(self):
        with patch.object(self.deploy,'az',return_value={
                'subscriptionPolicies':{'quotaId':'FreeTrial_2014-09-01'}}):
            with self.assertRaisesRegex(RuntimeError,'ACR Tasks are paused'):
                self.deploy.check_build_method('acr','subscription-id')
        with patch.object(self.deploy.shutil,'which',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'requires Docker'):
                self.deploy.check_build_method('local','subscription-id')
