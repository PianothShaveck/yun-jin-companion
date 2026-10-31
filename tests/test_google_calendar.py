"""OAuth boundary, HTTP pagination, recurrence and merge contract tests."""
import json
import os
import tempfile
import io
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app'))
from yun_jin_google_auth import GoogleAPI, GoogleError, Cancelled, authorize, client_config, request_json, TOKEN_URL
from yun_jin_google_codec import decode, encode, merge


class Vault:
    def __init__(self):
        self.value={'client':{'client_id':'test','client_secret':'test'}, 'token':{'access_token':'access','refresh_token':'refresh','expires_at':0}}
    def load(self, _): return self.value
    def save(self, _, value): self.value=value


class AuthTests(unittest.TestCase):
    def test_expired_refresh_token_requests_reconnection_without_exposing_payload(self):
        error=HTTPError(TOKEN_URL,400,'Bad request',{},io.BytesIO(json.dumps({
            'error':'invalid_grant','error_description':'private-response-sentinel'}).encode()))
        with patch('yun_jin_google_auth.build_opener') as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaises(GoogleError) as result:
                request_json(TOKEN_URL,method='POST',form={'refresh_token':'private-token'})
        self.assertEqual(result.exception.status,401)
        self.assertNotIn('private-response-sentinel',str(result.exception))
        self.assertNotIn('private-token',str(result.exception))

    def test_app_identity_is_bundled_without_user_setup_or_user_tokens(self):
        with patch.dict(os.environ,{'YUNJIN_GOOGLE_CLIENT_FILE':''}):
            config=client_config()
        self.assertEqual(set(config),{'client_id','client_secret'})
        self.assertTrue(config['client_id'].endswith('.apps.googleusercontent.com'))
        self.assertTrue(config['client_secret'])
        bundled=json.loads((Path(__file__).resolve().parents[1]/'app/google-calendar-client.json').read_text())
        self.assertEqual(set(bundled),{'installed'})
        self.assertEqual(set(bundled['installed']),{'client_id','client_secret'})

    def test_developer_override_is_optional_and_cannot_change_google_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'client.json'
            path.write_text(json.dumps({'installed':{'client_id':'test.apps.googleusercontent.com',
                'client_secret':'test','token_uri':'https://untrusted.invalid','access_token':'do-not-import'}}))
            with patch.dict(os.environ,{'YUNJIN_GOOGLE_CLIENT_FILE':str(path)}):
                self.assertEqual(client_config(),{'client_id':'test.apps.googleusercontent.com','client_secret':'test'})
            path.write_text(json.dumps({'web':{'client_id':'test.apps.googleusercontent.com','client_secret':'test'}}))
            with self.assertRaises(ValueError):client_config(path)
            path.write_text('[]')
            with self.assertRaises(ValueError):client_config(path)

    def test_callback_pkce_state_and_exchange(self):
        cancel=threading.Event(); queries=[]; calls=[]
        def browser(url):
            query=parse_qs(urlparse(url).query);queries.append(query)
            self.assertEqual(query['code_challenge_method'],['S256'])
            def callback():
                with self.assertRaises(Exception):
                    urlopen(query['redirect_uri'][0]+'?state=wrong&code=bad',timeout=2)
                urlopen(query['redirect_uri'][0]+'?state='+query['state'][0]+'&code=test',timeout=2).read()
            thread=threading.Thread(target=callback);thread.start()
        def request(url, **kwargs):
            calls.append((url,kwargs))
            return {'access_token':'test','refresh_token':'refresh','expires_in':3600} if url.endswith('/token') else {'sub':'account','email':'test@example.test','email_verified':True}
        identity, credentials=authorize({'client_id':'test','client_secret':'test'},browser,cancel,timeout=5,request=request)
        self.assertEqual(identity['sub'],'account')
        form=calls[0][1]['form']
        import hashlib,base64
        self.assertEqual(queries[0]['code_challenge'][0],base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'].encode()).digest()).rstrip(b'=').decode())
        self.assertEqual(form['code'],'test')
        self.assertNotEqual(queries[0]['state'][0],form['code_verifier'])
        self.assertEqual(credentials['token']['refresh_token'],'refresh')

    def test_cancel_no_token_request(self):
        cancel=threading.Event()
        def browser(_):cancel.set()
        def request(*_,**__):self.fail('No HTTP after cancellation')
        with self.assertRaises(Cancelled):authorize({'client_id':'test'},browser,cancel,request=request)

    def test_refresh_keeps_refresh_token_and_single_401_retry(self):
        calls=[];vault=Vault()
        def request(url, **kwargs):
            calls.append((url,kwargs))
            if url.endswith('/token'):return {'access_token':'fresh','expires_in':3600}
            return {'items':[]}
        api=GoogleAPI(vault,'account',request=request)
        api.calendars()
        self.assertEqual(vault.value['token']['refresh_token'],'refresh')
        self.assertEqual(calls[1][1]['headers']['Authorization'],'Bearer fresh')
        self.assertEqual(len(calls),2)

    def test_sync_pagination_parameters_stay_stable(self):
        api=GoogleAPI(Vault(),'account'); calls=[]
        def call(path,**kwargs):
            calls.append((path,kwargs['params']))
            return {'items':[{'id':'1'}],'nextPageToken':'page'} if len(calls)==1 else {'items':[{'id':'2'}],'nextSyncToken':'next'}
        api.call=call
        items,token=api.events('calendar@example.test','sync')
        self.assertEqual(token,'next');self.assertEqual(len(items),2)
        self.assertEqual(calls[0][1]['syncToken'],calls[1][1]['syncToken'])
        self.assertEqual(calls[1][1]['pageToken'],'page')
        self.assertEqual(calls[1][1]['singleEvents'],'false')
        self.assertNotIn('timeMin',calls[1][1])

    def test_conditional_patch_uses_if_match_and_escapes_calendar_id(self):
        api=GoogleAPI(Vault(),'account'); calls=[]
        api._token=lambda force=False:'token'
        api.request=lambda url,**kw:calls.append((url,kw)) or {}
        api.event('a/b@example.test','abc','PATCH',{'summary':'Title'},etag='"v1"')
        self.assertIn('a%2Fb%40example.test',calls[0][0])
        self.assertEqual(calls[0][1]['headers']['If-Match'],'"v1"')


class CodecTests(unittest.TestCase):
    def event(self,**extra):
        event=dict(id='id',summary='Title',description='Note',start={'dateTime':'2027-03-27T09:00:00+01:00','timeZone':'Europe/Rome'},end={'dateTime':'2027-03-27T10:00:00+01:00','timeZone':'Europe/Rome'},reminders={'useDefault':False,'overrides':[{'method':'popup','minutes':10}]})
        event.update(extra);return event

    def test_roundtrip_supported_rules_and_dst(self):
        for rule in ['FREQ=DAILY;COUNT=3','FREQ=WEEKLY;BYDAY=MO,WE;INTERVAL=2;COUNT=9','FREQ=MONTHLY;COUNT=4','FREQ=YEARLY;COUNT=3','FREQ=DAILY;UNTIL=20270405T215959Z']:
            with self.subTest(rule=rule):
                item,readonly=decode(self.event(recurrence=['RRULE:'+rule]),'Europe/Rome')
                self.assertFalse(readonly)
                again,_=decode(dict(id='id',**encode(item)),'Europe/Rome')
                self.assertEqual(again,item)
        item,_=decode(self.event())
        item.update(start_local='2027-03-28T09:00:00',end_local='2027-03-28T10:00:00')
        self.assertTrue(encode(item)['start']['dateTime'].endswith('+02:00'))

    def test_all_day_exclusive_end_roundtrip(self):
        item,_=decode(self.event(start={'date':'2027-01-01'},end={'date':'2027-01-03'}),'Europe/Rome')
        self.assertTrue(item['all_day'])
        self.assertEqual(encode(item)['end'],{'date':'2027-01-03'})

    def test_unsupported_rule_retained_readonly_and_empty_patch_preserves_google_fields(self):
        item,readonly=decode(self.event(recurrence=['RRULE:FREQ=MONTHLY;BYDAY=2MO']))
        self.assertTrue(readonly)
        self.assertEqual(encode(item,item),{})
        changed=dict(item,title='New')
        self.assertEqual(encode(changed,item),{'summary':'New'})

    def test_default_reminders_are_applied_without_rewriting_google_defaults(self):
        event=self.event(reminders={'useDefault':True})
        value,readonly=decode(event,'Europe/Rome',[{'method':'popup','minutes':30},{'method':'email','minutes':10}])
        self.assertFalse(readonly);self.assertEqual(value['reminder_minutes'],30)
        edited=dict(value,title='New title')
        self.assertEqual(encode(edited,value),{'summary':'New title'})
        edited['reminder_minutes']=5
        self.assertEqual(encode(edited,value)['reminders'],{'useDefault':False,'overrides':[{'method':'popup','minutes':5}]})
    def test_schedule_is_atomic_in_merge(self):
        item,_=decode(self.event())
        local=dict(item,start_local='2027-03-27T11:00:00',end_local='2027-03-27T12:00:00')
        remote=dict(item,end_local='2027-03-27T13:00:00')
        self.assertTrue(merge(item,local,remote)[1])


if __name__=='__main__':unittest.main()
