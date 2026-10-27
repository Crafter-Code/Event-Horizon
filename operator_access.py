                                                                              
import base64
import binascii
import hmac
import os


def required():
    return bool(os.getenv('EVENT_HORIZON_OPERATOR_PASSWORD') or
                os.getenv('EVENT_HORIZON_PUBLIC_ORIGIN') or
                os.getenv('EVENT_HORIZON_BIND','127.0.0.1') not in ('127.0.0.1','localhost','::1'))


def validate_configuration():
    if required() and len(os.getenv('EVENT_HORIZON_OPERATOR_PASSWORD','')) < 32:
        raise ValueError('Public hosting requires EVENT_HORIZON_OPERATOR_PASSWORD with at least 32 characters')


def authorized(header):
    if not required():return True
    password = os.getenv('EVENT_HORIZON_OPERATOR_PASSWORD','')
    if not isinstance(header,str) or len(password) < 32 or len(header) > 1024 or not header.isascii():return False
    try:
        scheme, encoded = header.split(' ',1)
        if scheme.lower() != 'basic':return False
        username, supplied = base64.b64decode(encoded,validate=True).decode('utf-8').split(':',1)
    except (ValueError, UnicodeError, binascii.Error):return False
    user_ok = hmac.compare_digest(username.encode(),b'editor')
    password_ok = hmac.compare_digest(supplied.encode(),password.encode())
    return user_ok and password_ok
