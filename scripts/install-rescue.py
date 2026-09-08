#!/usr/bin/env python3
"""Rebuild Rescue launchers from the version-controlled source; no sudo required."""
import hashlib
import math
import os
from pathlib import Path
import plistlib
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from rescue_settings import parse_env

SOURCE = Path(__file__).resolve().parent
FILES = ['mac-rescue.py','rescue_gui.py','rescue_native.py','rescue_settings.py','rescue-native/Rescue.swift','rescue-ui/index.html','rescue-ui/style.css','rescue-ui/app.js','rescue-ui/icon.svg']
MARKER = '# Rescue managed launcher v1'
VERSION = (SOURCE.parent/'VERSION').read_text().strip()
ENV_SOURCE = SOURCE.parent/'.env.local'


def build_native(version):
    binary = version/'Rescue'
    if not binary.exists():
        pending = version/'Rescue.building'
        sdk = subprocess.run(['xcrun','--sdk','macosx','--show-sdk-path'],check=True,
                             capture_output=True,text=True).stdout.strip()
        subprocess.run(['xcrun','swiftc','-sdk',sdk,'-parse-as-library','-O','-target',
                        platform.machine()+'-apple-macosx14.0',str(version/'rescue-native/Rescue.swift'),
                        '-o',str(pending)],check=True)
        pending.replace(binary)
    return binary


def icon_png():
    size=256
    raw=bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            dx,dy=x-127.5,y-127.5
            corner=math.hypot(max(abs(dx)-62,0),max(abs(dy)-62,0))
            alpha=255 if corner<=64 else 0
            radius=math.hypot(dx,dy)
            angle=math.atan2(dy,dx)
            diagonal=abs((angle-math.pi/4+math.pi/4)%(math.pi/2)-math.pi/4)<.18
            color=(231,241,233) if 60<=radius<=92 and not diagonal else (23,102,83)
            raw.extend((*color,alpha))
    def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(raw)))+chunk(b'IEND',b'')


