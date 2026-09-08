#!/usr/bin/env python3
"""macOS process-footprint monitor and explicitly confirmed session cleanup."""
import argparse
import collections
import ctypes
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import shlex
import rescue_settings

sys.dont_write_bytecode = True

GIB = 1024 ** 3


def run(args, timeout=10):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          env=dict(os.environ, LC_ALL='C'))


def elapsed(text):
    days, rest = text.split('-', 1) if '-' in text else ('0', text)
    parts = list(map(int, rest.split(':')))
    parts = [0] * (3 - len(parts)) + parts
    return int(days) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


class Usage(ctypes.Structure):
    # Darwin sys/resource.h, rusage_info_v0 (footprint includes compressed charges).
    _fields_ = [('uuid', ctypes.c_uint8 * 16)] + [
        (name, ctypes.c_uint64) for name in
        ('user', 'system', 'idle', 'interrupt', 'pageins', 'wired',
         'resident', 'footprint', 'start', 'exit')]


def processes():
    lib = ctypes.CDLL('/usr/lib/libproc.dylib')
    ps = run(['ps', '-axo', 'pid=,ppid=,uid=,etime=,pcpu=,state=,comm='])
    if ps.returncode: raise RuntimeError(ps.stderr.strip())
    args = run(['ps', '-ww', '-axo', 'pid=,args='])
    if args.returncode: raise RuntimeError(args.stderr.strip())
    commands = {}
    for line in args.stdout.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) == 2: commands[int(fields[0])] = fields[1]
    rows = []
    for line in ps.stdout.splitlines():
        x = line.split(None, 6)
        if len(x) != 7: continue
        pid, ppid, uid = map(int, x[:3])
        u = Usage()
        ok = lib.proc_pid_rusage(pid, 0, ctypes.byref(u)) == 0
        rows.append(dict(pid=pid, ppid=ppid, uid=uid, age=elapsed(x[3]),
                         cpu=float(x[4]), state=x[5], name=x[6],
                         args=commands.get(pid, ''), start=u.start if ok else 0,
                         footprint=u.footprint if ok else None,
                         rss=u.resident if ok else None, cwd='', ports=[]))
    return rows


def clean(text):
    return ''.join(c if c.isprintable() else '?' for c in str(text))


def runtime(row):
    name = os.path.basename(row['name'])
    return name == 'node' or name.startswith('next-server') or name in ('turbo', 'bun', 'deno')


def dev_seed(row):
    return runtime(row) and (row['name'].startswith('next-server') or
                            re.search(r'\b(next\s+dev|turbo\s+dev|vite(?:\s|$)|(?:pnpm|npm|bun)(?:\s+run)?\s+dev(?:\b|:))', row['args']) or
                            bool(row['ports']))


def browser_root(row):
    return row['name'].endswith('/Google Chrome for Testing')


def descendants(root, rows):
    children = collections.defaultdict(list)
    for r in rows: children[r['ppid']].append(r['pid'])
    seen, queue = set(), [root]
    while queue:
        pid = queue.pop(0)
        if pid in seen: continue
        seen.add(pid)
        queue.extend(children[pid])
    return seen


def project(cwd):
    if not cwd: return '경로 확인 불가'
    p = Path(cwd)
    for parent in [p, *p.parents]:
        if (parent / '.git').exists(): return str(parent)
    return cwd


