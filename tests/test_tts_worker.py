"""Edge protocol regression and worker behavior, without network or audio hardware."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from yun_jin_tts_worker import synthesize


class EdgeVoiceTests(unittest.TestCase):
    def test_installed_edge_library_uses_the_v2_protocol(self):
        # Published upstream v2 vector: an old client produces a different token
        # and receives HTTP 403 before any speech can be synthesized.
        from edge_tts.constants import SEC_MS_GEC_VERSION
        from edge_tts.drm import DRM
        self.assertTrue(SEC_MS_GEC_VERSION.startswith('2-'))
        with patch.object(DRM, 'get_unix_timestamp', return_value=1791888000):
            self.assertEqual(DRM.generate_sec_ms_gec(),
                '492D7694A183A45E-56E821F95D4579C5B7C7E33DC7303FF379EC36D510213555BBBB9EB17EF15876')

    def test_edge_preserves_voice_rate_pitch_unicode_and_reuses_cached_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            for voice, language, text in (
                ('it-IT-ElsaNeural', 'it', 'Buonasera, è ora di riposare.'),
                ('zh-CN-XiaoxiaoNeural', 'zh-CN', '晚上好，今天辛苦了。'),
            ):
                with self.subTest(voice=voice):
                    job = dict(provider='edge', voice=voice, language=language,
                               text=text, rate=-10, pitch=2, cache=tmp)

                    async def save(path):
                        Path(path).write_bytes(b'ID3' + bytes(200))

                    with patch('edge_tts.Communicate') as speaker:
                        speaker.return_value.save.side_effect = save
                        result = synthesize(job)
                        speaker.assert_called_once_with(text, voice=voice, rate='-10%',
                            pitch='+2Hz', connect_timeout=8, receive_timeout=20)
                        self.assertTrue(result['ok'])
                        self.assertFalse(result['cached'])
                        cached = synthesize(job)
                        self.assertTrue(cached['cached'])
                        self.assertTrue(Path(cached['path']).samefile(result['path']))
                        speaker.assert_called_once()

    def test_failed_edge_request_leaves_no_partial_cache_and_can_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = dict(provider='edge', voice='it-IT-ElsaNeural', language='it',
                       text='Buongiorno!', rate=0, pitch=0, cache=tmp)

            async def fail(path):
                Path(path).write_bytes(b'incomplete')
                raise ConnectionError('service unavailable')

            async def succeed(path):
                Path(path).write_bytes(b'ID3' + bytes(200))

            with patch('edge_tts.Communicate') as speaker:
                speaker.return_value.save.side_effect = fail
                with self.assertRaises(ConnectionError):
                    synthesize(job)
                self.assertEqual(list(Path(tmp).iterdir()), [])
                speaker.return_value.save.side_effect = succeed
                self.assertTrue(synthesize(job)['ok'])
                self.assertEqual(speaker.call_count, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
