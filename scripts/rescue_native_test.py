import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('native', Path(__file__).with_name('rescue_native.py'))
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeTests(unittest.TestCase):
    def test_dispatch_has_no_arbitrary_signal_or_command(self):
        app = Mock()
        for data in ({'method':'kill','pid':1}, {'method':'shell'}, [], None):
            with self.assertRaises(ValueError): native.dispatch(app, data)
        app.assert_not_called()

    def test_plan_and_execution_use_existing_validation(self):
        app = Mock()
        native.dispatch(app, {'method':'plan','target':42,'mode':'group','force':False})
        app.preview.assert_called_once_with(42, 'group', False)
        native.dispatch(app, {'method':'execute','id':'plan','phrase':'종료 42'})
        app.execute.assert_called_once_with('plan', '종료 42')

    def test_status_uses_redacted_public_snapshot(self):
        app = Mock()
        app.status.return_value = {'rows':[]}
        self.assertEqual(native.dispatch(app, {'method':'status'}), {'rows':[]})


if __name__ == '__main__': unittest.main()