def make_groups(rows):
    by_pid = {r['pid']: r for r in rows}
    roots = {}
    for row in rows:
        if row['uid'] != os.getuid(): continue
        if browser_root(row):
            root = row
            parent = by_pid.get(row['ppid'])
            if parent and 'agent-browser' in os.path.basename(parent['name']): root = parent
            roots[root['pid']] = 'chrome'
        elif dev_seed(row):
            root, seen = row, set()
            while root['ppid'] in by_pid and root['pid'] not in seen:
                seen.add(root['pid'])
                parent = by_pid[root['ppid']]
                if not runtime(parent) or parent['uid'] != row['uid']: break
                root = parent
            roots[root['pid']] = 'dev'
    # A shell wrapper may separate two runtime ancestors. Keep only the outer
    # recognized launch group so its children are never counted twice.
    nested = {child for parent in roots for child in descendants(parent, rows)
              if child != parent and child in roots}
    roots = {pid: kind for pid, kind in roots.items() if pid not in nested}
    groups = []
    for pid, kind in roots.items():
        members = [by_pid[p] for p in sorted(descendants(pid, rows)) if p in by_pid]
        root = by_pid[pid]
        cwd = root['cwd'] or next((r['cwd'] for r in members if r['cwd']), '')
        memory = sum(r['footprint'] or 0 for r in members)
        reasons = []
        if memory >= 2 * GIB: reasons.append('2GiB 이상')
        if root['age'] >= 86400: reasons.append('24시간 이상')
        if root['ppid'] == 1: reasons.append('부모 소실/분리')
        groups.append(dict(root=pid, kind=kind, pids=[r['pid'] for r in members],
                           footprint=memory, partial=any(r['footprint'] is None for r in members),
                           age=root['age'], project=project(cwd), cwd=cwd,
                           ports=sorted({p for r in members for p in r['ports']}), reasons=reasons))
    for g in groups:
        if g['kind'] == 'chrome' and g['cwd'] and sum(
                x['kind'] == 'chrome' and x['project'] == g['project'] for x in groups) > 1:
            g['reasons'].append('같은 프로젝트의 여러 Chrome 세션')
    return sorted(groups, key=lambda g: -g['footprint'])


def enrich(rows):
    by_pid = {r['pid']: r for r in rows}
    warnings = []
    # One lsof invocation per surface; no /proc scans or heap snapshots.
    for args, mode in [(['lsof', '-nP', '-iTCP', '-sTCP:LISTEN', '-Fpn'], 'port'),
                       (['lsof', '-a', '-u', str(os.getuid()), '-d', 'cwd', '-Fpn'], 'cwd')]:
        try:
            result = run(args)
        except subprocess.TimeoutExpired:
            warnings.append(mode + ' 조회 시간 초과'); continue
        if result.returncode not in (0, 1): warnings.append(mode + ': ' + result.stderr.strip())
        pid = None
        for line in result.stdout.splitlines():
            if line.startswith('p') and line[1:].isdigit(): pid = int(line[1:])
            elif line.startswith('n') and pid in by_pid:
                if mode == 'cwd': by_pid[pid]['cwd'] = line[1:]
                else:
                    match = re.search(r':(\d+)$', line[1:])
                    if match: by_pid[pid]['ports'].append(int(match[1]))
    return warnings


def system_memory():
    values = run(['sysctl', '-n', 'hw.memsize', 'kern.memorystatus_vm_pressure_level']).stdout.splitlines()
    if len(values) != 2: raise RuntimeError('RAM/메모리 압력 조회 실패')
    vm = run(['vm_stat']).stdout
    page = re.search(r'page size of (\d+) bytes', vm)
    if not page: raise RuntimeError('vm_stat 조회 실패')
    size = int(page[1])
    pages = {k.strip(): int(v) * size for k, v in re.findall(r'^([^:\n]+):\s+(\d+)\.', vm, re.M)}
    swap = run(['sysctl', 'vm.swapusage']).stdout
    used = re.search(r'used = ([\d.]+)M', swap)
    return dict(ram=int(values[0]), pressure={1: '정상', 2: '경고', 4: '위험'}.get(int(values[1]), values[1]),
                compressed=pages.get('Pages occupied by compressor'), wired=pages.get('Pages wired down'),
                free=pages.get('Pages free'), swap_used=float(used[1])*1024**2 if used else None,
                disk_free=shutil.disk_usage('/System/Volumes/Data').free)


def snapshot():
    rows = processes()
    warnings = enrich(rows)
    return dict(time=datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
                system=system_memory(), rows=rows, groups=make_groups(rows), warnings=warnings)


