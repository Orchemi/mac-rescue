import importlib.util
import os
import signal
import sys
import subprocess
import time
import tempfile
from pathlib import Path
import json
import io
from types import SimpleNamespace
from unittest.mock import patch
import unittest

spec = importlib.util.spec_from_file_location('rescue', os.path.join(os.path.dirname(__file__), 'mac-rescue.py'))
rescue = importlib.util.module_from_spec(spec)
sys.modules['rescue'] = rescue
spec.loader.exec_module(rescue)


def proc(pid, ppid=1, name='node', args='node next dev', **kw):
    return dict(pid=pid, ppid=ppid, uid=os.getuid(), name=name, args=args,
                start=pid * 100, footprint=1024, rss=512, cpu=0., age=90000,
                cwd='/repos/demo/apps/web', ports=[], state='S', **kw)


class SafetyTests(unittest.TestCase):
    def test_preview_cancellation_and_non_tty_never_signal(self):
        rows = [proc(10)]
        snap = dict(rows=rows, groups=rescue.make_groups(rows))
        for execute, tty, answer in [(False, True, 'TERM 10'), (True, True, 'no'), (True, False, 'TERM 10')]:
            opts = SimpleNamespace(pid=False, target=10, force=False, execute=execute)
            with patch('sys.stdout', new=io.StringIO()), patch('sys.stdin.isatty', return_value=tty), \
                    patch('builtins.input', return_value=answer), patch.object(rescue.os, 'kill') as kill:
                if execute and not tty:
                    with self.assertRaises(ValueError): rescue.stop(snap, opts)
                else: rescue.stop(snap, opts)
                kill.assert_not_called()

    def test_shell_wrapper_does_not_create_overlapping_groups(self):
        rows = [proc(10, args='node pnpm dev'), proc(11, 10, name='sh', args='sh -c pnpm dev'),
                proc(12, 11, args='node pnpm dev'), proc(13, 12, name='next-server (v16)')]
        groups = rescue.make_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['pids'], [10, 11, 12, 13])

    def test_groups_do_not_include_shell_or_orca(self):
        rows = [proc(10, name='/Applications/Orca.app/Contents/MacOS/Orca', args='Orca'),
                proc(11, 10, name='zsh', args='-zsh'),
                proc(12, 11, args='node /bin/pnpm dev'),
                proc(13, 12, name='next-server (v16)', args='next-server (v16)'),
                proc(14, 13, args='node worker.js')]
        groups = rescue.make_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['root'], 12)
        self.assertEqual(groups[0]['pids'], [12, 13, 14])

    def test_browser_groups_are_distinct_and_orphan_is_not_auto_killed(self):
        name = '/tmp/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
        rows = [proc(20, name=name, args='chrome'), proc(21, name=name, args='chrome')]
        groups = rescue.make_groups(rows)
        self.assertEqual(len(groups), 2)
        self.assertTrue(all('부모 소실/분리' in g['reasons'] for g in groups))

    def test_pid_reuse_aborts_before_any_signal(self):
        old = [proc(10), proc(11, 10)]
        new = [dict(old[0]), dict(old[1], start=999)]
        sent = []
        with self.assertRaises(ValueError):
            rescue.terminate(old, lambda: new, lambda p, s: sent.append(p), set())
        self.assertEqual(sent, [])

    def test_protected_descendant_aborts_whole_plan(self):
        rows = [proc(10), proc(11, 10, name='sshd', args='sshd')]
        with self.assertRaises(ValueError):
            rescue.validate_plan(rows, set())

    def test_missing_identity_and_other_user_are_rejected(self):
        for row in [dict(proc(10), start=0), dict(proc(10), uid=os.getuid()+1)]:
            with self.assertRaises(ValueError): rescue.validate_plan([row], set())

    def test_current_session_ancestor_is_protected(self):
        with self.assertRaises(ValueError): rescue.validate_plan([proc(10)], {10})

    def test_only_previewed_pids_receive_term_and_parent_first(self):
        old = [proc(10), proc(11, 10)]
        new = old + [proc(12, 10)]
        sent = []
        result = rescue.terminate(old, lambda: new, lambda p, s: sent.append((p, s)), set())
        self.assertEqual(sent, [(10, signal.SIGTERM), (11, signal.SIGTERM)])
        self.assertEqual(result['new_children'], [12])

    def test_reparented_child_keeps_identity_and_is_still_selected(self):
        old = [proc(10), proc(11, 10)]
        sent = []
        rescue.terminate(old, lambda: [dict(r, ppid=1) for r in old],
                         lambda p, s: sent.append(p), set())
        self.assertEqual(sent, [10, 11])

    def test_elapsed_time_parser(self):
        self.assertEqual(rescue.elapsed('04-16:37:40'), 405460)
        self.assertEqual(rescue.elapsed('05:00'), 300)

    def test_history_is_bounded_and_does_not_overwrite_unrelated_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.jsonl'
            snap = dict(time='now', system={}, groups=[], rows=[{'args': 'secret'}])
            for _ in range(242): rescue.save_history(path, snap)
            self.assertEqual(len(path.read_text().splitlines()), 240)
            self.assertNotIn('secret', path.read_text())
            path.write_text('unrelated')
            with self.assertRaises(ValueError): rescue.save_history(path, snap)
            self.assertEqual(path.read_text(), 'unrelated')

    def test_history_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'target'
            target.write_text('untouched')
            link = Path(folder) / 'link'
            link.symlink_to(target)
            with self.assertRaises(OSError): rescue.save_history(link, {})
            self.assertEqual(target.read_text(), 'untouched')

    @unittest.skipUnless(sys.platform == 'darwin', 'Darwin libproc integration')
    def test_real_disposable_tree_termination(self):
        child = subprocess.Popen([sys.executable, '-u', '-c',
            'import subprocess,time; p=subprocess.Popen(["sleep","30"]); print(p.pid,flush=True); time.sleep(30)'],
            stdout=subprocess.PIPE, text=True)
        leaf = int(child.stdout.readline().strip())
        try:
            rows = rescue.processes()
            plan = [r for r in rows if r['pid'] in (child.pid, leaf)]
            self.assertEqual(len(plan), 2)
            result = rescue.terminate(plan, rescue.processes, os.kill, rescue.ancestors(rows))
            self.assertEqual(result['errors'], [])
            self.assertEqual(set(result['sent']), {child.pid, leaf})
            child.wait(timeout=3)
            time.sleep(.1)
            remaining = {r['pid']: r for r in rescue.processes()}
            self.assertTrue(leaf not in remaining or 'Z' in remaining[leaf]['state'])
        finally:
            if child.poll() is None: child.terminate(); child.wait(timeout=3)
            child.stdout.close()


if __name__ == '__main__': unittest.main()
