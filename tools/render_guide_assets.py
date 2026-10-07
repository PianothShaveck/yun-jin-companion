#!/usr/bin/env python3
"""Render the guide's final screenshots using temporary, fictional data."""
import os
import sys
import tempfile
import time
import math
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_SCALE_FACTOR']='2'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from PyQt6.QtWidgets import QApplication,QFrame
from yun_jin_app import Companion
from yun_jin_data import Store
from yun_jin_panel import ReminderDialog
from yun_jin_core import ANIMATIONS


def main():
    app=QApplication([]);app.setStyle('Fusion')
    out=ROOT/'docs'/'art';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='yun-jin-guide-') as directory:
        store=Store(directory)
        store.set_preference('updates_enabled',False)
        note=store.save_note('Studio','Scale: 80 → 120 BPM\n\nQuattro ripetizioni per ogni tempo.\nRivedere il passaggio finale.','',None)
        store.save_note('Idee','Una passeggiata e un po’ di musica.','',None)
        store.add_reminder('Fai una pausa',time.time()-60)
        pet=Companion(store);pet.timer.stop();pet.reminder_timer.stop();pet.checkpoint_timer.stop()
        pet.context.enabled={k:False for k in ('greeting','time','weather')}
        pet.open_panel();panel=pet.panel;panel.load_note(note);panel.status.hide()
        pet.stopwatch.accumulated=125.8
        pet.stopwatch.laps=[{'total':42.1,'split':42.1},{'total':83.7,'split':41.6},{'total':125.8,'split':42.1}]
        panel.music.refresh_watch()
        for name,page,sub in [('appunti',0,None),('voce',3,None),('metronomo',5,0),('cronometro',5,1)]:
            panel.resize(990,690) if name in ('appunti','voce','impostazioni') else panel.resize(760,550)
            panel.show_page(page,sub)
            if name=='metronomo':panel.music.ramp.setChecked(True)
            app.processEvents();panel.grab().save(str(out/(name+'.png')))
        pet.context.set_weather_location({'city':'Reggio Calabria','region':'Calabria','country':'Italia',
                                          'latitude':38.11047,'longitude':15.66129})
        context_card=panel.context_checks['greeting'].parentWidget()
        panel.show_page(2);app.processEvents();context_card.grab().save(str(out/'orario-meteo.png'))
        from yun_jin_updates_ui import UpdateDialog
        pet.updates.release=dict(version='1.4.0',notes='## Novità\n\n- Miglioramenti alle funzioni.\n- Correzioni e ottimizzazioni.',automatic=True,url='https://github.com/PianothShaveck/yun-jin-companion/releases')
        dialog=UpdateDialog(pet.updates);dialog.refresh();dialog.show();app.processEvents()
        dialog.grab().save(str(out/'aggiornamento.png'));dialog.hide();dialog.deleteLater()
        panel.show_page(4);app.processEvents()
        panel.tabs.widget(4).findChild(QFrame,'hero').grab().save(str(out/'focus.png'))
        dialog=ReminderDialog(pet);dialog.title.setText('Fai una pausa');dialog.quick(25);dialog.show()
        app.processEvents();dialog.grab().save(str(out/'promemoria.png'));dialog.hide()
        pet.card.present(store.mark_due());app.processEvents();pet.card.grab().save(str(out/'avviso.png'));pet.card.hide()
        for name in ('conduct16','stopwatch16'):
            row=ANIMATIONS[name][0];pet.sheet.frames[row,6].save(str(out/(name+'.png')))
        # Study screens use only fictional, local Chinese vocabulary.
        study=store.study;deck=study.save_deck('Cinese · parole quotidiane')
        for front,back in [('你好','nǐ hǎo · Ciao'),('谢谢','xièxie · Grazie'),('学习','xuéxí · Studiare'),('明天','míngtiān · Domani')]:
            study.save_note(deck,'basic',dict(front=front,back=back))
        study.save_note(deck,'cloze',dict(front='我{{c1::喜欢::xǐhuān}}学习中文。',back='Mi piace studiare il cinese.'))
        panel.study.refresh(deck);panel.resize(990,690);panel.show_page(6);app.processEvents()
        panel.grab().save(str(out/'studio.png'))
        from yun_jin_study_widgets import NoteEditor
        editor=NoteEditor(pet,deck,parent=panel);editor.kind.setCurrentIndex(1)
        editor.edits['front'].setPlainText('我{{c1::喜欢::xǐhuān}}学习中文。')
        editor.edits['back'].setPlainText('Mi piace studiare il cinese.');editor.show();app.processEvents()
        editor.grab().save(str(out/'carte.png'));editor.close();editor.deleteLater()
        from yun_jin_hotkeys import ShortcutDialog
        shortcuts=ShortcutDialog(pet,panel);shortcuts.show();app.processEvents()
        shortcuts.grab().save(str(out/'scorciatoie.png'));shortcuts.reject();shortcuts.deleteLater()
        # Illustrative seven-day forecast, never a network lookup or personal data.
        from yun_jin_forecast import fetch_forecast,HOURLY,DAILY,CURRENT
        now=time.time();start=int(now//86400)*86400
        hours={'time':[start+i*3600 for i in range(168)]}
        days={'time':[start+i*86400 for i in range(7)]}
        for key in HOURLY:hours[key]=[0]*168
        for i in range(168):
            hours['temperature_2m'][i]=round(22+4*math.sin((i%24-8)*math.pi/12),1)
            hours['apparent_temperature'][i]=hours['temperature_2m'][i]-1
            hours['is_day'][i]=int(6<=i%24<18);hours['precipitation_probability'][i]=10
            hours['wind_speed_10m'][i]=12;hours['wind_gusts_10m'][i]=20;hours['relative_humidity_2m'][i]=65
        for key in DAILY:days[key]=[0]*7
        for i,stamp in enumerate(days['time']):
            for key,value in dict(weather_code=[0,2,3,61,65,95,0][i],temperature_2m_min=18+i%2,
                temperature_2m_max=24+i%3,precipitation_probability_max=[5,10,25,80,90,85,0][i],
                sunrise=stamp+5*3600,sunset=stamp+16*3600,uv_index_max=4.2).items():days[key][i]=value
        current={key:hours[key][int((now-start)//3600)] for key in CURRENT}
        current.update(time=int(now//900)*900,temperature_2m=23.4,apparent_temperature=23,is_day=1)
        result=fetch_forecast(pet.context.weather_location,now,lambda _:dict(timezone='Europe/Rome',
            utc_offset_seconds=7200,current=current,hourly=hours,daily=days))
        store.set_preference('weather_forecast_cache',result)
        panel.resize(990,850);panel.show_page(7);app.processEvents();app.processEvents()
        panel.grab().save(str(out/'meteo.png'))
        pet.close();store.close()
    print(out)

if __name__=='__main__':main()
