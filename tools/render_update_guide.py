#!/usr/bin/env python3
"""Render settings and the real update dialog with clearly marked example notes."""
import os,sys,tempfile
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['QT_SCALE_FACTOR']='2'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from PyQt6.QtWidgets import QApplication
from yun_jin_app import Companion
from yun_jin_data import Store
from yun_jin_updates_ui import UpdateDialog
app=QApplication([]);app.setStyle('Fusion')
with tempfile.TemporaryDirectory() as tmp:
 store=Store(tmp);pet=Companion(store)
 for timer in (pet.timer,pet.reminder_timer,pet.checkpoint_timer,pet.updates.initial,pet.updates.timer):timer.stop()
 pet.open_panel(tab=2);pet.panel.resize(810,630);app.processEvents()
 pet.panel.grab().save(str(ROOT/'docs/art/impostazioni-1.1.png'))
 pet.updates.release=dict(version='1.2.0',notes='## Note di rilascio di esempio\n\nLe novità della release saranno mostrate qui, esattamente come pubblicate su GitHub.\n\n- Nuove funzioni e miglioramenti.\n- Correzioni dei problemi segnalati.\n- Eventuali indicazioni per aggiornare.\n\nPuoi aggiornare, rimandare oppure saltare soltanto questa versione.',
  url='https://github.com/PianothShaveck/yun-jin-companion/releases',automatic=True)
 dialog=UpdateDialog(pet.updates);dialog.refresh();dialog.show();app.processEvents()
 dialog.grab().save(str(ROOT/'docs/art/aggiornamento-1.1.png'));dialog.hide()
 pet.close();store.close()
