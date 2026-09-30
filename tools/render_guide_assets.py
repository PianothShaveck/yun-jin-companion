#!/usr/bin/env python3
"""Render the guide's final screenshots using temporary, fictional data."""
import os
import sys
import tempfile
import time
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
        note=store.save_note('Studio','Scale: 80 → 120 BPM\n\nQuattro ripetizioni per ogni tempo.\nRivedere il passaggio finale.','',None)
        store.save_note('Idee','Una passeggiata e un po’ di musica.','',None)
        store.add_reminder('Fai una pausa',time.time()-60)
        pet=Companion(store);pet.timer.stop();pet.reminder_timer.stop();pet.checkpoint_timer.stop()
        pet.open_panel();panel=pet.panel;panel.load_note(note);panel.status.hide()
        pet.stopwatch.accumulated=125.8
        pet.stopwatch.laps=[{'total':42.1,'split':42.1},{'total':83.7,'split':41.6},{'total':125.8,'split':42.1}]
        panel.music.refresh_watch()
        for name,page,sub in [('appunti',0,None),('voce',3,None),('impostazioni',2,None),('metronomo',5,0),('cronometro',5,1)]:
            panel.resize(990,690) if name in ('appunti','voce','impostazioni') else panel.resize(760,550)
            panel.show_page(page,sub)
            if name=='metronomo':panel.music.ramp.setChecked(True)
            app.processEvents();panel.grab().save(str(out/(name+'.png')))
        context_card=panel.context_checks['greeting'].parentWidget()
        panel.show_page(2);app.processEvents();context_card.grab().save(str(out/'orario-meteo.png'))
        from yun_jin_updates_ui import UpdateDialog
        pet.updates.release=dict(version='1.3.0',notes='## Novità\n\n- Miglioramenti alle funzioni.\n- Correzioni e ottimizzazioni.',automatic=True,url='https://github.com/PianothShaveck/yun-jin-companion/releases')
        dialog=UpdateDialog(pet.updates);dialog.refresh();dialog.show();app.processEvents()
        dialog.grab().save(str(out/'aggiornamento.png'));dialog.hide();dialog.deleteLater()
        panel.show_page(4);app.processEvents()
        panel.tabs.widget(4).findChild(QFrame,'hero').grab().save(str(out/'focus.png'))
        dialog=ReminderDialog(pet);dialog.title.setText('Fai una pausa');dialog.quick(25);dialog.show()
        app.processEvents();dialog.grab().save(str(out/'promemoria.png'));dialog.hide()
        pet.card.present(store.mark_due());app.processEvents();pet.card.grab().save(str(out/'avviso.png'));pet.card.hide()
        for name in ('conduct16','stopwatch16'):
            row=ANIMATIONS[name][0];pet.sheet.frames[row,6].save(str(out/(name+'.png')))
        pet.close();store.close()
    print(out)

if __name__=='__main__':main()
