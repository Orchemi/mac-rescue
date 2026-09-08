# Rescue

Mac 메모리 문제를 **프로젝트 실행 그룹** 단위로 확인하고, 사용자가 선택한 프로세스만
종료하는 작은 도구입니다. SwiftUI 네이티브 앱과 SSH에서 쓰는 `rescue` 명령을 제공합니다.

## 설치와 실행

macOS 14 이상, Python 3, Xcode Command Line Tools가 필요합니다.

```sh
python3 scripts/install-rescue.py
```

- Mac: `~/Applications/Rescue.app` 또는 `rescue gui`. Dock에 추가할 수 있습니다.
- Termius로 SSH 접속한 뒤: `rescue` 또는 `rescue watch`.
- 연결 점검: `rescue remote-check`.
- 앱 종료: 창 닫기 또는 `⌘Q`. 관찰하던 개발 서버는 계속 실행됩니다.

설치기는 Swift 앱을 빌드하고 짧은 명령을 설치합니다. 기존 앱·다른 명령을 덮어쓰지 않으며
반복 실행할 수 있습니다. 현재 로그인 셸에 명령이 아직 없다면 새 터미널/SSH를 열어 주세요.

## 개인 설정과 Obsidian 복원

`.env.local.example`의 개인 값은 모두 `***`로 마스킹되어 있습니다. 이를 `.env.local`로
복사하고 필요하면 실제 값을 입력합니다. `***`를 유지하면 자동 감지/기본값을 사용합니다.

| 키 | 용도 |
|---|---|
| `RESCUE_HOST_ALIAS` | 모바일 SSH 앱에서 쓰는 별칭 |
| `RESCUE_SSH_USER` | Mac의 짧은 로그인 계정, 미설정 시 현재 계정 |
| `RESCUE_TAILSCALE_IP` | 보관할 접속 주소, 현재 Mac 주소가 다르면 현재 값을 우선하고 안내 |
| `RESCUE_SSH_PORT` | SSH 포트, 기본값 22 |

실값은 Git에서 제외합니다. 설치기는 `.env.local`을 `~/.config/rescue/.env.local`에
소유자만 읽고 쓸 수 있는 0600 권한으로 복사하며, 앱 번들과 버전별 소스에는 넣지 않습니다.
`rescue config`는 값을 마스킹해 검증하고, `rescue remote-check`는 실제 접속 정보를 표시합니다.

설정 우선순위는 환경변수 → 명시한 `RESCUE_ENV_FILE` 또는 소스의 `.env.local` → 설치된
개인 설정 → 기본값입니다. 파일의 셸 명령·변수 치환은 실행하지 않습니다.

Obsidian 연동 시 `$sync-env mac-rescue`의 대상은 `projects/tools/mac-rescue/env.md`의
`## Root` / `### .env.local`입니다. 해당 vault는 비공개여야 합니다. 이 노트는 공개 가능한
코드 저장소와 별도로 관리합니다. 비밀번호·개인키는 환경변수에도 보관하지 않습니다.

## 확인할 수 있는 것

- 실제 RAM, 메모리 압력, 압축 메모리, 스왑, 디스크 여유
- 프로젝트별 개발 서버·자동화 Chrome의 메모리, 실행 기간, 포트, 부모·자식 PID
- 검색·필터·정렬과 개별/그룹 종료 미리보기
- 정확한 확인 문구, 60초 만료, PID 재사용·보호 대상 검증

오래됐거나 메모리가 크다는 이유로 자동 종료하지 않습니다. 전체 프로세스를 조회하지만
종료는 감지된 본인 개발/자동화 그룹으로 제한합니다. Orca·SSH·Tailscale·Docker와 시스템
프로세스는 보호합니다. footprint 합계는 종료 후 확보되는 물리 RAM과 다릅니다.

기본 앱은 브라우저 없이 전용 파이프 도우미로 실행되며 네트워크 포트를 열지 않습니다.
기존 로컬 웹 화면은 `rescue gui --web`으로 선택할 수 있습니다.

## 포맷 후 복원

이 저장소의 변경사항을 먼저 GitHub에 push해 두세요. 새 Mac에서 다음을 실행하세요:

```sh
mkdir -p ~/Desktop/repositories/tools
cd ~/Desktop/repositories/tools
git clone https://github.com/Orchemi/mac-rescue.git mac-rescue
cd mac-rescue
# 비공개 Obsidian env.md에서 .env.local을 복원한 뒤 설치합니다.
python3 scripts/install-rescue.py
```

Tailscale 로그인과 Mac 원격 로그인은 다시 설정해야 합니다. 이 저장소에 SSH 키나 비밀번호는
보관하지 않습니다. Mac 전체 멈춤·절전·FileVault 재부팅 잠금의 복구는 SSH만으로 보장하지 않습니다.

[사용·복원 안내](docs/mac-rescue.md) · [변경 기록](CHANGELOG.md)

## 개발

```sh
bash scripts/verify.sh
python3 scripts/install-rescue.py
```

`VERSION`과 `CHANGELOG.md`로 SemVer를 기록하고 Git 태그 `v1.0.0` 형태로 기준점을 남깁니다.
설치 산출물은 로컬에서 만들며 원격 저장소에는 소스와 검증 절차를 보관합니다.
