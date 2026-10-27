                                                                         
from collections import deque
from copy import deepcopy
import math

KINDS=('pass_started','pass_completed','shot','tackle','interception','possession_change','pressure','goal')


class RecognitionEvaluation:
    def __init__(self):
        self.frames=0;self.detected=0;self.matched=0;self.correct=0;self.position_error=0.
        self.ball_frames=0;self.ball_error=0.;self.speed_n=0;self.speed_error=0.;self.previous=None
        self.truth_cursor=0;self.pred_cursor=0;self.truth=deque();self.pred=[]
        self.scores={kind:dict(tp=0,fp=0,fn=0) for kind in KINDS};self.examples=deque(maxlen=16)
        self.watched_truth=set();self.verdicts={}

    def watch(self, matches):
                                                                                      
        self.watched_truth.update(item['event_id'] for item in matches.values())

    def compare(self, observation, truth_players, truth_ball, truth_events, predictions):
        self.frames+=1;self.detected+=len(observation['players'])
        available=list(truth_players)
        for p in observation['players']:
            if not available:break
            nearest=min(available,key=lambda gt:math.dist((p['x'],p['y']),(gt['x'],gt['y'])))
            error=math.dist((p['x'],p['y']),(nearest['x'],nearest['y']))
            if error<=2:
                available.remove(nearest);self.matched+=1;self.position_error+=error
                self.correct+=(p['team'],p['number'])==(nearest['team'],nearest['number'])
        ball=observation['ball'];time=observation['time']
        if ball:
            self.ball_frames+=1;self.ball_error+=math.dist((ball['x'],ball['y']),truth_ball)
            if self.previous and observation['in_play'] and self.previous[2] and ball['speed_mps'] is not None:
                previous_time,previous_ball,_=self.previous
                true_speed=math.dist(truth_ball,previous_ball)/(time-previous_time)
                if true_speed<=45:
                    self.speed_n+=1;self.speed_error+=abs(ball['speed_mps']-true_speed)
        self.previous=(time,tuple(truth_ball),observation['in_play'])
        for event in truth_events[self.truth_cursor:]:
            if event['kind'] in KINDS:self.truth.append(event)
        self.truth_cursor=len(truth_events)
        self.pred.extend(e for e in predictions[self.pred_cursor:] if e['kind'] in KINDS)
        self.pred_cursor=len(predictions)
        self._settle(time)

    def _settle(self,time,final=False):
        while self.truth and (final or self.truth[0]['time']<=time-1.2):
            gt=self.truth.popleft()
            def compatible(p):
                if p['kind']!=gt['kind'] or abs(p['time']-gt['time'])>.8:return False
                if gt['kind'] in ('pass_started','pass_completed','shot','tackle','interception'):
                    actor=gt['actors'][-1 if gt['kind'] in ('interception','tackle') else 0] if gt['actors'] else None
                    return bool(p['actors'] and actor and all(p['actors'][0][k]==actor[k] for k in ('team','number')))
                if gt['kind']=='pressure':
                    return p['facts']['pressing_team']==gt['team'] and p['facts']['count']==gt['details']['counts'][gt['team']]
                if gt['kind']=='possession_change':return p['facts'].get('to_team')==gt['team']
                if gt['kind']=='goal':return bool(p['actors']) and p['actors'][0]['team']==gt['team']
                return True
            choices=[p for p in self.pred if compatible(p)]
            score=self.scores[gt['kind']]
            if choices:
                match=min(choices,key=lambda p:abs(p['time']-gt['time']));self.pred.remove(match);score['tp']+=1
                verdict={'status':'matched','truth_id':gt['id'],'prediction_id':match['id'],
                                      'kind':gt['kind'],'time':gt['time'],
                                      'prediction_time':match['time'],
                                      'frame_ids':match.get('frame_ids',[])[:],
                                      'delta_s':round(match['time']-gt['time'],2)}
            else:
                score['fn']+=1;verdict={'status':'missed','truth_id':gt['id'],'kind':gt['kind'],'time':gt['time']}
            self.examples.append(verdict)
            if gt['id'] in self.watched_truth:self.verdicts[gt['id']]=verdict.copy()
        expired=[p for p in self.pred if final or p['time']<=time-2.1]
        for p in expired:
            self.pred.remove(p);self.scores[p['kind']]['fp']+=1
            self.examples.append({'status':'unmatched','prediction_id':p['id'],'kind':p['kind'],
                                  'time':p['time'],'frame_ids':p.get('frame_ids',[])[:]})

    def finalize(self):
                                                                                  

                                                                           
                                                                              
                                                                         
           
        self._settle(float('inf'),final=True)

    def snapshot(self):
        def ratio(a,b):return round(a/b,4) if b else None
        scores=deepcopy(self.scores)
        for score in scores.values():
            score['precision']=ratio(score['tp'],score['tp']+score['fp'])
            score['recall']=ratio(score['tp'],score['tp']+score['fn'])
        return {'frames':self.frames,'player_precision':ratio(self.matched,self.detected),
                'player_recall':ratio(self.matched,self.frames*22),'identity_accuracy':ratio(self.correct,self.matched),
                'position_mae_m':ratio(self.position_error,self.matched),'ball_recall':ratio(self.ball_frames,self.frames),
                'ball_position_mae_m':ratio(self.ball_error,self.ball_frames),'ball_speed_mae_mps':ratio(self.speed_error,self.speed_n),
                'speed_samples':self.speed_n,'event_scores':scores,'examples':list(self.examples),
                'pending_truth':len(self.truth),'pending_predictions':len(self.pred),
                'event_tolerance_s':.8,'maturation_s':1.2,'scope':'this synthetic camera; not real broadcast footage'}
