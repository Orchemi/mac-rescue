# Mac 메모리 점검과 모바일 복구

`rescue`는 macOS에서 프로젝트별 개발 서버와 자동화 Chrome의 메모리를 조회하고,
선택한 실행 묶음을 종료하는 도구다. SwiftUI 네이티브 앱과 Python 3 표준 라이브러리 기반 조회 엔진을 사용한다.
Orca·Docker와 독립적으로 동작한다. 조회와 모니터링은 프로세스에 신호를 보내지 않는다.

## PC 화면과 짧은 명령

Mac에서는 `~/Applications/Rescue.app`을 열거나 `rescue gui`를 실행한다. SwiftUI로 만든
실제 macOS 앱이며, 브라우저·WebView·Electron 없이 기본 창과 표·검색·상세 패널을 사용한다.
macOS 14 이상에서 실행되며 `⌘R` 새로고침, `⌘Q` 종료를 지원한다.
Spotlight에서 Rescue로 검색하거나 Finder에서 앱을 Dock으로 끌어놓을 수 있다.

- 전체 상태: 메모리 압력, 개발/자동화 그룹 점유량, 스왑, 디스크 여유
- 실행 그룹: 프로젝트·ROOT·프로세스 수·포트·실행 기간·검토 근거
- 검색과 필터: 프로젝트/PID, 2GiB 이상, 24시간 이상, 메모리순/오래된순/이름순
- 상세: 부모 경로와 구성 프로세스, 개별 또는 그룹 종료
- 종료: 실제 PID 목록을 먼저 보여주고 문구 입력 후 실행한다. 60초 이후 미리보기는 만료된다.
- 전체 프로세스: 앱/시스템을 포함해 조회한다. 개발/자동화 외의 앱과 시스템은 조회 전용이다.

앱 전용 Python 도우미와 표준 입력·출력 파이프로 통신하며 네트워크 포트를 열지 않는다.
창을 닫거나 `⌘Q`로 앱을 종료하면 조회 도우미도 끝난다. 열린 앱이 활성 상태일 때 15초마다
갱신한다. 모바일에서는 SSH의 `rescue`를 사용한다.

기존 웹 화면은 선택 옵션 `rescue gui --web` / `--url`로 남겨두었다. 이 옵션만
`127.0.0.1` 임의 포트와 실행별 인증값을 사용한다. `rescue gui --stop`은 웹 모니터만
종료하며, 네이티브 앱은 창 닫기 또는 `⌘Q`로 종료한다.

## 설치·업데이트·포맷 후 복원

소스와 설치기는 mac-rescue 저장소에 둔다. `~/.local/bin`은 원본 보관 장소가 아니라 실행 명령
설치 위치다. **포맷 전에 변경사항을 원격 저장소에 push해 두어야 한다.** 설치기는 commit/push를 대신하지 않는다.
원격 저장소: `git@github.com:Orchemi/mac-rescue.git` (비공개).

1. 새 Mac에 Python 3, Git, Swift 컴파일러가 포함된 Xcode Command Line Tools를 준비한다.
   최초 설치 시 SwiftUI 앱을 로컬에서 빌드하므로 몇 분 걸릴 수 있다.
2. GitHub 접근 권한을 설정하고 `Orchemi/mac-rescue`를 clone한다. 해당 폴더에서 실행한다.

```sh
python3 scripts/install-rescue.py
```

3. 새 터미널이나 Termius 연결에서 `rescue`를 입력한다. 기존 연결에는 한 번만 다음을 실행한다.

```sh
export PATH="$HOME/.local/bin:$PATH"
```

4. GUI는 Rescue 앱을 연다. 포맷 후 Tailscale 로그인과 macOS 원격 로그인도 다시 설정한다.
   SSH 호스트 키는 바뀔 수 있으므로 새 Mac의 지문을 확인하고 모바일의 이전 기록을 갱신한다.

설치기는 다음 항목을 관리한다. 다른 이름의 프로그램·기존 앱은 덮어쓰지 않으며 반복 실행할 수 있다.

| 위치 | 역할 |
|---|---|
| `~/.local/bin/rescue` | 짧은 CLI 실행 명령 |
| `~/.local/bin/mac-rescue` | 기존 명령 호환 |
| `~/.local/share/rescue/versions/` | 소스 해시별 설치본, 이전 버전 보존 |
| `~/.local/share/rescue/current` | 현재 설치본 링크 |
| `~/Applications/Rescue.app` | 네이티브 실행 파일·아이콘·조회 엔진 |
| `~/.zprofile`의 Rescue PATH 블록 | 새 로그인 셸에서 짧은 명령 인식 |
| `~/.local/state/rescue/` | 로컬 GUI 포트·인증값·실행 잠금; 백업 불필요 |
| `~/.config/rescue/.env.local` | 개인 접속 설정, 0600 권한, 앱 번들·Git 추적 제외 |

