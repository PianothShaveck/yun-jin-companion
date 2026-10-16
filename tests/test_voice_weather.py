"""Master voice switch and weather variety, without network or audio hardware."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import random
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtCore import QObject,QProcess,pyqtSignal
from PyQt6.QtWidgets import QApplication
from PyQt6.QtMultimedia import QMediaPlayer
from yun_jin_data import Store
from yun_jin_app import Companion
from yun_jin_speech import Speech
from yun_jin_weather import detailed_weather_kind,fetch_weather
from yun_jin_forecast import condition
from yun_jin_weather_lines import LANGUAGES,LINES,line_pool,choose_weather_line
from yun_jin_greeting_lines import LINES as GREETING_LINES, line_pool as greeting_pool, choose_greeting_line

app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class GreetingVarietyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)

    def tearDown(self):
        self.store.close();self.tmp.cleanup()

    def test_twenty_distinct_short_greetings_per_period_and_language(self):
        self.assertEqual(set(GREETING_LINES),{'morning','afternoon','evening','night'})
        for period,rows in GREETING_LINES.items():
            self.assertTrue(all(len(row)==3 for row in rows))
            for language in LANGUAGES:
                pool=greeting_pool(period,language)
                self.assertEqual(len(pool),20);self.assertEqual(len(set(pool)),20)
                self.assertTrue(all(8<=len(line)<=140 for line in pool),(period,language))
                if language=='zh-CN':
                    self.assertTrue(all(any('\u3400'<=c<='\u9fff' for c in line) for line in pool))
        self.assertEqual(greeting_pool('night','unknown'),greeting_pool('night','it'))

    def test_full_rotation_survives_restarts_without_consecutive_repeats(self):
        rng=random.Random(151)
        first=[choose_greeting_line(self.store,'morning','it',rng) for _ in range(7)]
        self.store.close();self.store=Store(self.tmp.name)
        first += [choose_greeting_line(self.store,'morning','it',rng) for _ in range(13)]
        second=[choose_greeting_line(self.store,'morning','it',rng) for _ in range(20)]
        self.assertEqual(set(first),set(greeting_pool('morning','it')))
        self.assertEqual(set(second),set(first));self.assertNotEqual(first[-1],second[0])

    def test_language_period_histories_are_independent_and_bounded(self):
        for language in LANGUAGES:
            for period in GREETING_LINES:
                for _ in range(3):
                    self.assertIn(choose_greeting_line(self.store,period,language),greeting_pool(period,language))
        state=self.store.preference('context_greeting_phrases',{})
        self.assertEqual(len(state),12)
        self.assertTrue(all(len(value['remaining'])==17 for value in state.values()))
        self.assertLess(len(json.dumps(state)),2000)
        self.assertIn(choose_greeting_line(self.store,'morning','unknown'),greeting_pool('morning','it'))
        self.assertEqual(len(self.store.preference('context_greeting_phrases',{})),12)

    def test_bad_history_is_repaired_without_retaining_unknown_data(self):
        for broken in (None,17,{'it/morning':{'last':1,'remaining':[1]*10000}},
                       {'it/morning':{'last':False,'remaining':['x']},'obsolete':'x'*10000},
                       {'it/morning':{'last':1,'remaining':[1,2]}},
                       {'en/night':{'last':1,'remaining':[2,3],'junk':'x'*10000}}):
            self.store.set_preference('context_greeting_phrases',broken)
            self.assertIn(choose_greeting_line(self.store,'morning','it'),greeting_pool('morning','it'))
            self.assertLess(len(json.dumps(self.store.preference('context_greeting_phrases',{}))),350)

    def test_greeting_corpus_is_lazy_and_does_not_import_weather_corpus(self):
        code=("import sys;sys.path.insert(0,sys.argv[1]);import yun_jin_context;"
              "assert 'yun_jin_greeting_lines' not in sys.modules;"
              "import yun_jin_greeting_lines;assert 'yun_jin_weather_lines' not in sys.modules")
        subprocess.run([sys.executable,'-c',code,str(Path(__file__).resolve().parents[1]/'app')],check=True,timeout=10)


class WeatherVarietyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)

    def tearDown(self):
        self.store.close();self.tmp.cleanup()

    def test_fifteen_distinct_localized_lines_for_every_existing_weather_picture(self):
        assets=Path(__file__).resolve().parents[1]/'app'/'assets'/'weather'
        self.assertEqual(set(LINES),{p.stem for p in assets.glob('*.webp')})
        self.assertEqual(len(LINES),16)
        for kind in LINES:
            self.assertTrue(all(len(row)==3 for row in LINES[kind]),kind)
            for language in LANGUAGES:
                lines=line_pool(kind,language)
                self.assertEqual(len(lines),15,(kind,language))
                self.assertEqual(len(set(lines)),15,(kind,language))
                self.assertTrue(all(10<=len(line)<=180 for line in lines),(kind,language))
                if language=='zh-CN':
                    self.assertTrue(all(any('\u3400'<=c<='\u9fff' for c in line) for line in lines))
        self.assertEqual(sum(len(line_pool(k,lang)) for k in LINES for lang in LANGUAGES),720)

    def test_rotation_exhausts_pool_before_repeating_and_survives_restart(self):
        rng=random.Random(2026)
        first=[choose_weather_line(self.store,'rain','it',rng) for _ in range(6)]
        self.store.close();self.store=Store(self.tmp.name)
        rest=[choose_weather_line(self.store,'rain','it',rng) for _ in range(9)]
        self.assertEqual(len(set(first+rest)),15)
        second=[choose_weather_line(self.store,'rain','it',rng) for _ in range(15)]
        self.assertEqual(set(second),set(first+rest))
        self.assertNotEqual(rest[-1],second[0])

    def test_each_language_and_weather_have_independent_bounded_history(self):
        rng=random.Random(7)
        for language in LANGUAGES:
            for kind in LINES:
                for _ in range(3):
                    self.assertIn(choose_weather_line(self.store,kind,language,rng),line_pool(kind,language))
        state=self.store.preference('context_weather_phrases',{})
        self.assertEqual(len(state),48)
        self.assertTrue(all(len(v['remaining'])==12 for v in state.values()))
        self.assertLess(len(json.dumps(state)),5000)
        self.assertIn(choose_weather_line(self.store,'storm','unknown',rng),line_pool('thunderstorm','it'))

    def test_corrupt_rotation_history_is_repaired_and_unrecognized_keys_removed(self):
        for broken in (None,17,{'it/rain':{'last':3,'remaining':[3]*10000}},
                       {'it/rain':{'last':False,'remaining':['x']},'en/snow':{'last':0,'remaining':[1,2],'junk':'x'*10000},'obsolete':'x'*10000}):
            self.store.set_preference('context_weather_phrases',broken)
            self.assertIn(choose_weather_line(self.store,'rain','it'),line_pool('rain','it'))
            self.assertLess(len(json.dumps(self.store.preference('context_weather_phrases',{}))),300)

    def test_corpus_is_not_imported_by_context_until_a_weather_phrase_is_needed(self):
        code="import sys;sys.path.insert(0,sys.argv[1]);import yun_jin_context;assert 'yun_jin_weather_lines' not in sys.modules"
        result=subprocess.run([sys.executable,'-c',code,str(Path(__file__).resolve().parents[1]/'app')],
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_all_sixteen_classifications_match_forecast_and_current_observations(self):
        fixtures=[(0,1,None,None,None,'sun'),(0,0,None,None,None,'clear_night'),
                  (2,1,None,None,None,'partly_cloudy'),(2,0,None,None,None,'partly_cloudy_night'),
                  (3,1,None,None,None,'cloud'),(45,1,None,None,None,'fog'),
                  (51,1,None,None,None,'drizzle'),(61,1,None,None,None,'rain'),
                  (65,1,None,None,None,'heavy_rain'),(66,1,None,None,None,'freezing_rain'),
                  (61,1,1,1,None,'sleet'),(71,1,None,None,None,'snow'),
                  (75,1,None,None,None,'heavy_snow'),(95,1,None,None,None,'thunderstorm'),
                  (96,1,None,None,None,'storm_hail'),(0,1,None,None,55,'wind')]
        for code,day,rain,snow,wind,expected in fixtures:
            with self.subTest(expected=expected):
                self.assertEqual(detailed_weather_kind(code,day,rain,snow,wind),expected)
                row=dict(weather_code=code,is_day=day,rain=rain,snowfall=snow,wind_speed_10m=wind,time=1000)
                self.assertEqual(condition(row)[1],expected)
                got=fetch_weather({'city':'Test','latitude':38.,'longitude':15.},1000,
                                  Mock(return_value={'current':row}))
                self.assertEqual(got['kind'],expected)
        for code in (True,'95',999,None):self.assertIsNone(detailed_weather_kind(code,1))
        self.assertEqual(detailed_weather_kind(0,1,None,None,'windy'),'sun')


class SilentCaptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.store.set_preference('updates_enabled',False)
        self.pet=Companion(self.store)
        for timer in (self.pet.timer,self.pet.reminder_timer,self.pet.checkpoint_timer,self.pet.context.timer):timer.stop()
        self.pet.cancel();self.pet.idle();self.pet.show();app.processEvents()
        self.speech=self.pet.speech
        self.captions=[];self.speech.caption_changed.connect(self.captions.append)

    def tearDown(self):
        self.speech.process=None
        self.pet.close();self.pet.deleteLater();app.processEvents()
        self.store.close();self.tmp.cleanup()

    def test_muted_manual_preview_reminder_calendar_and_alarm_are_text_only(self):
        self.speech.set_enabled(False)
        with patch.object(self.speech,'ensure_player') as player,patch('yun_jin_speech.QProcess') as process:
            for category in ('manual','reminder','calendar','alarm'):
                self.speech.stop(False)
                self.assertTrue(self.speech.speak('Un avviso importante.',category=category,preview=True))
                self.assertEqual(self.pet.bubble.text,'Un avviso importante.')
                self.assertTrue(self.speech.busy);self.assertTrue(self.speech.caption_timer.isActive())
                self.assertFalse(self.speech.timeout.isActive());self.assertFalse(self.speech.cached_timer.isActive())
                self.speech.advance_silent_caption()
                self.assertFalse(self.speech.busy);self.assertFalse(self.speech.caption_timer.isActive())
                self.assertEqual(self.pet.bubble.text,'')
            player.assert_not_called();process.assert_not_called()
        self.assertIsNone(self.speech.player)

    def test_switch_persists_and_old_opt_out_does_not_become_master_mute(self):
        self.store.set_preference('tts_enabled',False)
        self.assertTrue(self.speech.enabled)
        changes=[];self.speech.enabled_changed.connect(changes.append)
        self.speech.set_enabled(False);self.speech.set_enabled(False)
        self.speech.set_pref('volume',90);self.speech.set_pref('auto_reminders',True)
        self.assertFalse(self.speech.enabled)
        again=Speech(self.pet)
        self.assertFalse(again.enabled);again.shutdown();again.deleteLater()
        self.speech.set_pref('master_enabled',True)
        self.assertEqual(changes,[False,True])

    def test_muting_current_playback_keeps_current_page_and_never_resumes_audio(self):
        self.speech.player=Mock();self.speech.output=Mock()
        self.speech.player.duration.return_value=10000;self.speech.player.position.return_value=0
        process=Mock()
        with patch('yun_jin_speech.QProcess',return_value=process):
            self.speech.speak('Una frase da leggere con calma. '*35)
        self.speech.playback_state(QMediaPlayer.PlaybackState.PlayingState)
        self.speech.update_caption(6000)
        index=self.speech.caption_index;page=self.pet.bubble.text;self.assertGreater(index,0)
        self.captions.clear();self.speech.set_enabled(False)
        self.assertEqual(self.speech.caption_index,index);self.assertEqual(self.pet.bubble.text,page)
        self.assertEqual(self.captions,[],'Muting must not briefly erase or rewind the current page')
        process.kill.assert_called_once();self.assertIsNone(self.speech.process)
        self.speech.playback_state(QMediaPlayer.PlaybackState.StoppedState)
        self.speech.media_status(QMediaPlayer.MediaStatus.EndOfMedia)
        self.speech.playback_error()
        self.assertEqual(self.pet.bubble.text,page)
        self.speech.set_enabled(True)
        self.speech.player.play.assert_not_called()
        self.assertTrue(self.speech.silent_caption)
        self.speech.advance_silent_caption();self.assertEqual(self.speech.caption_index,index+1)
        while self.speech.busy:self.speech.advance_silent_caption()
        self.assertFalse(self.speech.caption_timer.isActive())

    def test_muting_preparation_cancels_cached_or_remote_work_without_a_stale_result(self):
        self.speech.player=Mock();self.speech.output=Mock();process=Mock()
        with patch('yun_jin_speech.QProcess',return_value=process):self.speech.speak('Prima frase.')
        self.speech.set_enabled(False)
        self.assertEqual(self.pet.bubble.text,'Prima frase.')
        self.speech.speak('Frase nuova.')
        self.speech.generated(process,0);self.speech.play_cached()
        self.assertEqual(self.pet.bubble.text,'Frase nuova.')
        self.speech.player.play.assert_not_called()

    def test_silent_pages_keep_all_text_and_shutdown_cancels_timer(self):
        self.speech.set_enabled(False)
        text='今天我们慢慢学习，记得休息。'*25
        self.assertTrue(self.speech.speak(text))
        while self.speech.busy:self.speech.advance_silent_caption()
        self.assertEqual(''.join(self.captions),text)
        self.assertFalse(self.speech.caption_timer.isActive())
        self.speech.speak('Ultimo avviso.');self.speech.shutdown()
        before=list(self.captions);self.speech.advance_silent_caption();app.processEvents()
        self.assertEqual(self.captions,before);self.assertFalse(self.speech.caption_timer.isActive())
        self.assertFalse(self.speech.speak('Non deve comparire.'))

    def test_replacement_and_stop_do_not_leave_a_silent_caption_running(self):
        self.speech.set_enabled(False)
        self.speech.speak('Frase vecchia. '*40)
        self.speech.speak('Frase nuova.')
        self.assertEqual(self.speech.caption_index,0);self.assertEqual(self.pet.bubble.text,'Frase nuova.')
        self.speech.stop(False);self.speech.advance_silent_caption()
        self.assertEqual(self.pet.bubble.text,'');self.assertFalse(self.speech.busy)
        self.assertFalse(self.speech.caption_timer.isActive())

    def test_muted_alerts_and_reminders_leave_metronome_running(self):
        self.speech.set_enabled(False)
        self.pet.metronome.running=True;self.speech.set_pref('auto_reminders',False)
        self.pet.sound.quiet_until=time.time()+300
        with patch.object(self.pet.metronome,'stop') as stop:
            for category in ('reminder','calendar','alarm'):
                self.speech.stop(False)
                self.assertTrue(self.speech.speak('Avviso.',category=category))
                self.assertEqual(self.pet.bubble.text,'Avviso.');stop.assert_not_called()
        self.pet.metronome.running=False

    def test_muted_weather_still_selects_voice_language_and_animates_once(self):
        self.speech.set_enabled(False);self.speech.set_pref('language','zh-CN')
        ctx=self.pet.context;ctx.started=True;ctx.enabled.update(weather=True,greeting=False)
        ctx.last_reaction=-1e10;ctx.pending={'weather':(ctx.monotonic()+300,'heavy_rain')}
        with patch('yun_jin_speech.QProcess') as process,patch.object(self.speech,'ensure_player') as player:
            ctx.dispatch()
            self.assertIn(self.pet.bubble.text,line_pool('heavy_rain','zh-CN'))
            self.assertEqual(self.pet.animation,'rain16')
            serial=self.pet.action_serial
            ctx.dispatch();self.speech.animate_ambient();self.speech.advance_silent_caption()
            self.assertEqual(self.pet.action_serial,serial)
            process.assert_not_called();player.assert_not_called()
        # Cadence is unchanged: another immediate weather dispatch is held.
        ctx.pending={'weather':(ctx.monotonic()+300,'sun')}
        ctx.dispatch();self.assertIn('weather',ctx.pending)

    def test_muted_ambient_respects_manual_action_and_focus(self):
        self.speech.set_enabled(False);self.pet.context.started=True
        tag={'kind':'weather','serial':self.pet.action_serial,'animation':('rain16','wait')}
        self.pet.sequence([('jump',1)])
        self.assertFalse(self.speech.speak('Piove.',category='ambient',tag=tag))
        self.assertEqual(self.pet.animation,'jump');self.assertEqual(self.pet.bubble.text,'')
        self.pet.cancel();self.pet.idle()
        with patch.object(self.pet,'focus_active',return_value=True):
            self.assertFalse(self.speech.speak('Piove.',category='ambient',tag={'kind':'weather'}))

    def test_synchronous_failed_process_start_does_not_arm_a_late_timeout(self):
        class FailingProcess(QObject):
            started=pyqtSignal();finished=pyqtSignal(int,int);errorOccurred=pyqtSignal(object)
            def setProgram(self,*args):pass
            def setArguments(self,*args):pass
            def start(self):self.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
        self.speech.player=Mock();self.speech.output=Mock()
        with patch('yun_jin_speech.QProcess',FailingProcess):
            # The controller compares the actual Qt enum even while QProcess is patched.
            FailingProcess.ProcessError=QProcess.ProcessError
            self.speech.speak('Prova.')
        self.assertIsNone(self.speech.process);self.assertFalse(self.speech.busy)
        self.assertFalse(self.speech.timeout.isActive())


if __name__=='__main__':unittest.main(verbosity=2)
