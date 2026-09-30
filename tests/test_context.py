"""Ambient behavior and network boundaries, with deterministic clocks and offline fixtures."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6 import sip
from PyQt6.QtCore import QEventLoop, QTimer, QProcess, QSettings
from PyQt6.QtWidgets import QApplication
from yun_jin_app import Companion
from yun_jin_data import Store
from yun_jin_context import Context, time_period, GREETINGS
from yun_jin_weather import fetch_weather, read_json, weather_kind, WEATHER_TTL, MAX_RESPONSE
import yun_jin_context as context_module

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.now = 1800000000.
        self.location = {'latitude': 45.46, 'longitude': 9.19, 'city': 'Test', 'checked': self.now}
        self.current = {'current': {'weather_code': 61, 'is_day': 1, 'time': self.now-300}}

    def test_minimal_requests_and_coarse_location_cache(self):
        get = Mock(side_effect=[dict(self.location, success=True, latitude=45.4642), self.current])
        result = fetch_weather(now=self.now, get=get)
        self.assertEqual(result['kind'], 'rain')
        self.assertEqual(result['location']['latitude'], 45.46)
        urls = [c.args[0] for c in get.call_args_list]
        self.assertIn('fields=success,city,latitude,longitude', urls[0])
        self.assertIn('current=weather_code%2Cis_day', urls[1]); self.assertNotIn('hourly=', urls[1])
        get.reset_mock(side_effect=True); get.return_value = self.current
        self.assertEqual(fetch_weather(result['location'], self.now+60, get)['kind'], 'rain')
        get.assert_called_once()
        self.assertTrue(get.call_args.args[0].startswith('https://api.open-meteo.com/'))

    def test_expired_location_refetched_and_invalid_location_silent(self):
        for location in (None, {}, dict(self.location, checked=self.now-86401), dict(self.location, latitude=float('nan'))):
            get = Mock(return_value={'success': False})
            self.assertIsNone(fetch_weather(location, self.now, get)); get.assert_called_once()
        self.assertIsNone(fetch_weather(now=self.now, get=Mock(return_value={'success': True, 'latitude': 200, 'longitude': 9})))

    def test_known_conditions_and_night_is_not_sun(self):
        for code, kind in [(0,'sun'),(1,'sun'),(2,'cloud'),(45,'fog'),(61,'rain'),(56,'rain'),(71,'snow'),(95,'storm')]:
            self.assertEqual(weather_kind(code, 1), kind)
        self.assertEqual(weather_kind(0, 0), 'clear_night')
        for code, day in [(999,1),('61',1),(61,2),(True,1)]: self.assertIsNone(weather_kind(code,day))

    def test_stale_future_missing_and_malformed_weather_rejected(self):
        for current in ({}, {'weather_code':0,'is_day':1,'time':self.now-7201},
                        {'weather_code':0,'is_day':1,'time':self.now+3600},
                        {'weather_code':1000,'is_day':1,'time':self.now}):
            self.assertIsNone(fetch_weather(self.location, self.now, Mock(return_value={'current':current})))

    def test_response_size_and_timeout_are_bounded(self):
        response=Mock(); response.read.return_value=b'x'*(MAX_RESPONSE+1)
        cm=Mock(); cm.__enter__=Mock(return_value=response); cm.__exit__=Mock(return_value=False)
        with patch('yun_jin_weather.urlopen', return_value=cm) as open_url:
            with self.assertRaises(ValueError): read_json('https://example.test/')
        response.read.assert_called_once_with(MAX_RESPONSE+1)
        self.assertEqual(open_url.call_args.kwargs['timeout'],5)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(self.tmp.name)
        self.store.set_preference('updates_enabled',False)
        self.pet=Companion(self.store)
        for timer in (self.pet.timer,self.pet.reminder_timer,self.pet.checkpoint_timer): timer.stop()
        self.pet.cancel(); self.pet.idle(); self.pet.mode='normal'; self.pet.paused=False
        self.pet.use_extra_animations=True; self.pet.sound.enabled=True; self.pet.sound.interactions=True
        self.now=SimpleNamespace(local=datetime(2026,9,30,8), mono=100., wall=1800000000.)
        self.pet.context.shutdown()
        self.ctx=Context(self.pet, lambda:self.now.local, lambda:self.now.mono, lambda:self.now.wall)
        self.pet.context=self.ctx; self.ctx.enabled['weather']=False
        self.speech_patch=patch.object(self.pet.speech,'speak',return_value=True)
        self.speak=self.speech_patch.start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.pet.close(); self.pet.deleteLater(); app.processEvents(); self.store.close(); self.tmp.cleanup()

    def advance(self, seconds=61, hour=None, day=30):
        self.now.mono+=seconds; self.now.wall+=seconds
        if hour is not None: self.now.local=datetime(2026,9,day,hour)
        self.pet.cancel(); self.pet.idle()
        self.ctx.poll()

    def weather(self, kind='rain'):
        return {'kind':kind,'checked':self.now.wall,'observed':self.now.wall-300,
                'location':{'latitude':45.46,'longitude':9.19,'city':'Test','checked':self.now.wall}}

    def wait_until(self, predicate, timeout=5):
        deadline=time.monotonic()+timeout; loop=QEventLoop(); timer=QTimer()
        errors=[]
        def check():
            try:
                if predicate() or time.monotonic()>=deadline: loop.quit()
            except Exception as exc:
                errors.append(exc); loop.quit()
        timer.timeout.connect(check); timer.start(5)
        if not predicate(): loop.exec()
        timer.stop()
        if errors: raise errors[0]
        self.assertTrue(predicate(),'Timed out waiting for event')

    def test_greeting_only_once_and_uses_voice_language(self):
        self.store.set_preference('tts_language','it'); self.ctx.start()
        self.assertEqual(self.speak.call_count,1)
        self.assertEqual(self.speak.call_args.args[0],GREETINGS['it']['morning'])
        self.assertNotIn('language',self.speak.call_args.kwargs)
        for _ in range(3): self.ctx.start(); self.ctx.dispatch(); self.advance()
        self.assertEqual(self.speak.call_count,1)
        self.assertEqual(self.store.preference('tts_language',''),'it')

    def test_distinct_daypart_animations_and_single_startup_greeting(self):
        for hour, period, animation in [(8, 'morning', 'morning16'),
                                        (14, 'afternoon', 'afternoon16'),
                                        (20, 'evening', 'evening16')]:
            with self.subTest(period=period):
                self.ctx.shutdown(); self.pet.cancel(); self.pet.idle()
                self.now.local = datetime(2026, 9, 30, hour)
                self.ctx = Context(self.pet, lambda:self.now.local, lambda:self.now.mono, lambda:self.now.wall)
                self.pet.context = self.ctx; self.ctx.enabled['weather'] = False
                self.speak.reset_mock()
                with patch.object(self.pet, 'sequence') as sequence:
                    self.ctx.start(); self.ctx.start(); self.ctx.poll()
                    sequence.assert_called_once_with([(animation, 1)])
                self.speak.assert_called_once()
                self.assertEqual(self.speak.call_args.args[0], GREETINGS['it'][period])

    def test_each_time_period_once_rollback_midnight_and_resume(self):
        self.ctx.enabled['greeting']=False; self.ctx.start()
        with patch.object(self.pet,'sequence') as sequence:
            self.advance(hour=12); self.advance(hour=12)
            self.assertEqual(sequence.call_count,1)
            sequence.assert_called_with([('afternoon16',1)])
            self.advance(hour=8); self.advance(hour=12); self.assertEqual(sequence.call_count,1)
            self.advance(hour=18); self.advance(hour=18)
            self.assertEqual(sequence.call_count,2)
            sequence.assert_called_with([('evening16',1)])
            self.advance(hour=23); self.assertEqual(sequence.call_count,3)
            self.advance(hour=2, day=1)  # backwards: never replay
            self.assertEqual(sequence.call_count,3)
        self.assertEqual(time_period(datetime(2026,9,30,23)),time_period(datetime(2026,10,1,3)))

    def test_resume_only_latest_period_not_missed_animation_queue(self):
        self.ctx.enabled['greeting']=False; self.ctx.start()
        self.now.local=datetime(2026,10,4,20); self.now.mono+=86400
        with patch.object(self.pet,'sequence') as sequence:
            self.ctx.poll(); self.ctx.dispatch()
        sequence.assert_called_once_with([('evening16',1)])

    def test_unavailable_clock_silent_and_no_late_greeting(self):
        self.ctx.clock=Mock(side_effect=OSError('clock')); self.ctx.start(); self.ctx.poll()
        self.assertFalse(self.ctx.pending); self.speak.assert_not_called()
        self.ctx.clock=lambda:self.now.local; self.ctx.poll(); self.speak.assert_not_called()

    def test_manual_states_keep_priority_and_expired_reactions_discarded(self):
        self.ctx.enabled['greeting']=False; self.ctx.start()
        self.now.local=datetime(2026,9,30,12)
        self.pet.call_later(); self.ctx.poll(); self.assertEqual(self.pet.state,'follow_pending')
        self.assertIn('time',self.ctx.pending)
        self.now.mono+=301; self.pet.cancel(); self.pet.idle()
        with patch.object(self.pet,'sequence') as sequence: self.ctx.dispatch(); sequence.assert_not_called()
        for attr,value in [('paused',True),('locked',True),('menu_open',True),('following',True),('due_count',1)]:
            old=getattr(self.pet,attr); setattr(self.pet,attr,value)
            self.assertFalse(self.ctx.can_react(),attr); setattr(self.pet,attr,old)
        self.pet.mode='asleep'; self.assertFalse(self.ctx.can_react())
        self.pet.mode='normal'
        with patch.object(self.pet,'focus_active',return_value=True): self.assertFalse(self.ctx.can_react())
        self.pet.metronome.running=True; self.assertFalse(self.ctx.can_react()); self.pet.metronome.running=False
        self.pet.open_panel(); self.assertFalse(self.ctx.can_react()); self.pet.panel.hide()

    def test_disabling_removes_pending_and_never_replays_startup(self):
        self.pet.paused=True; self.ctx.start(); self.assertIn('greeting',self.ctx.pending)
        self.ctx.set_enabled('greeting',False); self.ctx.set_enabled('greeting',True)
        self.pet.paused=False; self.ctx.dispatch(); self.speak.assert_not_called()
        self.assertTrue(self.store.preference('context_greeting',False))
        self.ctx.set_enabled('time',False); self.advance(hour=12)
        self.ctx.set_enabled('time',True)
        with patch.object(self.pet,'sequence') as sequence: self.ctx.poll(); sequence.assert_not_called()

    def test_weather_changes_only_and_two_hour_cooldown(self):
        self.ctx.enabled.update(greeting=False,weather=True); self.ctx.start()
        self.ctx.queue_weather(self.weather()); self.ctx.dispatch()
        self.assertEqual(self.speak.call_count,1)
        with patch.object(self.ctx,'request_weather'): self.advance()
        self.ctx.queue_weather(self.weather()); self.ctx.dispatch()
        self.assertEqual(self.speak.call_count,1)
        self.ctx.queue_weather(self.weather('sun')); self.ctx.dispatch(); self.assertEqual(self.speak.call_count,1)
        self.now.mono+=7201; self.now.wall+=7201; self.pet.cancel(); self.pet.idle()
        self.ctx.queue_weather(self.weather('snow')); self.ctx.dispatch(); self.assertEqual(self.speak.call_count,2)

    def test_weather_cache_delays_network_and_failures_retry_only_hourly(self):
        self.store.set_preference('context_weather_cache',self.weather())
        self.ctx.enabled.update(greeting=False,weather=True)
        with patch.object(self.ctx,'request_weather') as request:
            self.ctx.start(); request.assert_not_called()
            self.advance(); request.assert_not_called()
        self.now.mono+=3601; self.now.wall+=3601
        with patch.object(context_module,'BASE',Path(self.tmp.name)):
            (Path(self.tmp.name)/'yun_jin_weather.py').write_text('print("null")')
            self.ctx.poll(); self.wait_until(lambda:self.ctx.process is None)
        self.assertGreater(self.ctx.next_weather,self.now.mono+3599)
        with patch.object(self.ctx,'request_weather') as request: self.ctx.poll(); request.assert_not_called()

    def test_worker_result_queued_to_gui_and_saved_only_when_valid(self):
        self.ctx.enabled.update(greeting=False,weather=True); self.ctx.start()
        worker=Path(self.tmp.name)/'yun_jin_weather.py'
        for raw,valid in [(json.dumps(self.weather()),True),('null',False),('{',False),('x'*40000,False)]:
            worker.write_text('import sys\nsys.stdin.buffer.read()\nprint('+repr(raw)+')',encoding='utf-8')
            with patch.object(context_module,'BASE',Path(self.tmp.name)),patch.object(self.ctx,'queue_weather') as queue:
                self.ctx.request_weather(); self.wait_until(lambda:self.ctx.process is None)
                self.assertEqual(queue.call_count,int(valid))
        self.assertEqual(self.store.preference('context_weather_cache',None)['kind'],'rain')

    def test_slow_worker_does_not_block_gui_and_disable_ignores_result(self):
        self.ctx.enabled.update(greeting=False,weather=True); self.ctx.start()
        worker=Path(self.tmp.name)/'yun_jin_weather.py'
        worker.write_text('import time\ntime.sleep(60)\nprint("null")')
        with patch.object(context_module,'BASE',Path(self.tmp.name)):
            self.ctx.request_weather(); process=self.ctx.process
            self.wait_until(lambda:process.state()==QProcess.ProcessState.Running)
            ticks=[]; timer=QTimer(); timer.timeout.connect(lambda:ticks.append(1)); timer.start(5)
            self.wait_until(lambda:len(ticks)>=3); timer.stop()
            self.ctx.set_enabled('weather',False)
            self.assertIsNone(self.ctx.process); self.assertFalse(self.ctx.pending)
            self.wait_until(lambda:sip.isdeleted(process) or process.state()==QProcess.ProcessState.NotRunning)
        self.assertIsNone(self.store.preference('context_weather_cache',None))

    def test_worker_timeout_and_shutdown_cancel_without_notifications(self):
        self.ctx.enabled.update(greeting=False,weather=True); self.ctx.start()
        worker=Path(self.tmp.name)/'yun_jin_weather.py'; worker.write_text('import time\ntime.sleep(60)')
        with patch.object(context_module,'BASE',Path(self.tmp.name)),patch.object(self.pet.speech,'report') as report:
            self.ctx.request_weather(); self.wait_until(lambda:self.ctx.process.state()==QProcess.ProcessState.Running)
            self.ctx.timeout.start(10); self.wait_until(lambda:self.ctx.process is None)
            self.ctx.shutdown(); self.ctx.poll(); self.ctx.dispatch(); report.assert_not_called()
        self.speak.assert_not_called()

    def test_ambient_speech_job_language_and_manual_priority(self):
        self.speech_patch.stop(); self.ctx.enabled.update(greeting=True,weather=True)
        self.ctx.started=True; speech=self.pet.speech
        player,output=Mock(),Mock(); speech.player=player; speech.output=output
        process=Mock()
        with patch('yun_jin_speech.QProcess',return_value=process):
            self.assertTrue(speech.speak('早上好！',category='ambient',language='zh-CN',tag={'kind':'greeting'}))
            callback=process.started.connect.call_args.args[0]; callback()
            job=json.loads(process.write.call_args.args[0])
            self.assertEqual(job['language'],'zh-CN'); self.assertTrue(job['voice'].startswith('zh-CN-'))
            self.assertEqual(speech.pref('language','it'),'it')
            self.assertTrue(speech.speak('Promemoria',category='reminder'))
            self.assertEqual(speech.category,'reminder'); self.assertTrue(process.kill.called)
        speech.process=None;speech.busy=False;speech.timeout.stop()

    def test_ambient_failures_quiet_mode_and_user_activity_never_report(self):
        self.speech_patch.stop(); self.ctx.started=True; speech=self.pet.speech
        speech.player=Mock();speech.output=Mock()
        notices=[];speech.status_changed.connect(notices.append)
        self.pet.sound.quiet_until=time.time()+300
        self.assertFalse(speech.speak('你好',category='ambient',language='zh-CN',tag={'kind':'greeting'}))
        self.pet.sound.quiet_until=0
        self.pet.call_later()
        self.assertFalse(speech.speak('你好',category='ambient',language='zh-CN',tag={'kind':'greeting'}))
        self.pet.cancel();self.pet.idle()
        speech.category='ambient';speech.current_tag={'kind':'greeting'};speech.busy=True
        process=Mock();process.readAllStandardOutput.return_value=b'{"ok":false,"error":"Offline"}'
        speech.process=process;speech.generated(process,1)
        self.assertFalse(speech.busy);self.assertEqual(notices,[])
        self.assertNotEqual(self.pet.state,'voice_wait')

    def test_speech_result_discarded_when_user_started_following(self):
        self.speech_patch.stop(); self.ctx.started=True;speech=self.pet.speech
        speech.player=Mock();speech.output=Mock();speech.category='ambient'
        audio=speech.cache/'test.mp3';audio.write_bytes(b'test')
        process=Mock();process.readAllStandardOutput.return_value=json.dumps({'ok':True,'path':str(audio)}).encode()
        speech.process=process;speech.busy=True;speech.current_tag={'kind':'greeting'}
        self.pet.call_later();speech.generated(process,0)
        speech.player.play.assert_not_called();self.assertEqual(self.pet.state,'follow_pending')
        self.assertFalse(speech.busy)

    def test_no_generic_voice_animation_for_ambient_comments(self):
        self.pet.speech.category='ambient'
        self.pet.sequence([('celebrate16',1)])
        self.pet.voice_animation(True);self.pet.speech_status_animation()
        self.assertEqual(self.pet.animation,'celebrate16');self.assertEqual(self.pet.state,'action')


if __name__=='__main__': unittest.main(verbosity=2)
