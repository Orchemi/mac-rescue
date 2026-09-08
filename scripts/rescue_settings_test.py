import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import rescue_settings as settings


class SettingsTests(unittest.TestCase):
    def test_masked_examples_are_empty_and_use_safe_defaults(self):
        values=settings.parse_env(Path('.env.local.example').read_text())
        self.assertEqual(values['RESCUE_SSH_USER'],'')
        self.assertEqual(values['RESCUE_TAILSCALE_IP'],'')
        self.assertEqual(values['RESCUE_HOST_ALIAS'],'')
        self.assertEqual(values['RESCUE_SSH_PORT'],'22')

    def test_no_shell_interpolation_or_arbitrary_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            marker=Path(folder)/'should-not-exist'
            with self.assertRaises(ValueError): settings.parse_env('RESCUE_SSH_USER=$(touch '+str(marker)+')')
            self.assertFalse(marker.exists())
        with self.assertRaises(ValueError): settings.parse_env('PASSWORD=never-store-me')
        with self.assertRaises(ValueError): settings.parse_env('RESCUE_SSH_PORT=0')
        with self.assertRaises(ValueError): settings.parse_env('RESCUE_TAILSCALE_IP=not-an-address')

    def test_source_then_installed_config_and_environment_overrides(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)/'home';root=Path(folder)/'repo';root.mkdir()
            saved=home/'.config/rescue/.env.local';saved.parent.mkdir(parents=True)
            saved.write_text('RESCUE_SSH_USER=installed_user\n')
            self.assertEqual(settings.load(root,home,{})['RESCUE_SSH_USER'],'installed_user')
            (root/'.env.local').write_text('RESCUE_SSH_USER=source_user\n')
            self.assertEqual(settings.load(root,home,{})['RESCUE_SSH_USER'],'source_user')
            self.assertEqual(settings.load(root,home,{'RESCUE_SSH_USER':'override_user'})['RESCUE_SSH_USER'],'override_user')

    def test_explicit_file_does_not_silently_fall_back(self):
        with self.assertRaises(ValueError): settings.load(environ={'RESCUE_ENV_FILE':'/nonexistent-rescue-test'})

    def test_live_address_wins_after_machine_migration(self):
        values={'RESCUE_SSH_USER':'demo','RESCUE_SSH_PORT':'22','RESCUE_TAILSCALE_IP':'100.64.0.10','RESCUE_HOST_ALIAS':'My Mac'}
        profile=settings.connection(values,'100.64.0.11')
        self.assertEqual(profile['address'],'100.64.0.11')
        self.assertTrue(profile['address_changed'])
        self.assertEqual(profile['username'],'demo')

    def test_invalid_values_are_not_echoed_in_errors(self):
        sentinel='private-invalid-value'
        with self.assertRaises(ValueError) as error: settings.parse_env('RESCUE_TAILSCALE_IP='+sentinel)
        self.assertNotIn(sentinel,str(error.exception))


if __name__=='__main__':unittest.main()
