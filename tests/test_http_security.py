import base64
from email.message import Message
import hashlib
import http.client
import json
import os
import socket
import threading
import unittest
from unittest.mock import patch

import app
import operator_access
from broadcast_peer import BroadcastPeer
from http_security import BoundedHTTPServer, body_length, policy


class HttpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'EVENT_HORIZON_OPERATOR_PASSWORD':'',
            'EVENT_HORIZON_PUBLIC_ORIGIN':'', 'EVENT_HORIZON_BIND':'127.0.0.1'})
        self.environment.start()
        self.server = BoundedHTTPServer(('127.0.0.1',0),app.Handler,max_connections=2)
        self.worker = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)
        self.environment.stop()

    def get(self,path='/',headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            connection.request('GET',path,headers=headers or {})
            response=connection.getresponse()
            return response.status,dict(response.getheaders()),response.read()
        finally:
            connection.close()

    def test_foreign_host_cannot_read_local_editor(self):
        status,headers,body=self.get('/state?view=editor',{'Host':'foreign.example'})
        self.assertEqual(status,403)
        self.assertNotIn(b'editorial',body)
        self.assertEqual(self.get('/health/live')[0],200)
        self.assertEqual(self.get('/health/live',{'Host':'internal-probe.example'})[0],200)

    def test_pages_errors_and_challenges_have_security_headers(self):
        for path in ('/','/output','/missing','/health/live'):
            status,headers,body=self.get(path)
            self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
            self.assertEqual(headers['X-Frame-Options'],'SAMEORIGIN')
            self.assertEqual(headers['Referrer-Policy'],'no-referrer')
            self.assertIn("frame-ancestors 'self'",headers['Content-Security-Policy'])
            self.assertNotIn('Python',headers['Server'])
        with patch.dict(os.environ,{'EVENT_HORIZON_OPERATOR_PASSWORD':'x'*40}):
            status,headers,body=self.get('/editor')
            self.assertEqual(status,401)
            self.assertIn('Content-Security-Policy',headers)

    def test_inline_script_hash_allows_only_the_actual_script(self):
        script=b'window.example=1;'
        expected=base64.b64encode(hashlib.sha256(script).digest()).decode()
        value=policy(b'<script>'+script+b'</script>','text/html')
        self.assertIn("'sha256-"+expected+"'",value)
        self.assertNotIn('unsafe-inline',value.split(';')[1])
        self.assertNotIn('unsafe-eval',value)

    def test_conflicting_or_ambiguous_body_framing_is_rejected(self):
        cases=[ [('Content-Length','2'),('Content-Length','2')],
            [('Content-Length','2'),('Transfer-Encoding','chunked')],
            [('Content-Length','-2')], [('Content-Length','5000')], [] ]
        for pairs in cases:
            headers=Message()
            for name,value in pairs:headers[name]=value
            with self.assertRaises(ValueError):body_length(headers,4096)
        headers=Message();headers['Content-Length']='2'
        self.assertEqual(body_length(headers,4096),2)

    def test_excess_connections_are_rejected_and_slots_recover(self):
        with self.server.slots:
            with self.server.slots:
                status,headers,body=self.get('/health/live')
                self.assertEqual(status,503)
        self.assertEqual(self.get('/health/live')[0],200)

    def test_credential_fields_and_embedded_url_secrets_fail_closed(self):
        with patch.dict(os.environ,{'EVENT_HORIZON_OPERATOR_PASSWORD':'x'*40}):
            self.assertFalse(operator_access.authorized('Basic non-ascii-\u00e9'))
        for url in ('https://user:secret@example.invalid/agent',
                    'https://example.invalid/agent?key=secret',
                    'https://example.invalid/agent#secret', 'https:///agent'):
            with self.assertRaises(ValueError):BroadcastPeer(url)
        BroadcastPeer('http://127.0.0.1:9018/a2a/broadcast')