def install(home=None):
    home=Path(home) if home else Path.home()
    private_text = ENV_SOURCE.read_text() if ENV_SOURCE.is_file() else None
    if private_text is not None: parse_env(private_text)
    config_dir=home/'.config/rescue'
    if config_dir.is_symlink() or (config_dir/'.env.local').is_symlink():
        raise ValueError('개인 설정 경로의 심볼릭 링크를 덮어쓰지 않습니다.')
    prefix=home/'.local/share/rescue'
    bindir=home/'.local/bin'
    app=home/'Applications/Rescue.app'
    for name in ('rescue','mac-rescue'):
        path=bindir/name
        if path.exists() or path.is_symlink():
            if path.is_symlink(): raise ValueError(f'기존 링크를 덮어쓰지 않습니다: {path}')
            text=path.read_text()
            legacy=name=='mac-rescue' and text.startswith('#!/usr/bin/env python3\n"""macOS process-footprint monitor')
            if MARKER not in text and not legacy: raise ValueError(f'다른 프로그램이 사용하는 명령입니다: {path}')
    if app.exists() and not (app/'Contents/Resources/rescue-managed').exists():
        raise ValueError(f'기존 앱을 덮어쓰지 않습니다: {app}')
    current=prefix/'current'
    if current.exists() and not current.is_symlink(): raise ValueError(f'설치 경로가 일반 파일/폴더입니다: {current}')
    digest=hashlib.sha256(VERSION.encode())
    for name in FILES: digest.update(name.encode());digest.update((SOURCE/name).read_bytes())
    version=prefix/'versions'/digest.hexdigest()[:16]
    for name in FILES:
        dest=version/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        payload=(SOURCE/name).read_bytes()
        if dest.exists() and dest.read_bytes()!=payload: raise ValueError('같은 버전 경로에 다른 파일이 있습니다.')
        dest.write_bytes(payload)
    (version/'VERSION').write_text(VERSION+'\n')
    native = build_native(version)
    prefix.mkdir(parents=True,exist_ok=True)
    pending=prefix/'current.next'
    if pending.exists() or pending.is_symlink(): raise ValueError('이전 설치가 남아 있습니다: current.next')
    pending.symlink_to(version, target_is_directory=True)
    pending.replace(current)
    bindir.mkdir(parents=True,exist_ok=True)
    import shlex
    launcher=f'#!/bin/sh\n{MARKER}\nexec {shlex.quote(sys.executable)} {shlex.quote(str(current/"mac-rescue.py"))} "$@"\n'
    for name in ('rescue','mac-rescue'):
        path=bindir/name;path.write_text(launcher);path.chmod(0o755)
    executable=app/'Contents/MacOS/Rescue'
    executable.parent.mkdir(parents=True,exist_ok=True)
    temporary=executable.with_suffix('.next')
    shutil.copy2(native,temporary);temporary.chmod(0o755);temporary.replace(executable)
    resources=app/'Contents/Resources';resources.mkdir(parents=True,exist_ok=True)
    engine=resources/'engine';engine.mkdir(parents=True,exist_ok=True)
    for name in ('mac-rescue.py','rescue_gui.py','rescue_native.py','rescue_settings.py','VERSION'): shutil.copy2(version/name,engine/name)
    with open(resources/'Engine.plist','wb') as stream: plistlib.dump({'Python':sys.executable},stream)
    (resources/'rescue-managed').write_text('Rescue installer v1\n')
    png=icon_png()
    element=b'ic08'+struct.pack('>I',len(png)+8)+png
    (resources/'Rescue.icns').write_bytes(b'icns'+struct.pack('>I',len(element)+8)+element)
    info={'CFBundleName':'Rescue','CFBundleDisplayName':'Rescue','CFBundleIdentifier':'dev.horbis.rescue',
          'CFBundleVersion':VERSION,'CFBundleShortVersionString':VERSION,'CFBundlePackageType':'APPL',
          'CFBundleExecutable':'Rescue','CFBundleIconFile':'Rescue.icns','LSMinimumSystemVersion':'14.0','NSHighResolutionCapable':True}
    with open(app/'Contents/Info.plist','wb') as stream: plistlib.dump(info,stream)
    # Only manage a clearly delimited PATH block; preserve the rest of user configuration.
    profile=home/'.zprofile'
    block='\n# >>> Rescue PATH >>>\nexport PATH="$HOME/.local/bin:$PATH"\n# <<< Rescue PATH <<<\n'
    original=profile.read_text() if profile.exists() else ''
    if '# >>> Rescue PATH >>>' not in original:
        profile.write_text(original+block)
    if private_text is not None:
        config_dir.mkdir(parents=True,exist_ok=True,mode=0o700);config_dir.chmod(0o700)
        with tempfile.NamedTemporaryFile(mode='w',dir=config_dir,delete=False) as stream:
            stream.write(private_text);pending_config=Path(stream.name)
        pending_config.chmod(0o600);pending_config.replace(config_dir/'.env.local')
    return dict(command=str(bindir/'rescue'),app=str(app),version=str(version))


if __name__=='__main__':
    if sys.platform!='darwin' or os.getuid()==0: raise SystemExit('Mac에서 sudo 없이 실행하세요.')
    try:
        result=install()
        print('Rescue 설치 완료')
        for key,value in result.items(): print(f'{key}: {value}')
        print('새 터미널/SSH에서: rescue | PC 화면: rescue gui 또는 Rescue 앱')
        print('기존 터미널/SSH에서 즉시 사용: export PATH="$HOME/.local/bin:$PATH"')
        print('원격 백업은 Git 커밋·푸시 완료 여부를 별도로 확인하세요.')
    except (ValueError,OSError,subprocess.CalledProcessError) as exc: raise SystemExit(str(exc))
