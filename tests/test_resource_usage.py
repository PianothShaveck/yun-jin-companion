"""Deterministic resource bounds and display invariants, independent of machine speed."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
from yun_jin_app import Companion
from yun_jin_core import SpriteSheet, BASE, ANIMATIONS
from yun_jin_data import Store
from yun_jin_music import format_elapsed
app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.store.set_preference('updates_enabled',False)
        self.pet=Companion(self.store)
        for timer in (self.pet.timer,self.pet.reminder_timer,self.pet.checkpoint_timer):timer.stop()
        self.pet.cancel();self.pet.idle();self.pet.allow_gaze=False

    def tearDown(self):
        self.pet.close();self.pet.deleteLater();app.processEvents();self.store.close();self.tmp.cleanup()

    def test_unused_animations_not_decoded_and_cache_bounded_after_every_clip(self):
        frames=self.pet.sheet.frames
        self.assertEqual(len(frames.cache),0)
        original=frames[0,5].toImage()
        for _ in range(3):
            for name,(row,count,_) in ANIMATIONS.items():
                for frame in range(count):self.assertFalse(frames[row,frame].isNull())
                self.assertLessEqual(len(frames.cache),2)
        self.assertEqual(frames[0,5].toImage(),original)
        size=sum(p.width()*p.height()*4 for p in frames.original.values())
        size+=sum(p.width()*p.height()*4 for clip in frames.cache.values() for p in clip)
        self.assertLess(size,16*1024*1024)

    def test_every_animation_uses_the_lossless_cache_without_runtime_alignment(self):
        sheet=self.pet.sheet
        with patch.object(sheet,'align_sequence',side_effect=AssertionError('Cache unavailable')), \
             patch.object(sheet,'align_frame',side_effect=AssertionError('Cache unavailable')):
            for spec in json.loads((BASE/'assets/animations.json').read_text())['animations']:
                frames=sheet.load_clip(BASE/'assets'/spec['file'],spec)
                self.assertEqual(len(frames),spec['count'])
                self.assertTrue(all(not frame.isNull() for frame in frames),spec['name'])

    def test_unused_audio_allocates_no_players_and_effects_are_reused(self):
        sound=self.pet.sound;speech=self.pet.speech
        self.assertEqual(sound.effects,{})
        self.assertFalse(sound.prepared);self.assertIsNone(speech.player)
        with patch('PyQt6.QtMultimedia.QSoundEffect') as effects, \
             patch('PyQt6.QtMultimedia.QMediaDevices.audioOutputs',return_value=[object()]):
            sound.enabled=False;sound.play('reminder');effects.assert_not_called()
            sound.play('reminder',preview=True);sound.play('reminder',preview=True)
            effects.assert_called_once_with(sound)
            self.assertEqual(set(sound.effects),{'reminder'})
            sound.play('saved',preview=True);self.assertEqual(effects.call_count,2)
        with patch('PyQt6.QtMultimedia.QMediaPlayer') as player, \
             patch('PyQt6.QtMultimedia.QAudioOutput'):
            self.assertTrue(speech.ensure_player());self.assertTrue(speech.ensure_player())
            player.assert_called_once_with(speech)

    def test_checkpoint_timer_runs_only_with_stopwatch_without_reset_on_lap(self):
        p=self.pet
        self.assertFalse(p.checkpoint_timer.isActive())
        p.stopwatch.start();self.assertTrue(p.checkpoint_timer.isActive())
        with patch.object(p.checkpoint_timer,'start') as start:
            p.stopwatch.lap();start.assert_not_called()
        p.stopwatch.pause();self.assertFalse(p.checkpoint_timer.isActive())
        self.assertEqual(len(self.store.preference('stopwatch',{})['laps']),1)
        p.stopwatch.start();self.assertTrue(p.checkpoint_timer.isActive())
        p.stopwatch.reset();self.assertFalse(p.checkpoint_timer.isActive())

    def test_baked_frames_use_same_dimensions_and_fallback_without_cache(self):
        sheet=self.pet.sheet;spec=json.loads((BASE/'assets/animations.json').read_text())['animations'][0]
        path=BASE/'assets'/spec['file']
        baked=sheet.load_clip(path,spec)
        with patch('yun_jin_core.animation_fingerprint',return_value='missing-cache'):
            dynamic=sheet.load_clip(path,spec)
        self.assertEqual(len(baked),len(dynamic))
        self.assertEqual([p.size() for p in baked],[p.size() for p in dynamic])
        # Exact byte equality is also verified when baking on the release host.
        # Qt raster backends on different CPU architectures may round edges.
        for a,b in zip(baked,dynamic):
            aa,bb=a.toImage(),b.toImage()
            self.assertEqual(aa.pixelColor(80,80),bb.pixelColor(80,80))

    def test_idle_frame_timing_unchanged_but_no_duplicate_repaints(self):
        p=self.pet;p.play('idle');p._painted_frame=p.visible_frame()
        with patch.object(p,'update') as update:
            for _ in range(20):p.animate(.01)
            self.assertEqual(p.frame,0);update.assert_not_called()
            p.animate(.29);self.assertEqual(p.frame,1);update.assert_called_once()
            p._painted_frame=p.visible_frame();update.reset_mock()
            p.animate(.05);self.assertEqual(p.frame,1);update.assert_not_called()
            p.animate(.08);self.assertEqual(p.frame,2);update.assert_called_once()

    def test_gaze_blinks_invalidate_and_unchanged_badge_does_not(self):
        p=self.pet;p.look=0;p._painted_frame=(9,0)
        with patch.object(p,'update') as update:
            p.blink_until=time.monotonic()+10;p.update_frame();update.assert_called_once()
            p._painted_frame=(0,1);update.reset_mock();p.update_frame();update.assert_not_called()
            p.blink_until=0;p.update_frame();update.assert_called_once()
        with patch.object(p,'update') as update:
            p.poll_reminders();p.poll_reminders();update.assert_not_called()

    def test_stopwatch_redraw_timer_only_when_visible_and_running(self):
        p=self.pet;p.open_panel(tab=5,subtab=1);app.processEvents();m=p.panel.music
        self.assertFalse(m.clock_timer.isActive())
        p.stopwatch.start();app.processEvents();self.assertTrue(m.clock_timer.isActive())
        p.panel.show_page(0);app.processEvents();self.assertFalse(m.clock_timer.isActive())
        p.panel.show_page(5,1);app.processEvents();self.assertTrue(m.clock_timer.isActive())
        p.panel.hide();app.processEvents();self.assertFalse(m.clock_timer.isActive())
        with patch('yun_jin_music.time.monotonic',return_value=12345.):
            p.stopwatch.started=12328.
            p.open_panel(tab=5,subtab=1);app.processEvents()
            self.assertEqual(m.clock.text(),format_elapsed(p.stopwatch.elapsed()))
            self.assertEqual(p.stopwatch.elapsed(),17.)
        p.stopwatch.pause();self.assertFalse(m.clock_timer.isActive())


if __name__=='__main__':unittest.main(verbosity=2)
