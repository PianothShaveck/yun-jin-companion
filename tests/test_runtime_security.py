"""Security floors and bootstrapping order, independent of the host's Python."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer_security', ROOT/'installer/install.py')
i = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i)


class SecurityTests(unittest.TestCase):
    def test_rejects_unpatched_python_and_unsupported_future_series(self):
        for system in ('darwin', 'win32'):
            for version in ((3,11,17),(3,12,15),(3,13,15),(3,13,16),(3,14,8),(3,15,0)):
                self.assertFalse(i.supported_python(version,system),(system,version))
            for version in ((3,13,17),(3,13,18),(3,14,9),(3,14,10)):
                self.assertTrue(i.supported_python(version,system),(system,version))
        self.assertTrue(i.supported_python((3,12,15),'linux'))
        self.assertFalse(i.supported_python((3,12,14),'linux'))

    def test_old_pip_bootstraps_from_hash_pinned_wheel_without_index(self):
        with patch.object(i,'python_works',side_effect=[False,True]),patch.object(i,'run') as run:
            i.secure_pip(Path('/tmp/python'))
        args=run.call_args.args[0]
        self.assertIn('--no-index',args);self.assertIn('--no-deps',args)
        self.assertIn('--isolated',args)
        self.assertIn('#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70',args[-1])

    def test_current_pip_does_not_download_again(self):
        with patch.object(i,'python_works',return_value=True),patch.object(i,'run') as run:
            i.secure_pip(Path('/tmp/python'))
        run.assert_not_called()

    def test_failed_security_bootstrap_aborts(self):
        with patch.object(i,'python_works',return_value=False),patch.object(i,'run'):
            with self.assertRaisesRegex(RuntimeError,'sicurezza'):
                i.secure_pip(Path('/tmp/python'))
        with patch.object(i,'python_works',return_value=False),patch.object(i,'run',side_effect=subprocess.CalledProcessError(1,[])):
            with self.assertRaises(subprocess.CalledProcessError):i.secure_pip(Path('/tmp/python'))


if __name__=='__main__':unittest.main()