def save_history(path, snap):
    """Keep only the latest 240 samples, excluding argv and environment data."""
    path = Path(path).expanduser()
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'r+', encoding='utf-8') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise ValueError('로그는 본인 소유의 일반 파일이어야 합니다.')
        if info.st_size > 10 * 1024**2: raise ValueError('기존 로그가 10MiB를 초과합니다. 새 경로를 사용하세요.')
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lines = stream.read().splitlines()
        # Refuse to replace an unrelated existing file.
        for line in lines:
            entry = json.loads(line)
            if not isinstance(entry, dict) or entry.get('format') != 'mac-rescue-v1':
                raise ValueError('mac-rescue 로그가 아닌 파일입니다.')
        sample = dict(format='mac-rescue-v1', time=snap['time'], system=snap['system'], groups=snap['groups'])
        lines = lines[-239:] + [json.dumps(sample, ensure_ascii=False)]
        stream.seek(0); stream.write('\n'.join(lines) + '\n'); stream.truncate()


def protected(row):
    name = os.path.basename(row['name']).lower().lstrip('-')
    return (row['pid'] <= 1 or row['uid'] != os.getuid() or not row['start'] or
            name in ('zsh', 'bash', 'fish', 'login', 'sshd', 'sshd-session', 'launchd') or
            (name == 'sh' and not re.match(r'^(?:/bin/)?sh\s+-c\s', row['args'])) or
            any(x in row['name'].lower() for x in ('orca.app/', 'tailscale', 'docker', 'virtualization',
                                                    'chatgpt.app/', 'aside.app/')) or
            name.startswith(('codex', 'claude')))


def ancestors(rows):
    by_pid = {r['pid']: r for r in rows}
    pid, seen = os.getpid(), set()
    while pid in by_pid and pid not in seen:
        seen.add(pid)
        pid = by_pid[pid]['ppid']
    return seen


def validate_plan(rows, protected_pids):
    if not rows: raise ValueError('종료 대상이 없습니다.')
    for r in rows:
        if protected(r) or r['pid'] in protected_pids:
            raise ValueError('보호 대상 또는 식별 불가 PID: ' + str(r['pid']))


def terminate(plan, collect, send, protected_pids, force=False):
    validate_plan(plan, protected_pids)
    latest = {r['pid']: r for r in collect()}
    for old in plan:
        now = latest.get(old['pid'])
        if now and (now['start'], now['uid'], now['name']) != (old['start'], old['uid'], old['name']):
            raise ValueError('PID 재사용/실행 파일 변경 감지. 다시 미리보기 하세요: ' + str(old['pid']))
    validate_plan([latest[r['pid']] for r in plan if r['pid'] in latest] or plan, protected_pids)
    selected = {r['pid'] for r in plan}
    new_children = sorted({p for r in plan for p in descendants(r['pid'], list(latest.values()))} - selected)
    sent, gone, errors = [], [], []
    # Stop launchers before their children so a supervisor cannot immediately respawn them.
    pending = {r['pid']: r for r in plan}
    ordered = []
    while pending:
        level = [r for r in pending.values() if r['ppid'] not in pending]
        if not level: raise ValueError('프로세스 관계가 순환합니다.')
        ordered.extend(level)
        for r in level: del pending[r['pid']]
    for old in ordered:
        now = next((r for r in collect() if r['pid'] == old['pid']), None)
        if not now: gone.append(old['pid']); continue
        if (now['start'], now['uid'], now['name']) != (old['start'], old['uid'], old['name']):
            errors.append(str(old['pid']) + ': 식별 변경, 건너뜀'); continue
        if protected(now) or now['pid'] in protected_pids:
            errors.append(str(old['pid']) + ': 보호 대상, 건너뜀'); continue
        try:
            send(old['pid'], signal.SIGKILL if force else signal.SIGTERM)
            sent.append(old['pid'])
        except ProcessLookupError: gone.append(old['pid'])
        except OSError as exc: errors.append(str(old['pid']) + ': ' + str(exc))
    return dict(sent=sent, already_exited=gone, errors=errors, new_children=new_children)