업데이트할 때 Rescue 앱을 `⌘Q`로 닫고(웹 버전은 `rescue gui --stop`) 설치기를 다시
실행한 후 Rescue 앱을 연다. 사용자 작업 앱은 종료하지 않는다.

### 개인 환경변수

`.env.local.example`은 개인 값이 `***`로 마스킹된 스키마다. `.env.local`에 실제 별칭,
SSH 사용자, Tailscale IP와 SSH 포트를 설정한다. `rescue config`로 마스킹된 상태에서
유효성을 확인한다. 기본값이면 현재 OS 계정과 Tailscale 주소를 자동 감지한다.

설치기는 `.env.local`을 별도 개인 설정 디렉터리로 복사한다. 설정이 없는 설치/업데이트는
기존 개인 설정을 보존한다. `.env.local` 변경 후 설치기를 다시 실행하면 설치본에도 반영된다.
`RESCUE_ENV_FILE`로 특정 파일을 지정하거나 `RESCUE_*` 환경변수로 일시 덮어쓸 수 있다.

Obsidian `$sync-env mac-rescue`는 `projects/tools/mac-rescue/env.md`의
`## Root` → `### .env.local`에 실값을 보관한다. 새 기기에서 이 내용을 프로젝트의
`.env.local`로 복원하고 설치한다. 해당 vault의 비공개 여부를 먼저 확인한다.
SSH 비밀번호와 개인키는 이 환경 파일의 관리 대상이 아니다.

## 빠른 사용

기본 명령은 `rescue`다. 기존 `mac-rescue`도 같은 기능을 제공한다.
소스에서 실행하려면 `python3 scripts/mac-rescue.py`를 사용한다.

```sh
rescue
rescue gui
rescue watch --interval 30
rescue watch --interval 60 --log ~/mac-rescue-history.jsonl
rescue remote-check
```

`watch`는 Ctrl-C로 끝낸다. 로그 옵션은 최근 240회만 보관한다. 60초 간격이면 약 4시간이며,
프로젝트 경로·메모리·포트·PID는 기록하지만 명령 인수·환경 변수는 기록하지 않는다.
백그라운드 서비스는 자동 설치하지 않는다. SSH 연결을 닫으면 계속 수집된다고 보장하지 않는다.
`status --json`은 후속 분석용 현재 스냅샷을 출력한다.

## 숫자와 검토 근거

표의 `G`는 GiB다. 메모리는 Darwin `physical footprint`이며 RSS와 다르다.
압축·스왑되는 프로세스는 RSS가 작아도 footprint가 클 수 있다. 그룹 합계는 해당 실행 트리에
속한 프로세스들의 footprint 합계이며, 종료 후 바로 확보될 물리 RAM의 양이 아니다.
권한 때문에 측정할 수 없는 프로세스는 `?`, 불완전한 그룹 합계는 `*`로 표시한다.

- `2GiB 이상`: 메모리를 많이 쓰는 검토 대상이다.
- `24시간 이상`: 장기간 실행됐다. 사용이 끝났다는 뜻은 아니다.
- `부모 소실/분리`: 부모가 launchd(PID 1)다. 정상적인 데몬 분리도 포함한다.
- `같은 프로젝트의 여러 Chrome 세션`: QA 병렬 실행일 수 있으므로 세션별로 확인한다.

실행 시간이나 낮은 CPU만으로 stale을 확정하지 않는다. `watch`의 증가량도 탭·자식 프로세스
추가와 정상 캐시를 포함하므로 메모리 누수 확정 근거로 사용하지 않는다.
자동화 Chrome은 `Google Chrome for Testing`을 감지한다. 일반 Chrome·다른 브라우저는
그룹 종료 대상으로 자동 분류하지 않는다. 개발 서버는 Node/Next/Vite/Turbo/Bun/Deno의
실행 명령 및 TCP 리스너를 기반으로 감지하며 모든 개발 도구를 포괄하지 않는다.

## 확인 후 종료

현재 목록의 `ROOT`를 사용한다. 아래 `12345`는 예시이며 오래된 PID를 그대로 복사하지 않는다.

```sh
mac-rescue inspect 12345
mac-rescue stop 12345
mac-rescue stop 12345 --execute
```

`inspect`는 작업 디렉터리·포트·PID/부모 PID와 Orca/셸까지의 부모 경로를 보여준다.
`stop`은 기본적으로 미리보기만 한다. `--execute`를 붙여도 실제 터미널에서 `TERM 12345`를
입력해야 실행한다. SSH 명령으로 직접 호출할 때는 `ssh -t`로 터미널을 할당한다.

그룹 종료는 실행 launcher부터 선택한 자식들에게 SIGTERM을 보낸다. 개발 사이트·HMR·API 요청
또는 자동화 탭·테스트가 중단된다. 파일이나 DB 볼륨은 삭제하지 않는다. 서버 자체가 종료 시
수행하는 저장·정리 동작은 해당 서버에 달려 있다. 실행 중인 테스트·요청이 끝났는지 먼저 확인한다.

