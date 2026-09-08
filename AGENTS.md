# mac-rescue

이 파일은 Claude/Codex 공통 프로젝트 사실·컨벤션의 정본이다. CLAUDE.md는 이 파일을 가져온다.

## 제품과 코드 지도

macOS 14+ 전용 메모리·프로세스 모니터와 SSH 복구 CLI. Python 3 표준 라이브러리와
SwiftUI/AppKit을 사용한다. Node 패키지 매니저, DB, 웹 호스팅은 필요하지 않다.

| 영역 | 파일 |
| --- | --- |
| 수집·프로세스 분류·CLI | `scripts/mac-rescue.py` |
| 종료 미리보기·실행·선택형 웹 UI | `scripts/rescue_gui.py`, `scripts/rescue-ui/` |
| 네이티브 stdin/stdout 프로토콜 | `scripts/rescue_native.py` |
| Mac 화면 | `scripts/rescue-native/Rescue.swift` |
| 환경설정 | `scripts/rescue_settings.py` |
| 설치·업데이트 | `scripts/install-rescue.py` |

## 동작 계약

- 기본 GUI는 네이티브 앱이며 도우미와 전용 파이프로 통신한다. 웹 UI는 명시적으로 선택한다.
- 프로세스 종료는 PID 정체성·시작 시간·소유자·보호 대상·확인 문구·만료를 재검증한다.
  UI에서 확인했더라도 실행 직전 백엔드 검증을 생략하지 않는다.
- 오래 실행됐거나 메모리가 크다는 이유만으로 stale/누수를 확정하거나 자동 종료하지 않는다.
- 테스트는 자체 생성한 임시 프로세스만 종료한다. 사용자 앱, 로그인 항목, SSH/Tailscale 설정은
  테스트 대상으로 변경하지 않는다. 실제 종료 요청은 대상과 영향을 설명한 뒤 사용자 범위에 따른다.
- 설치 명령은 사용자 앱·CLI·설정·셸 PATH를 변경한다. 빌드 검증에는 설치 명령 대신 아래 명령을 쓴다.

## 검증 명령

저장소 루트에서 실행한다. Python 외부 패키지는 필요하지 않다.

- 전체 검사: `bash scripts/verify.sh` (자체 fixture 테스트, Python 문법, 하네스 연결, diff 공백).
- 네이티브 컴파일: `python3 scripts/build-check.py` (임시 폴더, 설치하지 않음, Xcode CLT 필요).
- 사용자 설치/업데이트: `python3 scripts/install-rescue.py` (설치 요청이 있을 때).
- 화면/브리지 변경: 컴파일에 더해 실제 화면의 관련 흐름을 확인한다. 테스트용 프로세스만 사용한다.
- 별도 formatter/linter는 아직 없다. 기존 스타일을 따르고 없는 검증 명령을 만들어 보고하지 않는다.

## 개발과 Git 컨벤션

- `git.base_branch`: `main`. 작업 브랜치/PR 사용, main 직접 커밋 금지.
- 브랜치 형식: `<type>/<이슈번호>`. 작업 시작 시 정식 이슈를 생성한다.
- `git.branch_structure`: `single`. 별도 production 브랜치 없음.
- `git.verify_gate_cmd`: `bash scripts/verify.sh`.
- `git.ci_wait`: `gh-checks-watch`. CI는 `.github/workflows/verify.yml`.
- 공개 origin: `https://github.com/Orchemi/mac-rescue.git`. GitHub 계정 Orchemi.
- 한국어 conventional commits, 이슈 번호 선택 사항. AI 귀속 문구를 추가하지 않는다.
- push/merge는 현재 요청의 승인 범위에 따른다. `pr auto`는 push·PR·CI·merge·정리를 포함한다.
- 설치된 Horbis의 개발/Git/QA 절차를 활용하되 이 저장소에 플러그인 사본을 복제하지 않는다.
  Horbis가 없는 환경에서도 이 문서의 코드 지도·동작 계약·검증 명령으로 작업할 수 있다.
- 버전은 `VERSION`, `CHANGELOG.md`, `v` 접두 태그. GitHub Release·공증은 별도 요청.

## 공개 저장소와 로컬 상태

- 실제 `.env.local`, 키, 비밀번호, 토큰, 사용자 프로세스 덤프, 설치본은 커밋하지 않는다.
  `.env.local.example`은 마스킹만 유지한다. 개인정보가 필요한 설정은 기존 환경설정 모듈을 사용한다.
- 개인 접속 설정은 비공개 Obsidian 노트에서 복원한다. 노트 내용/경로를 공개 이력에 복사하지 않는다.
- 개인 도구 설정·세션 메모리는 로컬 ignored 파일에 둔다. 공개 가능한 설계와 검증 결과만
  `docs/plan/`, `docs/dev-history/`에 기록한다. 기존 083 문서는 최초 개발 기록이다.
- 새 세션 시작과 역할별 검토 범위는 `docs/development.md`를 참고한다.
