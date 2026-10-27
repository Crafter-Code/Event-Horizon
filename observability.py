                                                                              

                                                                                
                                                                                  
   
from collections import deque, Counter
from contextlib import contextmanager, nullcontext
import logging
import os
import threading
import time


class Observability:
    def __init__(self):
        self.lock = threading.Lock()
        self.recent = deque(maxlen=64)
        self.counts = Counter()
        self.tracer = self.histogram = self.counter = None
        self.export = 'local'

    def configure(self):
        if not os.getenv('APPLICATIONINSIGHTS_CONNECTION_STRING'):
            return
        from microsoft.opentelemetry import use_microsoft_opentelemetry
        from opentelemetry import trace, metrics
                                                                           
                                                                            
        use_microsoft_opentelemetry(enable_azure_monitor=True, enable_sensitive_data=False,
            logger_name='event_horizon', instrumentation_options={
                name:{'enabled':False} for name in ('azure_sdk','requests','urllib','urllib3',
                'httpx','httpx2','openai','openai_v2','openai_agents','django','fastapi','flask','psycopg2')})
        self.tracer = trace.get_tracer('event_horizon', '11')
        meter = metrics.get_meter('event_horizon', '11')
        self.histogram = meter.create_histogram('eh.stage.duration', unit='ms')
        self.counter = meter.create_counter('eh.stage.count', unit='{operation}')
        self.export = 'azure_monitor_configured'

    @contextmanager
    def span(self, stage, **attributes):
        started = time.perf_counter()
        outcome = 'ok'
        context = self.tracer.start_as_current_span(stage, attributes=attributes,
                    record_exception=False, set_status_on_exception=False) if self.tracer else nullcontext(None)
        with context as span:
            try:
                yield span
            except BaseException as error:
                outcome = 'error'
                if span:
                    from opentelemetry.trace import Status, StatusCode
                    span.set_status(Status(StatusCode.ERROR, type(error).__name__))
                    span.set_attribute('error.type', type(error).__name__)
                raise
            finally:
                self.record(stage, (time.perf_counter()-started)*1000, outcome)

    def record(self, stage, duration_ms, outcome='ok'):
        with self.lock:
            self.counts[f'{stage}:{outcome}'] += 1
            self.recent.append({'stage':stage,'outcome':outcome,'duration_ms':round(duration_ms,3)})
        if self.histogram:
            dimensions = {'stage':stage,'outcome':outcome}
            self.histogram.record(duration_ms, dimensions)
            self.counter.add(1, dimensions)

    def headers(self):
        if not self.tracer:return {}
        from opentelemetry.propagate import inject
        headers = {}
        inject(headers)
        return headers

    @contextmanager
    def incoming(self, headers):
        if not self.tracer:
            yield
            return
        from opentelemetry.context import attach, detach
        from opentelemetry.propagate import extract
        token = attach(extract(dict(headers)))
        try:yield
        finally:detach(token)

    def snapshot(self):
        with self.lock:
            return {'export':self.export,'counts':dict(self.counts),'recent':list(self.recent),
                    'cloud_delivery_verified':False}

    def close(self):
        if self.tracer:
            from opentelemetry import trace, metrics
            trace.get_tracer_provider().shutdown()
            metrics.get_meter_provider().shutdown()


observe = Observability()
