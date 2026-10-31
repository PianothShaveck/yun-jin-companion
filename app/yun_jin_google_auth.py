# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop OAuth with PKCE, loopback callback and OS-backed credential storage."""
from yun_jin_i18n import tr
import base64
import hashlib
import json
import os
import secrets
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qs, quote
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

SCOPES = 'openid email https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.calendarlist.readonly'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
MAX_RESPONSE = 8 * 1024 * 1024


class GoogleError(Exception):
    def __init__(self, status=0, retry_after=0):
        self.status = status
        self.retry_after = min(3600, max(0, int(retry_after or 0)))
        messages = {401: tr('Ricollega Google Calendar.'), 403: tr('Accesso al calendario non consentito.'),
                    429: tr('Google Calendar occupato. Riprova più tardi.')}
        super().__init__(messages.get(status, tr('Google Calendar non raggiungibile. Le modifiche restano salvate.')))


class Cancelled(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_json(url, *, method='GET', headers=None, data=None, form=None, cancel=None):
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    allowed = {'oauth2.googleapis.com', 'www.googleapis.com', 'openidconnect.googleapis.com'}
    if urlparse(url).scheme != 'https' or urlparse(url).hostname not in allowed:
        raise ValueError('Invalid Google endpoint')
    headers = dict(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
        headers['Content-Type'] = 'application/json'
    if form is not None:
        body = urlencode(form).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    import certifi
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())), NoRedirect())
    try:
        with opener.open(Request(url, data=body, headers=headers, method=method), timeout=12) as response:
            raw = response.read(MAX_RESPONSE+1)
            if len(raw) > MAX_RESPONSE:
                raise GoogleError()
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        retry = exc.headers.get('Retry-After', '0')
        if url == TOKEN_URL and exc.code == 400:
            # Expired/revoked refresh tokens return invalid_grant, not HTTP 401.
            # Classify only that known code; never expose Google's payload.
            try:
                invalid_grant = json.loads(exc.read(4096)).get('error') == 'invalid_grant'
            except (ValueError, AttributeError, OSError):
                invalid_grant = False
            if invalid_grant:
                raise GoogleError(401) from None
        raise GoogleError(exc.code, int(retry) if retry.isdigit() else 0) from None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise GoogleError() from None


class Vault:
    """Never fall back to a plaintext file or a third-party keyring backend."""
    def __init__(self, profile):
        self.profile = profile
        if sys.platform == 'darwin':
            from keyring.backends.macOS import Keyring
        elif sys.platform == 'win32':
            from keyring.backends.Windows import WinVaultKeyring as Keyring
        else:
            from keyring.backends.SecretService import Keyring
        self.backend = Keyring()
        if self.backend.priority <= 0:
            raise RuntimeError(tr('Portachiavi del sistema non disponibile.'))

    def load(self, account):
        raw = self.backend.get_password('Yun Jin Calendar/' + self.profile, account)
        return json.loads(raw) if raw else None

    def save(self, account, value):
        self.backend.set_password('Yun Jin Calendar/' + self.profile, account, json.dumps(value))

    def delete(self, account):
        from keyring.errors import PasswordDeleteError
        try:
            self.backend.delete_password('Yun Jin Calendar/' + self.profile, account)
        except PasswordDeleteError:
            pass


def client_config(path=None):
    path = path or os.environ.get('YUNJIN_GOOGLE_CLIENT_FILE', '')
    # A Desktop client identifies the app, not the user. Ship that public app
    # identity; account authorization is still obtained in the system browser.
    # The optional override remains available for developer test projects only.
    file = Path(path) if path else Path(__file__).with_name('google-calendar-client.json')
    try:
        if file.stat().st_size > 65536:
            raise ValueError()
        value = json.loads(file.read_text(encoding='utf-8')).get('installed', {})
    except (OSError, ValueError, AttributeError):
        raise ValueError(tr('Collegamento Google non disponibile. Reinstalla Yun Jin e riprova.')) from None
    if not isinstance(value, dict) or not isinstance(value.get('client_id'), str) or not value['client_id'].endswith('.apps.googleusercontent.com') or not isinstance(value.get('client_secret'), str) or not value['client_secret']:
        raise ValueError(tr('File OAuth non valido.'))
    # Endpoints in a supplied file are deliberately ignored.
    return {key: value[key] for key in ('client_id', 'client_secret')}


