import importlib.util
from pathlib import Path
import os
import sys
import unittest
import time
import threading
import urllib.request
import urllib.error
import json
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('gui', Path(__file__).with_name('rescue_gui.py'))
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)


def row(pid, ppid=1, name='node'):
    return dict(pid=pid, ppid=ppid, uid=os.getuid(), name=name, args='node next dev',
                start=pid*100, footprint=1024, rss=512, cpu=0., age=90000,
                cwd='/repos/demo', ports=[3000], state='S')


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.rows = [row(100), row(101, 100)]
        self.snap = dict(rows=self.rows, groups=gui.core.make_groups(self.rows), system={}, time='now', warnings=[])
        self.app = gui.App('test-token')

    def test_auth_requires_correct_host_token_and_origin(self):
        self.assertTrue(gui.authorized('127.0.0.1:8123', None, 'secret', 'secret', 8123))
        for host, origin, token in [('evil.test:8123', None, 'secret'),
                                    ('127.0.0.1:8123', 'https://evil.test', 'secret'),
                                    ('127.0.0.1:8123', None, ''),
                                    ('127.0.0.1:8123', 'null', 'secret')]:
            self.assertFalse(gui.authorized(host, origin, token, 'secret', 8123))

    def test_plan_is_fixed_and_execution_requires_exact_confirmation(self):
        with patch.object(gui.core, 'snapshot', return_value=self.snap), patch.object(gui.core, 'processes', return_value=self.rows):
            plan = self.app.preview(100, 'group', False)
            self.assertEqual([r['pid'] for r in plan['rows']], [100,101])
            with patch.object(gui.core, 'terminate') as kill:
                with self.assertRaises(ValueError): self.app.execute(plan['id'], 'wrong')
                kill.assert_not_called()

    def test_expired_plan_is_rejected(self):
        with patch.object(gui.core, 'snapshot', return_value=self.snap):
            plan = self.app.preview(100, 'group', False)
        self.app.plans[plan['id']]['expires'] = time.monotonic()-1
        with self.assertRaises(ValueError): self.app.execute(plan['id'], plan['phrase'])

    def test_protected_or_unknown_pid_cannot_be_planned(self):
        with patch.object(gui.core, 'snapshot', return_value=self.snap):
            with self.assertRaises(ValueError): self.app.preview(999, 'pid', False)
        self.snap['rows'][1]['name'] = '/Applications/Orca.app/Contents/MacOS/Orca'
        with patch.object(gui.core, 'snapshot', return_value=self.snap):
            with self.assertRaises(ValueError): self.app.preview(100, 'group', False)

    def test_snapshot_excludes_arguments_and_contains_applicable_targets(self):
        with patch.object(gui.core, 'snapshot', return_value=self.snap): result=self.app.status()
        self.assertNotIn('args', result['rows'][0])
        self.assertTrue(result['rows'][0]['can_stop'])

    def test_plan_is_single_use_and_force_is_explicit(self):
        result=dict(sent=[100,101],already_exited=[],errors=[],new_children=[])
        with patch.object(gui.core,'snapshot',return_value=self.snap), patch.object(gui.core,'processes',return_value=[]), \
                patch.object(gui.core,'terminate',return_value=result) as terminate:
            plan=self.app.preview(100,'group',True)
            self.assertEqual(plan['phrase'],'강제 종료 100')
            self.app.execute(plan['id'],plan['phrase'])
            self.assertTrue(terminate.call_args.args[-1])
            with self.assertRaises(ValueError): self.app.execute(plan['id'],plan['phrase'])

    def test_http_boundary_rejects_foreign_origin_missing_token_and_host(self):
        server=gui.HTTPServer(('127.0.0.1',0),gui.Handler);server.app=self.app
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            for headers in [{},{'X-Rescue-Token':'test-token','Origin':'https://evil.test'},
                            {'X-Rescue-Token':'test-token','Host':'evil.test'},
                            {'X-Rescue-Token':'wrong'}]:
                req=urllib.request.Request(base+'/api/plan',data=b'{}',headers={**headers,'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as ctx: urllib.request.urlopen(req)
                self.assertEqual(ctx.exception.code,403)
            req=urllib.request.Request(base+'/api/health',headers={'X-Rescue-Token':'test-token'})
            with urllib.request.urlopen(req) as response:self.assertTrue(json.load(response)['ok'])
        finally:server.shutdown();server.server_close();thread.join()


if __name__ == '__main__': unittest.main()
