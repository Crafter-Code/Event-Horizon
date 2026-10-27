                                                                            

                                                                              
                                                                         
                                                                        
   
import http.client
import json
import os
from urllib.parse import urlsplit
from cloud_contract import encode, digest, MAX_BODY
from observability import observe


class IngressConflict(ValueError):pass
class IngressUnavailable(OSError):pass


class JsonEndpoint:
    def __init__(self, url, headers=None, allow_local=False, timeout=5):
        parts = urlsplit(url)
        local = allow_local and parts.hostname in ('127.0.0.1','localhost')
        if (parts.scheme != 'https' and not (local and parts.scheme == 'http')) or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('A fixed HTTPS endpoint without embedded secrets is required')
        self.parts, self.headers, self.timeout = parts, headers or {}, timeout
        self.connection = None

    def post(self, payload, headers=None):
        if self.connection is None:
            cls = http.client.HTTPSConnection if self.parts.scheme == 'https' else http.client.HTTPConnection
            self.connection = cls(self.parts.hostname, self.parts.port, timeout=self.timeout)
        try:
            self.connection.request('POST', self.parts.path or '/', body=encode(payload),
                headers={**self.headers, **(headers or {}), 'Content-Type':'application/json'})
            response = self.connection.getresponse()
            body = response.read(MAX_BODY+1)
            if response.status != 200 or len(body)>MAX_BODY:
                raise IngressUnavailable(f'Ingress status {response.status}')
            return json.loads(body)
        except (OSError, http.client.HTTPException, ValueError) as error:
            self.close()
            raise IngressUnavailable('Ingress request failed') from error

    def close(self):
        if self.connection:self.connection.close()
        self.connection = None


class FunctionTransport:
    def __init__(self, endpoint):self.endpoint = endpoint

    def submit(self, payload):
        with observe.span('eh.functions.roundtrip', run_key=payload['run_key'], tick=payload['tick']):
            receipt = self.endpoint.post(payload, observe.headers())
            if (not isinstance(receipt,dict) or receipt.get('digest') != digest(payload)
                    or receipt.get('tick') != payload['tick'] or receipt.get('accepted') is not True):
                raise IngressUnavailable('Unconfirmed ingress receipt')
            return receipt

    def close(self):self.endpoint.close()


def from_environment():
    mode = os.getenv('EVENT_HORIZON_INGRESS','local')
    if mode == 'local':return None
    if mode != 'functions':raise ValueError('Invalid ingress mode')
    token = os.environ['EVENT_HORIZON_INGEST_TOKEN']
    key = os.environ['EVENT_HORIZON_FUNCTION_KEY']
    if len(token)<32 or not key:raise ValueError('Ingress secrets are missing')
    endpoint = JsonEndpoint(os.environ['EVENT_HORIZON_FUNCTION_URL'], {'x-functions-key':key})
    return FunctionTransport(endpoint)
