                                                                                  

                                                                            
                                                                            
                                                      
   
from collections import deque
import math
import time
from uuid import uuid4


class PresentationTiming:
    def __init__(self, clock=time.monotonic):
        self.clock=clock
        self.events={}
        self.pending={}
        self.samples=deque(maxlen=256)

    def produced(self, event_id, started, ready):
        self.events[event_id]=(started, max(0,(ready-started)*1000))

    def offer(self, record):
        if not record or not record.get('trigger_event_id'):
            return None
        source=self.events.get(record['trigger_event_id'])
        if not source or self.clock()-source[0]>10:
            return None
        for token, receipt in self.pending.items():
            if (receipt['material_id'],receipt['revision'],receipt['event_id']) == (record['material_id'],record['revision'],record['trigger_event_id']):
                return {'token':token,'material_id':record['material_id'],'revision':record['revision'],
                        'event_id':record['trigger_event_id'],'processing_ms':round(source[1],3)}
        token=uuid4().hex
        self.pending[token]={'material_id':record['material_id'],'revision':record['revision'],
                             'event_id':record['trigger_event_id'],'produced':source[0],
                             'processing_ms':source[1], 'offered':self.clock()}
        while len(self.pending)>512:self.pending.pop(next(iter(self.pending)))
        return {'token':token,'material_id':record['material_id'],'revision':record['revision'],
                'event_id':record['trigger_event_id'],'processing_ms':round(source[1],3)}

    def acknowledge(self, payload):
        token=payload.get('token')
        if not isinstance(token,str):raise ValueError('Invalid display token')
        if type(payload.get('revision')) is not int or type(payload.get('event_id')) is not int:
            raise ValueError('Invalid display source identity')
        receipt=self.pending.get(token)
        if receipt is None:raise ValueError('Unknown or expired display receipt')
        if self.clock()-receipt['offered']>30:raise ValueError('Display receipt expired')
        for key in ('material_id','revision','event_id'):
            if payload.get(key)!=receipt[key]:raise ValueError('Display receipt does not match delivered material')
        for key in ('render_ms','request_ms'):
            value=payload.get(key)
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=60000:
                raise ValueError('Invalid browser timing')
        if payload.get('visible') is not True:raise ValueError('Card was not reported visible')
        if receipt.get('acknowledged'):return False
        receipt['acknowledged']=True
        self.samples.append({'material_id':receipt['material_id'],'event_id':receipt['event_id'],
                             'event_to_display_ack_ms':round(max(0,(self.clock()-receipt['produced'])*1000),2),
                             'processing_ms':round(receipt['processing_ms'],3),
                             'browser_render_ms':round(payload['render_ms'],2),
                             'request_ms':round(payload['request_ms'],2)})
        return True

    def summary(self):
        values=sorted(item['event_to_display_ack_ms'] for item in self.samples)
        def percentile(q):return values[max(0,math.ceil(q*len(values))-1)] if values else None
        return {'sample_count':len(values),'latest':dict(self.samples[-1]) if values else None,
                'p50_ms':percentile(.5),'p95_ms':percentile(.95),
                'measurement':'event_to_display_ack_upper_bound',
                'browser_timing':'client_reported_after_two_animation_frames',
                'unmeasured':'Cards not visible while fresh have no live latency sample.'}
