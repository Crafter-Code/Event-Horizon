                                                                             
import math


def assess(origin, end, opponents, direction):
    length=math.dist(origin,end)
    forward=(end[0]-origin[0])*direction
    pressure=sum(math.dist(origin,p)<=5 for p in opponents)
    components={'distance':min(1,length/40),
                'direction':max(0,forward/length) if length else 0,
                'pressure':min(1,pressure/3)}
    value=round(100*(.4*components['distance']+.25*components['direction']+.35*components['pressure']))
    return {'distance_m':round(length,2),'forward_m':round(forward,2),
            'pressure_count':pressure,'difficulty':value,
            'difficulty_band':'high' if value>=60 else 'medium' if value>=30 else 'low',
            'components':components,'weights':{'distance':.4,'direction':.25,'pressure':.35},
            'method':'heuristic 0–100; not a probability'}
