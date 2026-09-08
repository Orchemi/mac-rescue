import importlib.util
from pathlib import Path
import tempfile
import unittest
import plistlib
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('installer',Path(__file__).with_name('install-rescue.py'))
installer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        def fake_build(version):
            binary=version/'Rescue';binary.write_bytes(b'native-test-binary');return binary
        mock=patch.object(installer,'build_native',side_effect=fake_build)
        mock.start();self.addCleanup(mock.stop)
        env=patch.object(installer,'ENV_SOURCE',Path('/nonexistent-rescue-test.env'),create=True)
        env.start();self.addCleanup(env.stop)

    def test_private_config_is_separate_from_bundle_and_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'private.env'
            source.write_text('RESCUE_SSH_USER=private_test_user\nRESCUE_SSH_PORT=2222\n')
            with patch.object(installer,'ENV_SOURCE',source): installer.install(root/'home')
            saved=root/'home/.config/rescue/.env.local'
            self.assertEqual(saved.read_text(),source.read_text())
            self.assertEqual(saved.stat().st_mode & 0o777,0o600)
            self.assertEqual(saved.parent.stat().st_mode & 0o777,0o700)
            self.assertFalse(list((root/'home/Applications').rglob('.env.local')))
            self.assertFalse(list((root/'home/.local/share/rescue/versions').rglob('.env.local')))

    def test_invalid_private_config_fails_before_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'private.env';source.write_text('PASSWORD=never-store-me')
            with patch.object(installer,'ENV_SOURCE',source), self.assertRaises(ValueError): installer.install(root/'home')
            self.assertFalse((root/'home').exists())

    def test_repeat_install_preserves_profile_and_one_path_block(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);(home/'.zprofile').write_text('# user setting\n')
            first=installer.install(home);second=installer.install(home)
            self.assertEqual(first,second)
            self.assertEqual((home/'.zprofile').read_text().count('# >>> Rescue PATH >>>'),1)
            self.assertTrue((home/'.zprofile').read_text().startswith('# user setting\n'))
            self.assertTrue((home/'.local/share/rescue/current/rescue-ui/app.js').exists())
            self.assertTrue((home/'Applications/Rescue.app/Contents/MacOS/Rescue').stat().st_mode & 0o111)
            app=home/'Applications/Rescue.app/Contents'
            self.assertEqual((app/'MacOS/Rescue').read_bytes(),b'native-test-binary')
            self.assertTrue((app/'Resources/engine/rescue_native.py').exists())
            self.assertNotIn('LSUIElement',plistlib.loads((app/'Info.plist').read_bytes()))

    def test_unrelated_command_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);binpath=home/'.local/bin';binpath.mkdir(parents=True)
            (binpath/'rescue').write_text('unrelated')
            with self.assertRaises(ValueError): installer.install(home)
            self.assertEqual((binpath/'rescue').read_text(),'unrelated')

    def test_unrelated_app_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);(home/'Applications/Rescue.app').mkdir(parents=True)
            with self.assertRaises(ValueError): installer.install(home)


if __name__=='__main__':unittest.main()
