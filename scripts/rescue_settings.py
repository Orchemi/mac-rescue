"""Small, non-executable private connection settings; never stores credentials."""
import getpass
import ipaddress
import os
from pathlib import Path
import re
import shlex

KEYS = ('RESCUE_HOST_ALIAS','RESCUE_SSH_USER','RESCUE_TAILSCALE_IP','RESCUE_SSH_PORT')
DEFAULTS = dict(RESCUE_HOST_ALIAS='',RESCUE_SSH_USER='',RESCUE_TAILSCALE_IP='',RESCUE_SSH_PORT='22')
MASKS = {'***','<masked>','REDACTED'}


def validate(values):
    result = {**DEFAULTS, **values}
    for key,value in result.items():
        if key not in KEYS: raise ValueError('지원하지 않는 Rescue 설정 키입니다.')
        if value in MASKS: result[key] = DEFAULTS[key]
        elif not isinstance(value,str) or len(value)>128 or any(not c.isprintable() for c in value):
            raise ValueError(key+': 설정 형식을 확인하세요.')
    user=result['RESCUE_SSH_USER']
    if user and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9._-]*',user): raise ValueError('RESCUE_SSH_USER: 계정 형식을 확인하세요.')
    address=result['RESCUE_TAILSCALE_IP']
    if address:
        try: ipaddress.ip_address(address)
        except ValueError: raise ValueError('RESCUE_TAILSCALE_IP: IP 주소 형식을 확인하세요.') from None
    port=result['RESCUE_SSH_PORT']
    if not port.isdigit() or not 1<=int(port)<=65535: raise ValueError('RESCUE_SSH_PORT: 1~65535 범위가 필요합니다.')
    return result


def parse_env(text):
    values={}
    for number,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'): continue
        if line.startswith('export '): line=line[7:].lstrip()
        key,separator,raw=line.partition('=')
        key=key.strip()
        if not separator or key not in KEYS: raise ValueError(f'설정 파일 {number}행: 지원하지 않는 키/형식입니다.')
        if key in values: raise ValueError(f'설정 파일 {number}행: 중복 키입니다.')
        try: parts=shlex.split(raw,comments=True,posix=True)
        except ValueError: raise ValueError(f'설정 파일 {number}행: 따옴표를 확인하세요.') from None
        if len(parts)>1: raise ValueError(f'설정 파일 {number}행: 공백이 있는 값은 따옴표로 감싸세요.')
        values[key]=parts[0] if parts else ''
    return validate(values)


def load(root=None,home=None,environ=None):
    home=Path(home) if home is not None else Path.home()
    root=Path(root) if root is not None else Path(__file__).resolve().parent.parent
    env=os.environ if environ is None else environ
    explicit=env.get('RESCUE_ENV_FILE')
    if explicit:
        path=Path(explicit).expanduser()
        if not path.is_file(): raise ValueError('RESCUE_ENV_FILE의 설정 파일을 찾을 수 없습니다.')
    else:
        source=root/'.env.local'
        path=source if source.is_file() else home/'.config/rescue/.env.local'
    values=parse_env(path.read_text()) if path.is_file() else dict(DEFAULTS)
    for key in KEYS:
        if key in env: values[key]=env[key]
    return validate(values)


def connection(values,live_address=None):
    values=validate(values)
    stored=values['RESCUE_TAILSCALE_IP']
    return dict(alias=values['RESCUE_HOST_ALIAS'] or '내 Mac',
                username=values['RESCUE_SSH_USER'] or getpass.getuser(),
                address=live_address or stored,port=int(values['RESCUE_SSH_PORT']),
                address_changed=bool(stored and live_address and stored!=live_address))
