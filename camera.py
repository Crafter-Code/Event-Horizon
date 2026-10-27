                                                                                
from base64 import b64encode
from collections import OrderedDict
from copy import deepcopy
import time

from raster import render, CALIBRATION
from vision import VideoRecognizer
from vision_evaluation import RecognitionEvaluation


class SyntheticCamera:
    def __init__(self):
        self.recognizer=VideoRecognizer();self.evaluation=RecognitionEvaluation()
        self.frames=OrderedDict();self.png=None;self.processing_ms=None;self.error=None

    def advance(self, match):
        started=time.monotonic()
        players=[{'team':p.team,'number':p.number,'x':p.x,'y':p.y} for p in match.players]
        png=render(players,match.ball)
        try:
                                                                                  
            observed=self.recognizer.observe(png,round(match.clock,2),match.period,not bool(match.restart) and not match.finished)
            self.evaluation.compare(observed,players,match.ball,match.events,self.recognizer.events)
            if match.finished:self.evaluation.finalize()
        except ValueError as error:
            self.error=str(error);return
        self.png=png;self.error=None
        self.frames[observed['frame_id']]=png
        while len(self.frames)>128:self.frames.popitem(last=False)
        self.processing_ms=round((time.monotonic()-started)*1000,2)

    def snapshot(self, include_image=True):
        result=self.recognizer.snapshot()
        result.update(enabled=True,calibration=deepcopy(CALIBRATION),evaluation=self.evaluation.snapshot(),
                      frame_range=[next(iter(self.frames)),next(reversed(self.frames))] if self.frames else None,
                      processing_ms=self.processing_ms,error=self.error,
                      frame_png=b64encode(self.png).decode() if include_image and self.png else None)
        return result
