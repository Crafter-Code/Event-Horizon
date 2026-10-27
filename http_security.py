import base64
import hashlib
import re
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit


REQUEST_TIMEOUT = 15


def host_allowed(headers, port, public_origin=''):
    hosts = headers.get_all('Host', [])
    if len(hosts) != 1:
        return False
    allowed = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'}
    public = urlsplit(public_origin)
    if public.scheme == 'https' and public.netloc and not public.username and not public.password:
        allowed.add(public.netloc)
    return hosts[0] in allowed


def body_length(headers, limit):
    values = headers.get_all('Content-Length', [])
    if headers.get_all('Transfer-Encoding') or len(values) != 1:
        raise ValueError('A single Content-Length is required')
    if not re.fullmatch(r'[0-9]{1,7}', values[0]):
        raise ValueError('Invalid Content-Length')
    length = int(values[0])
    if not 0 < length <= limit:
        raise ValueError('Request body exceeds limit')
    return length


def policy(content=b'', kind=''):
    hashes = []
    if kind.startswith('text/html'):
        for script in re.findall(br'<script\b[^>]*>(.*?)</script\s*>', content, re.I | re.S):
            if script.strip():
                hashes.append("'sha256-" + base64.b64encode(hashlib.sha256(script).digest()).decode('ascii') + "'")
    scripts = "script-src 'self'" + (' ' + ' '.join(hashes) if hashes else '')
    return "; ".join(("default-src 'self'", scripts, "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:", "connect-src 'self'", "font-src 'self'",
        "object-src 'none'", "base-uri 'none'", "form-action 'self'", "frame-ancestors 'self'"))


class BoundedHTTPServer(ThreadingHTTPServer):
    def __init__(self, address, handler, max_connections=32):
        self.slots = threading.BoundedSemaphore(max_connections)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\nRetry-After: 1\r\n\r\n')
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        from logging import getLogger
        getLogger('event_horizon').warning('HTTP request failed')
