"""Loopback-only Rescue UI. Every API requires a per-launch capability token."""
import fcntl
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rescue_core', HERE / 'mac-rescue.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def public_row(row, can_stop=False):
    return {**{k:v for k,v in row.items() if k != 'args'}, 'can_stop': can_stop}


def authorized(host, origin, token, expected, port):
    address = f'127.0.0.1:{port}'
    return (host == address and origin in (None, 'http://' + address)
            and bool(token) and hmac.compare_digest(token, expected))


class App:
    def __init__(self, token):
        self.token = token
        self.plans = {}
        self.history = []
        self.cached = None
        self.cached_at = 0
        self.last_request = time.monotonic()
        self.running = True

    def status(self):
        if self.cached and time.monotonic()-self.cached_at < 3: return self.cached
        snap = core.snapshot()
        ancestors = core.ancestors(snap['rows'])
        valid = {p for g in snap['groups'] for p in g['pids']}
        snap['rows'] = [public_row(r, r['pid'] in valid and not core.protected(r) and r['pid'] not in ancestors)
                        for r in snap['rows']]
        by_pid = {r['pid']:r for r in snap['rows']}
        for g in snap['groups']:
            g['can_stop'] = all(by_pid[p]['can_stop'] for p in g['pids'])
        self.history.append({'time':snap['time'], **snap['system']})
        self.history = self.history[-120:]
        snap['history'] = list(self.history)
        self.cached, self.cached_at = snap, time.monotonic()
        return snap

    def preview(self, target, mode, force):
        if type(target) is not int or mode not in ('group','pid') or type(force) is not bool:
            raise ValueError('잘못된 종료 요청입니다.')
        snap = core.snapshot()
        group = next((g for g in snap['groups'] if (g['root'] == target if mode == 'group' else target in g['pids'])), None)
        if not group: raise ValueError('대상이 사라졌거나 종료 가능한 개발/자동화 그룹이 아닙니다.')
        selected = group['pids'] if mode == 'group' else [target]
        rows = [r for r in snap['rows'] if r['pid'] in selected]
        core.validate_plan(rows, core.ancestors(snap['rows']))
        phrase = ('강제 종료 ' if force else '종료 ') + str(target)
        ident = secrets.token_urlsafe(24)
        self.plans = {k:v for k,v in self.plans.items() if v['expires'] > time.monotonic()}
        if len(self.plans) >= 32: self.plans.pop(next(iter(self.plans)))
        self.plans[ident] = dict(rows=rows, expires=time.monotonic()+60, phrase=phrase, force=force)
        return dict(id=ident, phrase=phrase, seconds=60, force=force, mode=mode, target=target,
                    project=group['project'], rows=[public_row(r) for r in rows],
                    footprint=sum(r['footprint'] or 0 for r in rows))

    def execute(self, ident, phrase):
        if not isinstance(ident,str) or not isinstance(phrase,str): raise ValueError('잘못된 확인 값입니다.')
        plan = self.plans.get(ident)
        if not plan or plan['expires'] < time.monotonic(): raise ValueError('미리보기가 만료됐습니다. 다시 확인해 주세요.')
        if phrase != plan['phrase']: raise ValueError('확인 문구가 일치하지 않습니다.')
        del self.plans[ident]
        result = core.terminate(plan['rows'], core.processes, os.kill,
                                core.ancestors(core.processes()), plan['force'])
        time.sleep(.5)
        latest = {r['pid']:r for r in core.processes()}
        result['remaining'] = [r['pid'] for r in plan['rows'] if r['pid'] in latest and latest[r['pid']]['start'] == r['start']]
        self.cached = None
        return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def reply(self, code, payload, content_type='application/json; charset=utf-8'):
        body = payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass

    def handle_request(self):
        app = self.server.app
        port = self.server.server_port
        if self.headers.get('Host') != f'127.0.0.1:{port}': self.reply(403,{'error':'접속 주소가 올바르지 않습니다.'}); return
        static = {'/':('index.html','text/html; charset=utf-8'), '/app.js':('app.js','text/javascript; charset=utf-8'),
                  '/style.css':('style.css','text/css; charset=utf-8'), '/icon.svg':('icon.svg','image/svg+xml')}
        if self.command == 'GET' and self.path in static:
            name, mime = static[self.path]
            self.reply(200,(HERE/'rescue-ui'/name).read_bytes(),mime); return
        if not authorized(self.headers.get('Host'), self.headers.get('Origin'),
                          self.headers.get('X-Rescue-Token'),app.token,port):
            self.reply(403,{'error':'인증이 만료됐습니다. Rescue 앱 또는 rescue gui로 다시 열어 주세요.'}); return
        app.last_request = time.monotonic()
        try:
            if self.command == 'GET' and self.path == '/api/status':
                self.reply(200,app.status()); return
            if self.command == 'GET' and self.path == '/api/health':
                self.reply(200,{'ok':True}); return
            if self.command == 'POST':
                if self.headers.get('Origin') not in (None,f'http://127.0.0.1:{port}'):
                    self.reply(403,{'error':'잘못된 Origin'}); return
                if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                    self.reply(415,{'error':'JSON 요청이 필요합니다.'}); return
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 4096: self.reply(413,{'error':'요청 크기가 올바르지 않습니다.'}); return
                data = json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise ValueError('JSON 객체가 필요합니다.')
                if self.path == '/api/plan': self.reply(200,app.preview(data.get('target'),data.get('mode'),data.get('force',False))); return
                if self.path == '/api/execute': self.reply(200,app.execute(data.get('id'),data.get('phrase'))); return
                if self.path == '/api/quit': app.running=False; self.reply(200,{'ok':True}); return
            self.reply(404,{'error':'요청을 찾을 수 없습니다.'})
        except (ValueError,RuntimeError,OSError,subprocess.TimeoutExpired) as exc:
            self.reply(409,{'error':str(exc)})

    do_GET = handle_request
    do_POST = handle_request