def gib(value):
    return '?' if value is None else f'{value/GIB:.2f}G'


def age(value):
    return f'{value/3600:.1f}h'


def display(snap, previous=None):
    s = snap['system']
    print(f"{snap['time']}  압력 {s['pressure']} | RAM {gib(s['ram'])} | 압축 {gib(s['compressed'])}")
    print(f"스왑 {gib(s['swap_used'])} | 디스크 여유 {gib(s['disk_free'])}")
    print('\n실행 그룹: ROOT  메모리  경과  종류  프로젝트 / 포트')
    old = {g['root']: g for g in previous['groups']} if previous else {}
    for g in snap['groups']:
        trend = ''
        if g['root'] in old:
            before = next((r for r in previous['rows'] if r['pid'] == g['root']), None)
            now = next((r for r in snap['rows'] if r['pid'] == g['root']), None)
            if before and now and before['start'] == now['start']:
                trend = f" / 전회 대비 {(g['footprint']-old[g['root']]['footprint'])/1024**2:+.0f}MiB"
        print(f"{g['root']:>6} {gib(g['footprint']):>7}{'*' if g['partial'] else ' '} {age(g['age']):>7} {g['kind']:>6}  {clean(g['project'])}")
        print('       포트 ' + ','.join(map(str, g['ports'])) + f" / {len(g['pids'])}개" + trend)
        print('       검토: ' + (' · '.join(g['reasons']) or '특별한 근거 없음'))
    print('\n상위 프로세스: PID / PPID / footprint / RSS / 이름')
    for r in sorted(snap['rows'], key=lambda r: -(r['footprint'] or 0))[:12]:
        print(f"{r['pid']:>6} {r['ppid']:>6} {gib(r['footprint']):>7} {gib(r['rss']):>7}  {clean(os.path.basename(r['name']))}")
    print('\n장시간·부모 분리는 stale 확정이 아닙니다. 메모리는 RAM 회수량과 다릅니다.')
    print('* 일부 프로세스 측정 불가. root/다른 사용자 메모리도 조회 권한에 따라 누락될 수 있습니다.')
    for warning in snap['warnings']: print('주의: ' + clean(warning))


def show_group(snap, root):
    group = next((g for g in snap['groups'] if g['root'] == root), None)
    if not group: raise ValueError('현재 실행 그룹 ROOT를 지정하세요. 먼저 mac-rescue를 실행하세요.')
    print(f"{group['kind']} / {clean(group['project'])} / {gib(group['footprint'])}")
    print('PID   PPID  메모리   경과   프로세스 / 작업 디렉터리 / 포트')
    for row in snap['rows']:
        if row['pid'] in group['pids']:
            print(f"{row['pid']} {row['ppid']} {gib(row['footprint'])} {age(row['age'])} {clean(row['name'])}")
            print(f"    {clean(row['cwd'])} / {row['ports']}")
    by_pid = {r['pid']: r for r in snap['rows']}
    chain, pid = [], root
    while pid in by_pid and pid not in [x['pid'] for x in chain]:
        chain.append(by_pid[pid]); pid = by_pid[pid]['ppid']
    print('부모 경로: ' + ' ← '.join(f"{r['pid']} {clean(os.path.basename(r['name']))}" for r in chain))
    return group


