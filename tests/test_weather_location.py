"""Manual weather location, cache isolation and cancellable city searches."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from urllib.parse import urlparse,parse_qs
from unittest.mock import Mock,patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6 import sip
from PyQt6.QtCore import Qt,QEventLoop,QTimer,QProcess
from PyQt6.QtWidgets import QApplication,QDialog
from yun_jin_app import Companion
from yun_jin_context import Context
from yun_jin_data import Store
from yun_jin_weather import fetch_weather,search_cities,selected_location
from yun_jin_weather_ui import CityDialog,WeatherLocationRow
import yun_jin_weather_ui as weather_ui

app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
CITY={'city':'Reggio Calabria','region':'Calabria','country':'Italia','latitude':38.11047,'longitude':15.66129}
OTHER=dict(CITY,city='Milano',region='Lombardia',latitude=45.46427,longitude=9.18951)


class LocationDataTests(unittest.TestCase):
    def test_manual_location_never_uses_ip_even_after_many_days(self):
        now=time.time();get=Mock(return_value={'current':{'weather_code':61,'is_day':1,'time':now}})
        result=fetch_weather(dict(CITY,checked=now-30*86400),now,get)
        self.assertEqual(result['location']['source'],'manual');self.assertEqual(result['kind'],'rain')
        get.assert_called_once()
        query=parse_qs(urlparse(get.call_args.args[0]).query)
        self.assertEqual(query['latitude'],[str(CITY['latitude'])])
        self.assertEqual(query['longitude'],[str(CITY['longitude'])])
        get.reset_mock()
        self.assertIsNone(fetch_weather({'city':'Invalid'},now,get));get.assert_not_called()

    def test_city_search_preserves_homonyms_and_encodes_unicode(self):
        get=Mock(return_value={'results':[
            {'name':'西安','latitude':34.26,'longitude':108.95,'admin1':'陕西','country':'中国'},
            {'name':'西安','latitude':45.1,'longitude':121.1,'admin1':'另一地区','country':'中国'},
            {'name':'西安','latitude':34.26,'longitude':108.95,'admin1':'陕西','country':'中国'},
            {'name':'Invalid','latitude':float('nan'),'longitude':0},None]})
        results=search_cities('  西安  ',get)
        self.assertEqual(len(results),2);self.assertEqual(results[0]['region'],'陕西')
        query=parse_qs(urlparse(get.call_args.args[0]).query)
        self.assertEqual(query['name'],['西安']);self.assertEqual(query['count'],['10'])
        self.assertEqual(query['language'],['it'])

    def test_invalid_and_oversized_searches_do_not_make_requests(self):
        get=Mock()
        for name in ('','A',' '*20,'x'*101,None):self.assertEqual(search_cities(name,get),[])
        get.assert_not_called()
        self.assertIsNone(selected_location(dict(CITY,latitude=True)))
        self.assertIsNone(selected_location(dict(CITY,city=' ')))
        with self.assertRaises(ValueError):search_cities('Reggio',Mock(return_value={'results':'bad'}))


class LocationUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root)
        self.store.set_preference('updates_enabled',False)
        self.pet=Companion(self.store);self.ctx=self.pet.context
        self.pet.timer.stop();self.pet.reminder_timer.stop();self.dialogs=[]

    def tearDown(self):
        for dialog in self.dialogs:dialog.reject();dialog.deleteLater()
        self.pet.close();self.pet.deleteLater();app.processEvents();self.store.close();self.tmp.cleanup()

    def result(self,city=CITY,source='manual'):
        now=time.time()
        return {'kind':'rain','checked':now,'observed':now,'location':dict(city,source=source,checked=now)}

    def wait(self,condition):
        end=time.monotonic()+5;loop=QEventLoop();timer=QTimer()
        timer.timeout.connect(lambda:loop.quit() if condition() or time.monotonic()>=end else None)
        timer.start(5)
        if not condition():loop.exec()
        timer.stop();self.assertTrue(condition(),'Timed out waiting for worker')

    def dialog(self):
        self.pet.open_panel(tab=2);dialog=CityDialog(self.pet,self.pet.panel)
        self.dialogs.append(dialog);return dialog

    def worker(self,body):
        (self.root/'yun_jin_weather.py').write_text(body,encoding='utf-8')
        return patch.object(weather_ui,'BASE',self.root)

    def test_location_change_clears_stale_cache_and_cancels_old_weather(self):
        old=Mock();self.ctx.process=old;self.ctx.started=True
        self.ctx.weather_result=self.result(OTHER,'ip');self.ctx.pending['weather']=(time.monotonic()+300,'sun')
        self.store.set_preference('context_weather_cache',self.ctx.weather_result)
        with patch.object(self.ctx,'request_weather') as request:
            self.ctx.set_weather_location(CITY);request.assert_called_once()
        old.kill.assert_called_once();self.assertIsNone(self.ctx.weather_result)
        self.assertNotIn('weather',self.ctx.pending)
        self.assertIsNone(self.store.preference('context_weather_cache',False))
        self.ctx.received(old,0,0);old.readAllStandardOutput.assert_not_called()
        self.assertFalse(self.ctx.valid_weather(self.result(OTHER,'manual')))
        self.assertFalse(self.ctx.valid_weather(self.result(CITY,'ip')))
        self.assertTrue(self.ctx.valid_weather(self.result()))

    def test_selected_city_survives_restart_and_old_ip_cache_is_removed(self):
        ip=dict(OTHER,source='ip',checked=time.time());self.store.set_preference('context_location_cache',ip)
        self.ctx.set_weather_location(CITY)
        process=Mock();process.readAllStandardOutput.return_value=json.dumps(self.result()).encode()
        self.ctx.process=process
        self.ctx.received(process,self.ctx.generation,0)
        reloaded=Context(self.pet)
        try:
            self.assertIsNone(self.store.preference('context_location_cache','missing'))
            self.assertEqual(reloaded.weather_location,CITY)
            self.assertTrue(reloaded.valid_weather(self.store.preference('context_weather_cache',None)))
        finally:reloaded.shutdown();reloaded.deleteLater()
        self.ctx.set_weather_location(None)
        self.assertIsNone(self.store.preference('context_weather_location','missing'))
        self.assertFalse(self.ctx.valid_weather(self.result()))
        self.assertFalse(self.ctx.valid_weather(self.result(OTHER,'ip')))

    def test_upgrade_without_selected_city_ignores_old_ip_weather_and_starts_no_worker(self):
        self.store.set_preference('context_location_cache',dict(OTHER,checked=time.time()))
        self.store.set_preference('context_weather_cache',self.result(OTHER,'ip'))
        reloaded=Context(self.pet)
        try:
            self.assertIsNone(self.store.preference('context_location_cache','missing'))
            self.assertIsNone(self.store.preference('context_weather_cache','missing'))
            reloaded.enabled.update(greeting=False,time=False)
            with patch('yun_jin_context.QProcess') as process:
                reloaded.start();reloaded.poll();reloaded.request_weather()
                reloaded.set_enabled('weather',False);reloaded.set_enabled('weather',True)
                reloaded.poll();process.assert_not_called()
            self.assertIsNone(reloaded.weather_location);self.assertIsNone(reloaded.weather_result)
        finally:reloaded.shutdown();reloaded.deleteLater()

    def test_disabled_weather_and_repeated_choice_make_no_requests(self):
        self.ctx.started=True;self.ctx.set_enabled('weather',False)
        with patch.object(self.ctx,'request_weather') as request:
            self.ctx.set_weather_location(CITY);self.ctx.set_weather_location(CITY);request.assert_not_called()
        with patch('yun_jin_context.QProcess') as process:
            self.ctx.enabled['weather']=True;self.ctx.request_weather()
            process.return_value.started.connect.call_args.args[0]()
            job=json.loads(process.return_value.write.call_args.args[0])
            self.assertEqual(job,{'location':CITY})
        self.ctx.process=None;self.ctx.timeout.stop()

    def test_search_is_explicit_and_selected_city_is_confirmed(self):
        dialog=self.dialog();self.assertIs(dialog.parentWidget(),self.pet.panel)
        dialog.query.setText('Reggio Calabria');self.assertIsNone(dialog.process)
        body='import json,sys\njob=json.load(sys.stdin)\nassert job["name"]=="Reggio Calabria"\nprint('+repr(json.dumps({'cities':[CITY,OTHER]}))+')'
        with self.worker(body):
            dialog.start_search();self.wait(lambda:dialog.process is None)
        self.assertEqual(dialog.results.count(),2);self.assertFalse(dialog.use.isEnabled())
        self.assertIsNone(self.ctx.weather_location)
        dialog.results.setCurrentRow(0);self.assertTrue(dialog.use.isEnabled())
        dialog.accept_selection();self.assertEqual(dialog.selection,CITY)
        self.assertEqual(dialog.result(),QDialog.DialogCode.Accepted)

    def test_edit_cancels_slow_search_without_blocking_gui_or_saving_city(self):
        dialog=self.dialog();dialog.query.setText('Reggio')
        with self.worker('import time\ntime.sleep(60)'):
            dialog.start_search();process=dialog.process
            self.wait(lambda:process.state()==QProcess.ProcessState.Running)
            ticks=[];QTimer.singleShot(0,lambda:ticks.append(True));self.wait(lambda:bool(ticks))
            dialog.query.setText('Milano');self.assertIsNone(dialog.process)
            self.wait(lambda:sip.isdeleted(process) or process.state()==QProcess.ProcessState.NotRunning)
        self.assertEqual(dialog.results.count(),0);self.assertIsNone(self.ctx.weather_location)

    def test_failure_empty_results_timeout_and_close_leave_settings_unchanged(self):
        self.ctx.set_weather_location(CITY)
        dialog=self.dialog();dialog.query.setText('Reggio')
        for raw,text in [('null','Ricerca non disponibile. Riprova.'),('{"cities":[]}','Nessuna città trovata.')]:
            with self.worker('print('+repr(raw)+')'):
                dialog.start_search();self.wait(lambda:dialog.process is None)
            self.assertEqual(dialog.status.text(),text)
        with self.worker('import time\ntime.sleep(60)'):
            dialog.start_search();dialog.timeout.start(10);self.wait(lambda:dialog.process is None)
            self.assertEqual(dialog.status.text(),'Ricerca non disponibile. Riprova.')
            dialog.start_search();process=dialog.process;dialog.reject()
            self.wait(lambda:sip.isdeleted(process) or process.state()==QProcess.ProcessState.NotRunning)
        self.assertEqual(self.ctx.weather_location,CITY)

    def test_location_row_requires_a_choice_and_cancel_preserves_it(self):
        row=WeatherLocationRow(self.pet,self.pet)
        try:
            self.assertEqual(row.choice.text(),'Scegli città…')
            self.ctx.set_weather_location(CITY)
            self.assertIn('Reggio Calabria',row.choice.text())
            with patch('yun_jin_weather_ui.exec_dialog',return_value=QDialog.DialogCode.Rejected):
                row.choose()
            self.assertEqual(self.ctx.weather_location,CITY)
            self.assertIn('Reggio Calabria',row.choice.text())
            self.pet.open_panel(tab=2);self.pet.panel.context_checks['weather'].setChecked(False)
            self.assertFalse(self.pet.panel.weather_location_row.isEnabled())
        finally:row.deleteLater()


if __name__=='__main__':unittest.main(verbosity=2)