def state_dir():
    path = Path.home()/'.local/state/rescue'
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink() or path.stat().st_uid != os.getuid(): raise ValueError('Rescue 상태 디렉터리 소유권을 확인하세요.')
    path.chmod(0o700)
    return path


def request_state(state, route='/api/health', body=None):
    port = state.get('port')
    if type(port) is not int or not 1 <= port <= 65535: raise ValueError('잘못된 GUI 포트입니다.')
    req = urllib.request.Request(f'http://127.0.0.1:{port}{route}',
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'X-Rescue-Token':state['token'],'Content-Type':'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req,timeout=3) as response: return json.load(response)


def serve():
    directory = state_dir()
    with open(directory/'server.lock','a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        token = secrets.token_urlsafe(32)
        server = HTTPServer(('127.0.0.1',0),Handler)
        server.timeout=1
        server.app=App(token)
        state = dict(pid=os.getpid(),port=server.server_port,token=token)
        path=directory/'gui.json'
        with open(directory/'gui.tmp','w') as stream:
            os.chmod(stream.name,0o600);json.dump(state,stream)
        os.replace(directory/'gui.tmp',path)
        try:
            while server.app.running and time.monotonic()-server.app.last_request < 1800:
                server.handle_request()
        finally:
            server.server_close()
            if path.exists() and json.loads(path.read_text()).get('token') == token: path.unlink()


def launch(stop=False, print_url=False):
    directory=state_dir()
    with open(directory/'launch.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=directory/'gui.json'
        state=None
        if path.exists():
            try:
                candidate=json.loads(path.read_text())
                if request_state(candidate)['ok']: state=candidate
            except (OSError,ValueError,KeyError): pass
        if stop:
            if state: request_state(state,'/api/quit',{}); print('Rescue 모니터를 종료했습니다.')
            else: print('실행 중인 Rescue 모니터가 없습니다.')
            return
        if not state:
            subprocess.Popen([sys.executable,str(HERE/'mac-rescue.py'),'gui','--serve'],
                             stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                             start_new_session=True,close_fds=True)
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                try:
                    state=json.loads(path.read_text())
                    if request_state(state)['ok']: break
                except (OSError,ValueError,KeyError): state=None
                time.sleep(.1)
            if not state: raise RuntimeError('GUI 서버를 시작하지 못했습니다.')
        url=f"http://127.0.0.1:{state['port']}/#{state['token']}"
        if print_url: print(url)
        else:
            result=subprocess.run(['open',url])
            if result.returncode: raise RuntimeError('브라우저를 열지 못했습니다. rescue gui --url로 주소를 확인하세요.')
            print('Rescue를 브라우저에서 열었습니다. 종료: rescue gui --stop')