def stop(snap, options):
    if options.pid:
        valid = {p for g in snap['groups'] for p in g['pids']}
        if options.target not in valid: raise ValueError('개발/자동화 그룹에 속한 PID만 종료할 수 있습니다.')
        plan = [r for r in snap['rows'] if r['pid'] == options.target]
    else:
        group = show_group(snap, options.target)
        plan = [r for r in snap['rows'] if r['pid'] in group['pids']]
    validate_plan(plan, ancestors(snap['rows']))
    word = 'KILL' if options.force else 'TERM'
    print(f"\n{word} 대상: " + ', '.join(str(r['pid']) for r in plan))
    print('대상 합계: ' + gib(sum(r['footprint'] or 0 for r in plan)))
    print('영향: 선택한 개발 서버의 연결·HMR·진행 중 요청 또는 자동화 탭·테스트가 중단됩니다.')
    if options.pid: print('개별 PID만 종료합니다. 부모가 재실행하거나 자식이 남을 수 있습니다.')
    if options.force: print('강제 종료는 저장·정리 처리를 건너뜁니다.')
    if not options.execute:
        print('미리보기만 실행했습니다. 실행하려면 같은 명령에 --execute를 추가하세요.'); return
    if not sys.stdin.isatty(): raise ValueError('종료 확인에는 대화형 터미널이 필요합니다. SSH는 -t 옵션을 사용하세요.')
    answer = input(f"실행하려면 {word} {options.target} 입력: ")
    if answer != f'{word} {options.target}': print('취소했습니다.'); return
    result = terminate(plan, processes, os.kill, ancestors(snap['rows']), options.force)
    time.sleep(1)
    remaining = {r['pid']: r for r in processes()}
    result['remaining'] = [r['pid'] for r in plan if r['pid'] in remaining and remaining[r['pid']]['start'] == r['start']]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('남은 PID/새 자식은 자동 강제 종료하지 않습니다. 목록을 새로 확인하세요.')
    if result['errors'] or result['remaining'] or result['new_children']: raise RuntimeError('일부 대상 또는 새 자식이 남았습니다.')


def remote_check():
    settings = rescue_settings.load()
    binary = '/Applications/Tailscale.app/Contents/MacOS/Tailscale'
    binary = binary if Path(binary).exists() else shutil.which('tailscale')
    if not binary: raise RuntimeError('Tailscale을 찾지 못했습니다.')
    result = run([binary, 'status', '--json'])
    if result.returncode: raise RuntimeError(result.stderr.strip())
    data = json.loads(result.stdout)
    print('Tailscale:', data.get('BackendState'), '/ Health:', data.get('Health') or [])
    addresses = data.get('TailscaleIPs', [])
    ipv4 = next((a for a in addresses if ':' not in a), None)
    profile = rescue_settings.connection(settings,ipv4)
    print('접속 별칭:', clean(profile['alias']))
    print('Mac 주소:', ipv4 or '없음')
    if profile['address_changed']:
        print('저장된 Tailscale 주소가 현재 Mac과 다릅니다. 현재 주소를 사용하며 .env.local 갱신이 필요합니다.')
    for host in ['127.0.0.1'] + ([ipv4] if ipv4 else []):
        for port, label in [(profile['port'], 'SSH'), (6768, 'Orca')]:
            try:
                with socket.create_connection((host, port), timeout=2): status = '연결 가능'
            except OSError: status = '연결 불가'
            print(f'{host}:{port} {label}: {status}')
    keyfile = Path.home() / '.ssh/authorized_keys'
    keys = [l for l in keyfile.read_text().splitlines() if l.strip() and not l.lstrip().startswith('#')] if keyfile.exists() else []
    print('authorized_keys 등록 줄 수:', len(keys))
    print('별도 기기:')
    for peer in data.get('Peer', {}).values():
        print(' ', clean(peer.get('HostName')), 'online=' + str(peer.get('Online')))
    print('아직 모바일 접속 검증 결과가 아닙니다. 모바일 Tailscale을 켜고 다음 명령으로 접속하세요:')
    if profile['address']:
        command=['ssh','-p',str(profile['port']),profile['username']+'@'+profile['address']]
        print('  '+shlex.join(command))
    print('호스트 키 지문 (모바일 최초 연결 시 대조):')
    host_keys = list(Path('/etc/ssh').glob('ssh_host_*_key.pub'))
    if not host_keys: print('  호스트 공개키가 없습니다. 원격 로그인 활성화 후 다시 확인하세요.')
    for key in host_keys:
        print(run(['ssh-keygen', '-lf', str(key)]).stdout.strip())