```sh
mac-rescue stop 12345 --pid
mac-rescue stop 12345 --pid --execute
mac-rescue stop 12345 --force --execute
```

`--pid`는 선택한 프로세스 하나만 종료한다. 부모가 재실행하거나 자식이 남을 수 있다.
`--force`는 `KILL 12345`를 별도로 입력해야 하며 저장·정리 처리를 건너뛴다.
TERM 실패 후 자동으로 KILL을 보내지 않는다. 살아남은 PID나 새 자식은 다시 조회한다.

안전 경계:

- 종료 대상은 현재 감지된 개발/자동화 그룹 또는 그 구성원이다. 프로젝트 전체 이름으로
  `pkill`, 음수 PGID kill을 실행하지 않는다.
- 다른 사용자, PID 1, SSH, Tailscale, Orca, Docker, 주요 대화형 셸, Codex/Claude와
  현재 명령의 조상 프로세스는 보호한다. 그룹 안에 보호 대상이 있으면 전체 요청을 거부한다.
- PID와 시작 시각·사용자·실행 파일을 확인 후 신호 직전 재확인한다. 미리보기 뒤 생긴
  자식은 자동으로 종료 범위에 추가하지 않는다. macOS의 PID 기반 신호 전달에는 마지막
  확인과 신호 사이의 아주 짧은 경쟁 구간이 남으므로 원자적인 종료 보장은 아니다.
- sudo로 실행하지 않는다. 상위 시스템 프로세스 전체가 보이지 않을 수 있다.

## 모바일 SSH 연결 준비

Mac별 접속 설정은 Git에서 제외되는 `.env.local`에 보관한다. 마스킹된
`.env.local.example`을 참고하고, `rescue remote-check`로 현재 주소·계정을 확인한다.
실제 값은 공개 문서·커밋 메시지·스크린샷에 넣지 않는다.

1. Mac에서 **시스템 설정 → 일반 → 공유 → 원격 로그인**을 켠다.
   **다음 사용자만**에서 사용할 Mac 계정을 선택한다. 관리자 인증은 Mac에서 직접 한다.
   이 진단 도구 때문에 원격 사용자의 전체 디스크 접근 권한을 추가할 필요는 없다.
2. 모바일에서 Tailscale을 같은 계정으로 연결한다. SSH 앱이 없다면 Termius 같은 앱을 설치한다.
3. 모바일 SSH 앱에서 접속용 키를 생성하고 공개키만 Mac에 등록한다.
   개인키와 Mac 비밀번호는 채팅에 보내지 않는다. 키가 아직 없다면 원격 로그인이 허용하는
   Mac 계정 비밀번호 방식으로 먼저 접속할 수도 있다. 비밀번호는 모바일 앱에 직접 입력한다.
4. SSH 호스트를 `rescue remote-check`에 표시된 주소·포트·사용자로 등록한다.
5. Mac에서 `mac-rescue remote-check`로 호스트 키 지문을 확인하고 모바일 최초 연결 화면과
   대조한다. 포트가 열렸다는 사실만으로 모바일 인증 성공이 검증된 것은 아니다.
6. 모바일 Wi-Fi를 끄고 이동통신+Tailscale로 접속해 아래 명령이 되는지 확인한다.

```sh
whoami
rescue remote-check
rescue
```

Tailscale GUI판에서는 macOS 원격 로그인(OpenSSH)을 사용한다. `tailscale up --ssh`로
별도의 SSH 서버를 켜려 하지 않는다. 라우터 포트 포워딩은 필요 없다. macOS 원격 로그인은
LAN에서도 서비스를 열 수 있으므로 Tailscale 전용 바인딩 설정으로 오해하지 않는다.

## Orca 문제 발생 시

1. 모바일 SSH에 접속한다. 메모리 압력과 큰 개발 그룹부터 확인한다.
2. 작업 중이 아닌 그룹을 선택해 미리보기 후 정상 종료한다. 현재도 필요한 DB·터미널은 유지한다.
3. Orca 창이 사라진 경우 `open -a Orca`로 다시 연다. GUI가 응답하지 않는 상태라면 이 명령만으로
   재시작되지 않는다. 저장 중인 작업을 확인한 뒤 별도로 Orca 본체 재시작을 판단한다.
4. `pkill -f Orca`를 사용하지 않는다. 터미널 데몬까지 종료해 개발 세션을 끊을 수 있다.

이 경로는 **Orca UI 장애**와 독립적이다. Mac 전체 멈춤·네트워크 단절·잠자기·전원 꺼짐까지
복구하지는 못한다. 장시간 무인 사용은 전원 연결과 잠자기 설정을 별도로 검증한다.
FileVault 재부팅 후 잠금 해제 전 접속도 보장하지 않는다.

## 참고

- [Apple 원격 로그인 설정](https://support.apple.com/en-lamr/guide/mac-help/mchlp1066/mac)
- [Tailscale SSH 지원 범위](https://tailscale.com/docs/features/tailscale-ssh)
- [Termius Android](https://www.termius.com/free-ssh-client-for-android)