def authorize(config, open_browser, cancel, timeout=180, request=request_json):
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            valid = (parsed.path == '/callback' and params.get('state') == [state]
                     and self.headers.get('Host') == '127.0.0.1:' + str(self.server.server_port))
            if not valid:
                self.send_error(400)
                return
            result['code'] = params.get('code', [''])[0]
            result['error'] = params.get('error', [''])[0]
            body = ('<!doctype html><meta charset="utf-8"><title>Yun Jin</title><p>' + tr('Puoi chiudere questa finestra.') + '</p>').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'none'")
            self.end_headers()
            self.wfile.write(body)

    class CallbackServer(HTTPServer):
        def get_request(self):
            connection,address=super().get_request()
            connection.settimeout(2)
            return connection,address

    with CallbackServer(('127.0.0.1', 0), Handler) as server:
        server.timeout = .25
        redirect = 'http://127.0.0.1:' + str(server.server_port) + '/callback'
        query = dict(client_id=config['client_id'], redirect_uri=redirect, response_type='code',
                     scope=SCOPES, state=state, code_challenge=challenge, code_challenge_method='S256',
                     access_type='offline', prompt='consent select_account')
        open_browser(AUTH_URL + '?' + urlencode(query))
        deadline = time.monotonic() + timeout
        while not result and not cancel.is_set() and time.monotonic() < deadline:
            server.handle_request()
    if cancel.is_set() or not result or result.get('error') or not result.get('code'):
        raise Cancelled()
    token = request(TOKEN_URL, method='POST', form=dict(config, grant_type='authorization_code',
                    code=result['code'], code_verifier=verifier, redirect_uri=redirect), cancel=cancel)
    if not token.get('refresh_token') or not token.get('access_token'):
        raise GoogleError(401)
    identity = request('https://openidconnect.googleapis.com/v1/userinfo',
                       headers={'Authorization': 'Bearer ' + token['access_token']}, cancel=cancel)
    if not identity.get('sub') or not identity.get('email_verified'):
        raise GoogleError(401)
    token['expires_at'] = time.time() + int(token.get('expires_in', 3600))
    return identity, dict(token=token, client=config)


class GoogleAPI:
    def __init__(self, vault, account, cancel=None, request=request_json):
        self.vault, self.account = vault, account
        self.cancel, self.request = cancel or threading.Event(), request
        self.credentials = None

    def _token(self, force=False):
        credentials = self.credentials or self.vault.load(self.account)
        if not credentials:
            raise GoogleError(401)
        token = credentials['token']
        if force or token.get('expires_at', 0) < time.time()+60:
            refreshed = self.request(TOKEN_URL, method='POST', form=dict(credentials['client'],
                grant_type='refresh_token', refresh_token=token['refresh_token']), cancel=self.cancel)
            token.update(refreshed)
            token['expires_at'] = time.time() + int(refreshed.get('expires_in', 3600))
            self.vault.save(self.account, credentials)
        self.credentials = credentials
        return token['access_token']

    def call(self, path, *, method='GET', data=None, etag=None, params=None):
        url = 'https://www.googleapis.com/calendar/v3/' + path
        if params:
            url += '?' + urlencode(params)
        for attempt in range(2):
            headers = {'Authorization': 'Bearer ' + self._token(force=bool(attempt))}
            if etag:
                headers['If-Match'] = etag
            try:
                return self.request(url, method=method, data=data, headers=headers, cancel=self.cancel)
            except GoogleError as exc:
                if exc.status != 401 or attempt:
                    raise

    def calendars(self):
        items, page = [], ''
        for _ in range(100):
            result = self.call('users/me/calendarList', params={'maxResults': 250, **({'pageToken': page} if page else {})})
            items.extend(result.get('items', []))
            page = result.get('nextPageToken', '')
            if not page:
                return items
        raise GoogleError()

    def events(self, calendar, token=''):
        items, page = [], ''
        for _ in range(100):
            params = {'maxResults': 250, 'singleEvents': 'false', 'showDeleted': 'true'}
            if token:
                params['syncToken'] = token
            if page:
                params['pageToken'] = page
            result = self.call('calendars/' + quote(calendar, safe='') + '/events', params=params)
            items.extend(result.get('items', []))
            if len(items) > 20000:
                raise ValueError(tr('Calendario troppo grande. Seleziona un calendario più piccolo.'))
            page = result.get('nextPageToken', '')
            if not page:
                if not result.get('nextSyncToken'):
                    raise GoogleError()
                return items, result['nextSyncToken']
        raise GoogleError()

    def event(self, calendar, remote, method='GET', data=None, etag=None):
        return self.call('calendars/' + quote(calendar, safe='') + '/events' + ('/' + quote(remote, safe='') if remote else ''),
                         method=method, data=data, etag=etag)

    def instance(self, calendar, remote, original):
        result = self.call('calendars/' + quote(calendar, safe='') + '/events/' + quote(remote, safe='') + '/instances',
                           params={'originalStart': original, 'showDeleted': 'true', 'maxResults': 250})
        rows = result.get('items', [])
        if len(rows) != 1:
            raise GoogleError()
        return rows[0]