def main():
    parser = argparse.ArgumentParser(description='Mac 메모리·개발 세션 진단. 기본 실행은 읽기 전용입니다.')
    version_file = Path(__file__).resolve().with_name('VERSION')
    if not version_file.exists(): version_file = Path(__file__).resolve().parent.parent/'VERSION'
    parser.add_argument('--version', action='version', version='Rescue '+(version_file.read_text().strip() if version_file.exists() else 'development'))
    sub = parser.add_subparsers(dest='command')
    status = sub.add_parser('status', help='메모리·프로젝트 그룹 조회')
    status.add_argument('--json', action='store_true')
    watch = sub.add_parser('watch', help='반복 측정과 이전 측정 대비 변화')
    watch.add_argument('--interval', type=int, default=15)
    watch.add_argument('--count', type=int, default=0, help='0은 Ctrl-C까지')
    watch.add_argument('--log', help='최근 240회 시스템·그룹 기록을 남길 JSONL 파일')
    inspect = sub.add_parser('inspect', help='그룹의 PID·부모·작업 경로')
    inspect.add_argument('target', type=int)
    kill = sub.add_parser('stop', help='그룹 종료 미리보기; 실행은 --execute 및 문자 확인 필요')
    kill.add_argument('target', type=int, help='그룹 ROOT (또는 --pid와 사용할 PID)')
    kill.add_argument('--pid', action='store_true', help='자식 없이 PID 하나만')
    kill.add_argument('--execute', action='store_true')
    kill.add_argument('--force', action='store_true', help='SIGKILL, 별도 강제 종료 확인')
    sub.add_parser('remote-check', help='Tailscale·SSH·호스트 키 상태 점검')
    sub.add_parser('config', help='개인 설정 유효성 점검; 값은 마스킹')
    gui = sub.add_parser('gui', help='PC용 Rescue 화면 열기')
    choice = gui.add_mutually_exclusive_group()
    choice.add_argument('--stop', action='store_true', help='이전 웹 모니터만 종료; Mac 앱은 ⌘Q')
    choice.add_argument('--url', action='store_true', help='웹 버전 접속 주소 출력')
    choice.add_argument('--web', action='store_true', help='선택적으로 웹 버전 열기')
    choice.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    options = parser.parse_args()
    if sys.platform != 'darwin': parser.error('macOS 전용 도구입니다.')
    if os.getuid() == 0: parser.error('sudo 없이 본인 계정으로 실행하세요.')
    if options.command == 'gui':
        import rescue_gui
        if options.serve: rescue_gui.serve()
        elif options.stop or options.url or options.web: rescue_gui.launch(options.stop, options.url)
        else:
            app = Path.home()/'Applications/Rescue.app'
            if not app.exists(): parser.error('python3 scripts/install-rescue.py로 Mac 앱을 설치하세요.')
            subprocess.run(['open',str(app)],check=True)
        return
    if options.command == 'config':
        settings=rescue_settings.load()
        for key in rescue_settings.KEYS:
            value=settings[key]
            print(key+'='+('***' if value and key!='RESCUE_SSH_PORT' else value or '(자동 감지/기본값)'))
        print('설정 유효성: OK'); return
    if options.command == 'remote-check': remote_check(); return
    if options.command == 'watch':
        if options.interval < 5 or options.count < 0: parser.error('interval은 5초 이상, count는 0 이상이어야 합니다.')
        previous, count = None, 0
        while True:
            current = snapshot()
            if options.log: save_history(options.log, current)
            if sys.stdout.isatty(): print('\033[2J\033[H', end='')
            display(current, previous)
            previous = current; count += 1
            if options.count and count >= options.count: return
            time.sleep(options.interval)
    snap = snapshot()
    if options.command == 'inspect': show_group(snap, options.target)
    elif options.command == 'stop': stop(snap, options)
    elif getattr(options, 'json', False):
        # Full argv may contain tokens/prompts; never expose it in reports.
        for row in snap['rows']: row.pop('args', None)
        print(json.dumps(snap, ensure_ascii=False, indent=2))
    else: display(snap)


if __name__ == '__main__':
    try: main()
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print('오류: ' + clean(exc), file=sys.stderr); sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print('\n종료했습니다.'); sys.exit(130)
