# mac-rescue에서 개발하기

저장소 루트에서 새 Claude/Codex 세션을 시작한다. Horbis 터미널의 대화 기록은 자동 이전되지 않는다.
시작 프롬프트 예: “AGENTS.md와 docs/development.md를 읽고, 현재 Git 상태를 확인한 뒤 [개발할 기능]을 구현해줘.”

```sh
cd ~/Desktop/repositories/tools/mac-rescue
claude
# 또는
codex
```

처음 실행할 때 도구가 요구하는 저장소 신뢰/로그인을 완료한다. CLI 설치와 계정 로그인은
기기별 설정이며 공개 저장소에 포함하지 않는다. 같은 작업 폴더에서 두 에이전트가 동시에
파일이나 Git 상태를 바꾸지 않도록, 병렬 작업은 별도 worktree를 사용한다.

## 두 도구의 공통 구조

| 파일 | 역할 |
| --- | --- |
| `AGENTS.md` | 공통 지침과 프로젝트 사실의 정본 |
| `CLAUDE.md` | `@AGENTS.md`를 가져오는 Claude 진입점 |
| `.agents/skills/rescue-check/` | 프로젝트 전용 검증 스킬의 정본 |
| `.claude/skills/rescue-check` | 같은 스킬을 가리키는 저장소 내부 상대 symlink |
| `scripts/harness-check.py` | adapter, symlink와 스킬 메타데이터 검사 |

Codex에서는 `$rescue-check`, Claude에서는 `/rescue-check`로 검증을 요청할 수 있다.
새로 추가한 스킬이 목록에 없으면 저장소 루트에서 새 세션을 시작한다.
Horbis 플러그인은 기기별 설치 상태에 따라 제공된다. `horbis:dev`, `horbis:qa`,
`horbis:git-workflow`가 없더라도 공통 문서와 로컬 검증 명령은 사용할 수 있다.
Horbis의 프로젝트 생성 구조에서 정본/adapter 분리와 명시적인 검증 명령만 가져왔다.
웹 앱용 패키지·서버·DB와 기기별 MCP/권한/모델 설정은 필요하지 않다.

## 개발·검증·설치

```sh
bash scripts/verify.sh
python3 scripts/build-check.py
```

첫 명령은 자동 테스트와 구조 검사다. 두 번째는 Xcode Command Line Tools의 SDK로 Swift를
임시 폴더에서 컴파일하고 출력물을 지운다. 사용 중인 Rescue 앱이나 SSH 설정을 바꾸지 않는다.
실제 UI/설치 흐름 검증은 별도이며, 사용자 설치 요청이 있을 때만
`python3 scripts/install-rescue.py`로 설치한다. Swift 컴파일은 macOS에서만 가능하다.

메모리 수집/분류는 `mac_rescue_test.py`, 종료 계획은 `rescue_gui_test.py`,
파이프 계약은 `rescue_native_test.py`, 개인 설정은 `rescue_settings_test.py`,
설치 경계는 `install_rescue_test.py`에서 검증한다. 명령은 모두 `scripts/` 아래에 있다.

## 역할과 다음 작업 기록

전용 서브에이전트 설정은 현재 두지 않는다. 주 에이전트가 작은 변경을 구현하고,
복잡한 종료 정책이나 UI 변경에서만 사용 가능한 리뷰/QA 역할을 활용한다.
리뷰는 PID 재사용·소유권·보호 대상·확인 만료를, 실행 QA는 자체 fixture와 실제 화면 흐름을 본다.
각 도구의 에이전트 설정 형식이 다르므로 한쪽 설정을 다른 쪽으로 무작정 복제하지 않는다.

공개 가능한 새 설계는 `docs/plan/`, 구현 결과는 `docs/dev-history/`에 남긴다.
미완료 작업의 목표·변경 파일·검증 결과·남은 작업을 기록하면 다른 세션이 이어받기 쉽다.
실제 호스트 주소, 프로세스 명령줄, 환경값은 공개 문서에 기록하지 않는다.

참고: [Codex skills](https://developers.openai.com/codex/skills),
[Claude skills](https://code.claude.com/docs/en/skills),
[Claude imports](https://code.claude.com/docs/en/memory).
