"""Native app's private stdin/stdout bridge; no socket or shell command endpoint."""
import json
import os
import sys
import subprocess
sys.dont_write_bytecode = True
from rescue_gui import App


def dispatch(app, data):
    if not isinstance(data, dict): raise ValueError('JSON 객체가 필요합니다.')
    method = data.get('method')
    if method == 'status': return app.status()
    if method == 'plan': return app.preview(data.get('target'), data.get('mode'), data.get('force', False))
    if method == 'execute': return app.execute(data.get('id'), data.get('phrase'))
    raise ValueError('지원하지 않는 요청입니다.')


def main():
    if sys.platform != 'darwin' or os.getuid() == 0: raise SystemExit('Mac에서 sudo 없이 실행하세요.')
    app = App('private-stdio')
    while True:
        line = sys.stdin.buffer.readline(4097)
        if not line: break
        if len(line) > 4096: break
        try:
            result = {'data': dispatch(app, json.loads(line))}
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            result = {'error': str(exc)}
        try:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except BrokenPipeError: break


if __name__ == '__main__': main()
