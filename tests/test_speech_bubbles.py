"""Speech captions, localization and passive window placement without live TTS."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtMultimedia import QMediaPlayer
from yun_jin_app import Companion
from yun_jin_data import Store
from yun_jin_speech import caption_pages
from yun_jin_context import GREETINGS, WEATHER_LINES, contextual_line
from yun_jin_macos import MacOverlay

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class CaptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.store.set_preference('updates_enabled', False)
        self.pet = Companion(self.store)
        for timer in (self.pet.timer, self.pet.reminder_timer, self.pet.checkpoint_timer): timer.stop()
        self.pet.cancel(); self.pet.idle(); self.pet.show(); app.processEvents()
        self.speech = self.pet.speech
        self.speech.player = Mock()
        self.speech.player.duration.return_value = 10000
        self.speech.player.position.return_value = 0
        self.speech.player.errorString.return_value = "Test playback error"
        self.speech.output = Mock()

    def tearDown(self):
        self.speech.process = None
        self.pet.close(); self.pet.deleteLater(); app.processEvents()
        self.store.close(); self.tmp.cleanup()

    def speak(self, text, category='manual'):
        process = Mock()
        with patch('yun_jin_speech.QProcess', return_value=process):
            self.assertTrue(self.speech.speak(text, category=category))
        return process

    def play(self):
        self.speech.playback_state(QMediaPlayer.PlaybackState.PlayingState)

    def test_caption_starts_with_playback_for_manual_preview_and_reminders(self):
        for category in ('manual', 'reminder'):
            with self.subTest(category=category):
                self.speech.stop(False)
                self.speak('Ricordati di fare una pausa.', category)
                self.assertFalse(self.pet.bubble.isVisible())
                self.play()
                self.assertEqual(self.pet.bubble.label.text(), 'Ricordati di fare una pausa.')
                self.assertTrue(self.pet.bubble.isVisible())
                self.speech.media_status(QMediaPlayer.MediaStatus.EndOfMedia)
                self.assertFalse(self.pet.bubble.isVisible())

    def test_long_text_pages_follow_playback_without_losing_words_or_cjk(self):
        for text in ('Una frase lunga da leggere senza perdere parole. '*30,
                     '今天是美好的一天。愿你心情愉快！'*30, 'a'*300):
            pages = caption_pages(text)
            self.assertEqual(''.join(pages).replace(' ', ''), text.replace(' ', ''))
            self.assertTrue(all(0 < len(p) <= 140 for p in pages))
        self.speak('Una frase lunga da leggere senza perdere parole. '*20)
        self.play()
        first = self.pet.bubble.text
        self.speech.update_caption(6000)
        self.assertGreater(self.speech.caption_index, 0)
        self.assertTrue(self.pet.bubble.isVisible())
        self.speech.update_caption(10000)
        self.assertEqual(self.pet.bubble.text, self.speech.caption_pages[-1])
        self.speech.update_caption(0)
        self.assertEqual(self.pet.bubble.text, first)

    def test_stop_error_and_replacement_remove_stale_caption(self):
        old = self.speak('Prima lettura.'); self.play()
        self.speech.stop(False)
        self.assertFalse(self.pet.bubble.isVisible())
        self.speak('Seconda lettura.')
        self.speech.generated(old, 0)
        self.assertFalse(self.pet.bubble.isVisible())
        self.play(); self.assertEqual(self.pet.bubble.text, 'Seconda lettura.')
        self.speech.playback_error()
        self.assertFalse(self.pet.bubble.isVisible())

    def test_background_failures_never_show_a_caption(self):
        self.pet.context.started = True
        self.speech.category = 'ambient'; self.speech.busy = True
        self.speech.current_tag = {'kind': 'greeting'}
        p = Mock(); p.readAllStandardOutput.return_value = b'{"ok": false, "error": "offline"}'
        self.speech.process = p
        self.speech.generated(p, 1)
        self.assertFalse(self.pet.bubble.isVisible())
        self.assertFalse(self.speech.busy)

    def test_bubble_is_plain_text_passive_and_has_no_timer(self):
        bubble = self.pet.bubble
        bubble.present('<b>Una frase</b> & un’altra.')
        self.assertEqual(bubble.label.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(bubble.label.text(), '<b>Una frase</b> & un’altra.')
        self.assertTrue(bubble.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertTrue(bubble.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        self.assertTrue(bubble.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        self.assertEqual(bubble.findChildren(QTimer), [])

    def test_bubble_follows_pet_and_stays_on_negative_origin_screen(self):
        rect = QRect(-1920, -200, 1920, 1080)
        screen = Mock(); screen.availableGeometry.return_value = rect
        with patch.object(self.pet, 'current_screen', return_value=screen):
            for x, y in [(-1900, -195), (-250, -190), (-250, 700), (-1800, 600)]:
                self.pet.move(x, y)
                self.pet.bubble.present('Una frase abbastanza lunga da occupare due righe.')
                app.processEvents()
                self.assertTrue(rect.contains(self.pet.bubble.geometry()), self.pet.bubble.geometry())
            old = self.pet.bubble.pos()
            self.pet.move(-1100, 300); app.processEvents()
            self.assertNotEqual(old, self.pet.bubble.pos())
        self.pet.hide(); app.processEvents(); self.assertFalse(self.pet.bubble.isVisible())
        self.pet.bubble.present(''); self.pet.show(); app.processEvents()
        self.assertFalse(self.pet.bubble.isVisible())

    def test_mac_overlay_orders_bubble_without_requesting_focus(self):
        native = Mock(); native.snapshot.return_value = (1, 0, 0, 0)
        overlay = MacOverlay(app, self.pet, native=native)
        self.pet.mac_overlay = overlay
        try:
            overlay.set_enabled(True)
            self.pet.bubble.present('Buonasera!'); app.processEvents()
            native.configure.assert_any_call(self.pet.bubble, 1001)
            native.focus.assert_not_called()
        finally:
            overlay.set_enabled(False); app.removeEventFilter(overlay)
            self.pet.mac_overlay = None; overlay.deleteLater()

    def test_context_uses_selected_language_provider_and_voice(self):
        context = self.pet.context
        context.started = True
        context.enabled['time'] = False
        for language in ('it', 'en', 'zh-CN'):
            for provider in ('edge', 'google'):
                with self.subTest(language=language, provider=provider):
                    self.speech.stop(False); self.pet.cancel(); self.pet.idle()
                    self.store.set_preference('tts_language', language)
                    self.store.set_preference('tts_provider', provider)
                    context.last_reaction = -1e10
                    context.pending = {'greeting': (context.monotonic()+30, 'morning')}
                    process = Mock()
                    with patch('yun_jin_speech.QProcess', return_value=process): context.dispatch()
                    process.started.connect.call_args.args[0]()
                    job = json.loads(process.write.call_args.args[0])
                    self.assertEqual(job['language'], language)
                    self.assertEqual(job['provider'], provider)
                    self.assertEqual(job['text'], GREETINGS[language]['morning'])
                    self.play()
                    self.assertEqual(self.pet.bubble.text, job['text'])
                    self.assertEqual(self.store.preference('tts_language', ''), language)
            for kind in WEATHER_LINES[language]:
                self.assertEqual(contextual_line(WEATHER_LINES, kind, language), WEATHER_LINES[language][kind])


if __name__ == '__main__': unittest.main(verbosity=2)
