                                                                                    
import os
import threading
import azure.functions as func
from cloud_contract import decode, digest
from ingress import JsonEndpoint, IngressUnavailable
from observability import observe

observe.configure()

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
_backend = None
_lock = threading.Lock()


def backend():
    global _backend
    if _backend is None:
        token = os.environ['EVENT_HORIZON_INGEST_TOKEN']
        if len(token)<32:raise ValueError('Relay secret is too short')
        _backend = JsonEndpoint(os.environ['EVENT_HORIZON_BACKEND_URL'],
                                {'Authorization':'Bearer '+token})
    return _backend


@app.route(route='events', methods=['POST'])
def events(req: func.HttpRequest) -> func.HttpResponse:
    try:
        if req.headers.get('content-type','').split(';')[0].strip() != 'application/json':
            raise ValueError('JSON required')
        payload = decode(req.get_body())
        with observe.incoming(req.headers), observe.span('eh.functions.receive',
                run_key=payload['run_key'],tick=payload['tick'],event_count=len(payload['events'])):
                                                                            
                                                                                 
            with _lock:
                receipt = backend().post(payload, observe.headers())
            if not isinstance(receipt,dict) or receipt.get('digest') != digest(payload) or receipt.get('accepted') is not True:
                raise IngressUnavailable('Backend did not confirm the exact batch')
            return func.HttpResponse(body=__import__('json').dumps(receipt),status_code=200,mimetype='application/json')
    except (ValueError, UnicodeError):
        return func.HttpResponse('{"error":"Invalid event envelope"}',status_code=400,mimetype='application/json')
    except (OSError, KeyError):
                                                                            
        return func.HttpResponse('{"error":"Event processing unavailable"}',status_code=503,mimetype='application/json')
