"""Reviewed animation boundaries and access through the compact menu."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtGui import QRegion
from PyQt6.QtWidgets import QApplication, QMenu
from yun_jin_app import Companion
from yun_jin_data import Store
from yun_jin_core import ANIMATIONS, ANIMATION_GROUPS, BASE
from yun_jin_context import WEATHER_REACTIONS, TIME_ANIMATIONS
app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
NEW = ('morning16', 'afternoon16', 'evening16', 'greeting16', 'yawn16', 'sun16', 'cloud16', 'rain16', 'snow16', 'applause16')


def model_metrics(pixmap):
    image = pixmap.toImage()
    alpha = [[image.pixelColor(x, y).alpha() for x in range(image.width())]
             for y in range(image.height())]
    points = [(x, y) for y, row in enumerate(alpha) for x, a in enumerate(row) if a > 80]
    top = min(y for x, y in points); bottom = max(y for x, y in points)+1
    height = bottom-top
    def width(low, high):
        xs = [x for x, y in points if top+round(low*height) <= y < top+round(high*height)]
        return max(xs)-min(xs)+1
    return dict(height=height, silhouette=width(0, 1), head=width(0, .28),
                skirt=width(.6, .8), boots=width(.86, 1),
                boot_area=sum(sum(row) for row in alpha[bottom-30:bottom])/255,
                toe_area=sum(sum(row) for row in alpha[bottom-14:bottom])/255)


class AnimationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.store = Store(self.tmp.name)
        self.store.set_preference('updates_enabled', False)
        self.pet = Companion(self.store)
        for timer in (self.pet.timer, self.pet.reminder_timer, self.pet.checkpoint_timer): timer.stop()
        self.pet.cancel(); self.pet.idle()

    def tearDown(self):
        self.pet.close(); self.pet.deleteLater(); app.processEvents()
        self.store.close(); self.tmp.cleanup()

    def test_every_new_frame_complete_with_consistent_standing_scale(self):
        for name in NEW:
            row, count, timing = ANIMATIONS[name]
            self.assertEqual(count, 16)
            self.assertGreaterEqual(min(timing), .2)
            for i in range(count):
                pic = self.pet.sheet.frames[row, i]
                box = QRegion(pic.mask()).boundingRect()
                self.assertGreaterEqual(box.left(), 1, (name, i))
                self.assertGreaterEqual(box.top(), 1, (name, i))
                self.assertLess(box.right(), pic.width()-1, (name, i))
                self.assertLess(box.bottom(), pic.height()-1, (name, i))
                # A deep bow lowers the head; all other new gestures stand.
                self.assertGreater(box.height(), 110 if name == 'greeting16' else 160, (name, i))
            height = QRegion(self.pet.sheet.frames[row, 0].mask()).boundingRect().height()
            self.assertGreaterEqual(height, 164, name)
            self.assertLessEqual(height, 180, name)

    def test_resting_proportions_match_original_parts_and_loop_closes(self):
        reference = model_metrics(self.pet.sheet.frames[0, 5])
        for name in NEW:
            row, count, _ = ANIMATIONS[name]
            first = self.pet.sheet.frames[row, 0]
            actual = model_metrics(first)
            for key, tolerance in [('height', .035), ('silhouette', .08), ('head', .07),
                                   ('skirt', .075), ('boots', .09), ('boot_area', .10)]:
                with self.subTest(animation=name, part=key):
                    self.assertAlmostEqual(actual[key]/reference[key], 1, delta=tolerance)
            self.assertEqual(first.toImage(), self.pet.sheet.frames[row, count-1].toImage(), name)

    def test_toe_area_stays_close_to_original_in_every_pose(self):
        reference = model_metrics(self.pet.sheet.frames[0, 5])['toe_area']
        for name in NEW:
            row, count, _ = ANIMATIONS[name]
            for i in range(count):
                area = model_metrics(self.pet.sheet.frames[row, i])['toe_area']
                with self.subTest(animation=name, frame=i):
                    self.assertAlmostEqual(area/reference, 1, delta=.10)

    def test_all_animations_reachable_and_each_category_has_at_most_eight_choices(self):
        menu = QMenu(self.pet); self.pet.populate_context_menu(menu)
        animations = next(a.menu() for a in menu.actions() if a.text() == 'Animazioni')
        self.assertEqual([a.text() for a in animations.actions() if a.menu()],
                         [n for n, _ in ANIMATION_GROUPS]+['Ripeti'])
        for root in (animations, next(a.menu() for a in animations.actions() if a.text() == 'Ripeti')):
            for category in (a.menu() for a in root.actions() if a.menu() and a.text() != 'Ripeti'):
                self.assertLessEqual(len(category.actions()), 8)
        gestures = next(a.menu() for a in animations.actions() if a.text() == 'Gesti')
        next(a for a in gestures.actions() if a.text() == 'Applauso').trigger()
        self.assertEqual((self.pet.animation, self.pet.state), ('applause16', 'action'))
        repeat = next(a.menu() for a in animations.actions() if a.text() == 'Ripeti')
        gestures = next(a.menu() for a in repeat.actions() if a.text() == 'Gesti')
        next(a for a in gestures.actions() if a.text() == 'Applauso').trigger()
        self.assertEqual((self.pet.animation, self.pet.state), ('applause16', 'pose'))
        self.pet.populate_context_menu(menu)
        animations = next(a.menu() for a in menu.actions() if a.text() == 'Animazioni')
        next(a for a in animations.actions() if a.text() == 'Termina').trigger()
        self.assertFalse(self.pet.locked)
        covered = {n for _, names in ANIMATION_GROUPS for n in names}
        self.assertEqual(set(ANIMATIONS)-covered, {'sleep_in', 'sleep_loop', 'sleep_out'})

    def test_cloud_is_contextual_and_applause_has_no_automatic_event(self):
        self.assertEqual(WEATHER_REACTIONS['cloud'][0], 'cloud16')
        self.assertNotIn('applause16', {v[0] for v in WEATHER_REACTIONS.values()})
        self.assertNotIn('applause16', {v[0] for v in TIME_ANIMATIONS.values()})
        self.assertNotIn('applause16', self.pet.sheet.event_animations.values())
        # Exercise the normal spontaneous choices repeatedly; applause must stay manual.
        import time
        with patch.object(self.pet, 'sequence') as sequence:
            for _ in range(60):
                self.pet.cancel(); self.pet.idle(); self.pet.mode='lively'
                self.pet.next_sleep=time.monotonic()+3600
                self.pet.last_cursor_motion=time.monotonic()
                self.pet.decide(time.monotonic())
            self.assertFalse(any(n == 'applause16' for call in sequence.call_args_list for n, _ in call.args[0]))


if __name__ == '__main__': unittest.main(verbosity=2)
