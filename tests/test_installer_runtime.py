"""Exercise runtime repair without downloading dependencies or touching user data."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', SOURCE / 'installer/install.py')
i = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="yun jin è ' runtime ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'data'
        self.root.mkdir()
        self.sentinels = {
            'companion.sqlite3': b'notes, reminders and study history',
            'attachments/photo.png': b'attachment',
            'study-media/audio.mp3': b'study audio',
            'program/app/yun_jin_pet.py': b'previous program',
        }
        for name, content in self.sentinels.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.env = self.root / 'runtime' / ('python-%s.%s' % sys.version_info[:2])
        self.exe = self.env / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        self.marker = self.env / 'installed.json'
        # Real Python/venv/ensurepip, but no network or application wheels.
        self.pip = self.enterContext(patch.object(i, 'run'))
        self.enterContext(patch.object(i, 'DEPENDENCY_CHECK', i.RUNTIME_CHECK))

    def assert_data_unchanged(self):
        for name, content in self.sentinels.items():
            self.assertEqual((self.root / name).read_bytes(), content)

    def site_packages(self):
        result = subprocess.run([str(self.exe), '-I', '-c',
                                 'import sysconfig; print(sysconfig.get_path("purelib"))'],
                                capture_output=True, text=True, check=True, timeout=30)
        return Path(result.stdout.strip())

    def test_new_environment_and_repeat_install_do_not_redownload(self):
        self.assertEqual(i.environment(self.root), self.exe)
        self.assertTrue(self.marker.is_file())
        self.pip.assert_called_once()
        with patch.object(i.venv.EnvBuilder, 'create') as create:
            self.assertEqual(i.environment(self.root), self.exe)
        create.assert_not_called()
        self.pip.assert_called_once()
        self.assert_data_unchanged()

    def test_removed_homebrew_framework_rebuilds_even_with_a_valid_marker(self):
        i.environment(self.root)
        real_run = subprocess.run
        for cached in (True, False):
            with self.subTest(cached=cached):
                if not cached:
                    self.marker.unlink()
                old = self.env / 'removed-framework'
                old.touch()

                def dyld_failure(args, **kwargs):
                    if str(args[0]) == str(self.exe) and old.exists():
                        # macOS dyld exits via SIGABRT despite an existing binary.
                        return subprocess.CompletedProcess(args, -6)
                    return real_run(args, **kwargs)

                with patch.object(i.subprocess, 'run', side_effect=dyld_failure):
                    self.assertEqual(i.environment(self.root), self.exe)
                self.assertFalse(old.exists())
                self.assertTrue(i.python_works(self.exe, i.RUNTIME_CHECK))
                self.assertTrue(self.marker.is_file())
                self.assert_data_unchanged()
        self.assertEqual(self.pip.call_count, 3)

    def test_missing_csv_is_repaired_even_when_python_starts(self):
        i.environment(self.root)
        hook = self.site_packages() / 'sitecustomize.py'
        hook.write_text('import sys\n'
                        'class MissingCsv:\n'
                        '    def find_spec(self, name, *args):\n'
                        '        if name == "csv": raise ModuleNotFoundError("No module named csv")\n'
                        'sys.meta_path.insert(0, MissingCsv())\n', encoding='utf-8')
        self.assertTrue(i.python_works(self.exe, 'import sys'))
        self.assertFalse(i.python_works(self.exe, 'import csv'))
        i.environment(self.root)
        self.assertFalse(hook.exists())
        self.assertTrue(i.python_works(self.exe, 'import csv, sqlite3, ssl'))
        self.assertEqual(self.pip.call_count, 2)
        self.assert_data_unchanged()

    def test_missing_pip_is_repaired(self):
        i.environment(self.root)
        shutil.rmtree(self.site_packages() / 'pip')
        self.assertTrue(i.python_works(self.exe, 'import csv'))
        self.assertFalse(i.python_works(self.exe, 'import pip'))
        i.environment(self.root)
        self.assertTrue(i.python_works(self.exe, 'import pip'))
        self.assertEqual(self.pip.call_count, 2)
        self.assert_data_unchanged()

    def test_switching_base_python_rebuilds_a_healthy_environment(self):
        i.environment(self.root)
        hook = self.site_packages() / 'sitecustomize.py'
        hook.write_text('import sys\nsys.base_prefix = "removed-homebrew-cellar"\n', encoding='utf-8')
        self.assertTrue(i.python_works(self.exe, i.RUNTIME_CHECK))
        i.environment(self.root)
        self.assertFalse(hook.exists())
        self.assertEqual(self.pip.call_count, 2)
        self.assert_data_unchanged()

    def test_failed_creation_preserves_data_and_the_next_attempt_recovers(self):
        def interrupted(env):
            Path(env).mkdir(parents=True)
            (Path(env) / 'incomplete').touch()
            raise OSError('interrupted creation')

        with patch.object(i.venv.EnvBuilder, 'create', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                i.environment(self.root)
        self.pip.assert_not_called()
        self.assertFalse(self.marker.exists())
        self.assert_data_unchanged()
        i.environment(self.root)
        self.assertFalse((self.env / 'incomplete').exists())
        self.assertTrue(i.python_works(self.exe, i.RUNTIME_CHECK))
        self.assert_data_unchanged()

    def test_failed_download_never_marks_ready_and_can_be_retried(self):
        self.pip.side_effect = subprocess.CalledProcessError(1, ['pip'])
        with self.assertRaises(subprocess.CalledProcessError):
            i.environment(self.root)
        self.assertFalse(self.marker.exists())
        self.assert_data_unchanged()
        self.pip.side_effect = None
        with patch.object(i.venv.EnvBuilder, 'create') as create:
            i.environment(self.root)
        create.assert_not_called()
        self.assertTrue(self.marker.is_file())
        self.assert_data_unchanged()

    def test_incomplete_dependencies_never_mark_ready(self):
        with patch.object(i, 'DEPENDENCY_CHECK', 'raise ImportError("incomplete dependencies")'):
            with self.assertRaisesRegex(RuntimeError, 'dipendenze'):
                i.environment(self.root)
        self.assertFalse(self.marker.exists())
        self.assert_data_unchanged()
        i.environment(self.root)
        self.assertTrue(self.marker.is_file())

    def test_invalid_marker_does_not_block_reinstallation(self):
        i.environment(self.root)
        for value in (None, [], {}, '{invalid json'):
            with self.subTest(marker=value):
                self.marker.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')
                with patch.object(i.venv.EnvBuilder, 'create') as create:
                    i.environment(self.root)
                create.assert_not_called()
                self.assertIn('requirements', json.loads(self.marker.read_text()))
        self.assert_data_unchanged()


class ProbeTests(unittest.TestCase):
    def test_probe_handles_missing_executable_abort_and_timeout(self):
        for failure in (FileNotFoundError(), PermissionError(),
                        subprocess.TimeoutExpired('python', 30)):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(i.subprocess, 'run', side_effect=failure) as run:
                    self.assertFalse(i.python_works('python', i.RUNTIME_CHECK))
                self.assertEqual(run.call_args.kwargs['timeout'], 30)
                self.assertIn('-I', run.call_args.args[0])
        with patch.object(i.subprocess, 'run', return_value=subprocess.CompletedProcess('python', -6)):
            self.assertFalse(i.python_works('python', i.RUNTIME_CHECK))

    @unittest.skipIf(os.name == 'nt', 'macOS shell bootstrap')
    def test_mac_prefers_official_python_and_skips_broken_candidates(self):
        script = (SOURCE / 'Mac.command').read_text(encoding='utf-8')
        function = script[script.index('find_python() {'):script.index('if ! PYTHON_EXE=')]
        with tempfile.TemporaryDirectory() as tmp:
            function = function.replace('/Library/Frameworks', tmp + '/official')
            function = function.replace('/opt/homebrew', tmp + '/brew')
            function = function.replace('/usr/local', tmp + '/local')
            official = Path(tmp) / 'official/Python.framework/Versions/3.14/bin/python3'
            brew = Path(tmp) / 'brew/bin/python3'
            for path in (official, brew):
                path.parent.mkdir(parents=True)
                path.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n', encoding='utf-8')
                path.chmod(0o755)
            result = subprocess.run(['bash', '-c', function + '\nfind_python'], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), str(official))
            official.write_text('#!/bin/sh\nexit 1\n', encoding='utf-8')
            result = subprocess.run(['bash', '-c', function + '\nfind_python'], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), str(brew))
            brew.write_text('#!/bin/sh\nexit 1\n', encoding='utf-8')
            result = subprocess.run(['bash', '-c', function + '\nfind_python'], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
