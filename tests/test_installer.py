import importlib.util
import os
from pathlib import Path
import plistlib
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('installer', Path(__file__).resolve().parents[1] / 'installer/install.py')
i = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="yun jin è ' test ")
        self.addCleanup(self.tmp.cleanup)
        actual = Path(self.tmp.name) / 'actual'
        actual.mkdir()
        # Exercise /var -> /private/var-style aliases even on Linux.
        alias = Path(self.tmp.name) / 'alias'
        alias.symlink_to(actual, target_is_directory=True)
        self.root = alias / 'data'
        self.root.mkdir()
        self.home = alias / 'home'
        (self.home / 'Desktop').mkdir(parents=True)
        self.apps = alias / 'Applications'
        self.apps.mkdir()
        self.program = i.deploy(self.root)
        self.exe = self.home / 'runtime/bin/python'
        self.legacy = self.home / 'Applications' / f'{i.NAME}.app'
        self.desktop = self.home / 'Desktop' / f'{i.NAME}.app'
        self.bundle = self.apps / f'{i.NAME}.app'
        self.enterContext(patch.object(Path, 'home', return_value=self.home))
        self.enterContext(patch.object(i, 'MAC_APPLICATIONS', self.apps))

    def test_deploy_preserves_personal_data(self):
        (self.root / 'companion.sqlite3').write_bytes(b'personal-data-sentinel')
        (self.root / 'attachments').mkdir()
        (self.root / 'attachments/test.png').write_bytes(b'capture')
        (self.program / 'obsolete.py').write_text('old')
        i.deploy(self.root)
        self.assertEqual((self.root / 'companion.sqlite3').read_bytes(), b'personal-data-sentinel')
        self.assertEqual((self.root / 'attachments/test.png').read_bytes(), b'capture')
        self.assertFalse((self.program / 'obsolete.py').exists())
        self.assertTrue((self.program / 'app/yun_jin_music.py').is_file())
        self.assertTrue((self.program / 'Guida.pdf').is_file())

    def test_fresh_install_and_repeat(self):
        for _ in range(2):
            bundle = i.mac_shortcut(self.exe, self.program, self.root)
            self.assertEqual(bundle, self.bundle)
            self.assertEqual(self.desktop.resolve(), bundle.resolve())
            info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
            self.assertEqual(info['CFBundleIdentifier'], i.MAC_BUNDLE_ID)
            self.assertEqual(info['CFBundleShortVersionString'], '1.0.1')
            launcher = bundle / 'Contents/MacOS/YunJin'
            self.assertTrue(launcher.stat().st_mode & 0o111)
            subprocess.run(['sh', '-n', str(launcher)], check=True)
            self.assertFalse(list(self.apps.glob('.yun-jin-install.*')))

    def test_migrate_legacy_and_desktop_link(self):
        i.write_mac_bundle(self.legacy, self.exe, self.program, self.root)
        (self.legacy / 'old-file').write_text('old version')
        self.desktop.symlink_to(self.legacy)
        (self.root / 'companion.sqlite3').write_bytes(b'keep notes')
        i.mac_shortcut(self.exe, self.program, self.root)
        self.assertFalse(self.legacy.exists())
        self.assertEqual(self.desktop.resolve(), self.bundle.resolve())
        self.assertEqual((self.root / 'companion.sqlite3').read_bytes(), b'keep notes')
        self.assertFalse((self.bundle / 'old-file').exists())

    def test_failed_publish_keeps_legacy_and_desktop(self):
        i.write_mac_bundle(self.legacy, self.exe, self.program, self.root)
        self.desktop.symlink_to(self.legacy)
        with patch.object(i, 'publish_mac_bundle', side_effect=PermissionError('cancelled')):
            with self.assertRaises(PermissionError):
                i.mac_shortcut(self.exe, self.program, self.root)
        self.assertTrue(self.legacy.exists())
        self.assertEqual(self.desktop.resolve(), self.legacy.resolve())

    def test_user_applications_alias_does_not_delete_new_app(self):
        (self.home / 'Applications').symlink_to(self.apps, target_is_directory=True)
        i.mac_shortcut(self.exe, self.program, self.root)
        self.assertTrue((self.bundle / 'Contents/MacOS/YunJin').is_file())
        self.assertEqual(self.desktop.resolve(), self.bundle.resolve())

    def test_unrelated_legacy_and_desktop_are_preserved(self):
        self.legacy.mkdir(parents=True)
        (self.legacy / 'personal-file').write_text('keep')
        self.desktop.mkdir()
        (self.desktop / 'personal-file').write_text('keep')
        i.mac_shortcut(self.exe, self.program, self.root)
        self.assertEqual((self.legacy / 'personal-file').read_text(), 'keep')
        self.assertEqual((self.desktop / 'personal-file').read_text(), 'keep')

    def test_another_users_global_launcher_is_preserved(self):
        i.write_mac_bundle(self.bundle, self.exe, self.program, self.root)
        launcher = self.bundle / 'Contents/MacOS/YunJin'
        launcher.write_text('#!/bin/sh\nexec /Users/another-user/python /Users/another-user/program/app/yun_jin_pet.py\n')
        before = (self.bundle / 'Contents/MacOS/YunJin').read_bytes()
        with self.assertRaises(RuntimeError):
            i.mac_shortcut(self.exe, self.program, self.root)
        self.assertEqual((self.bundle / 'Contents/MacOS/YunJin').read_bytes(), before)

    def test_authorization_only_for_copy_command(self):
        staged = self.root / "staged ' app"
        with patch.object(i.os, 'access', return_value=False), patch.object(i, 'run') as run:
            i.publish_mac_bundle(staged, self.bundle)
        args = run.call_args.args[0]
        self.assertEqual(args[0], '/usr/bin/osascript')
        self.assertIn('with administrator privileges', args[2])
        self.assertEqual(shlex.split(args[3]), ['/bin/sh', str(i.SOURCE / 'installer/install-mac-bundle.sh'), str(staged), str(self.bundle)])

    def test_publish_rolls_back_on_final_move_failure(self):
        i.mac_shortcut(self.exe, self.program, self.root)
        old = self.bundle / 'keep-old-version'
        old.write_text('keep')
        staged = self.root / 'staged.app'
        i.write_mac_bundle(staged, self.exe, self.program, self.root)
        stubdir = self.root / 'stub'
        stubdir.mkdir()
        stub = stubdir / 'mv'
        stub.write_text('#!/bin/sh\ncase "$1" in */new.app) exit 1;; esac\nexec /bin/mv "$@"\n')
        stub.chmod(0o755)
        env = dict(os.environ, PATH=str(stubdir) + os.pathsep + os.environ['PATH'])
        result = subprocess.run(['/bin/sh', str(i.SOURCE / 'installer/install-mac-bundle.sh'), str(staged), str(self.bundle)], env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(old.read_text(), 'keep')
        self.assertFalse(list(self.apps.glob('.yun-jin-install.*')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
