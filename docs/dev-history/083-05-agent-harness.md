# 083-05 — 프로젝트 로컬 Claude/Codex 개발 구조

## 변경 이유

Horbis 밖에서 새 세션을 시작할 때 코드 지도와 안전한 검증 명령을 찾을 수 있도록 한다.
기존에는 짧은 AGENTS.md만 있고 Claude adapter와 프로젝트 전용 스킬이 없었다.

## 변경

- AGENTS.md를 공통 사실·동작 계약·Git 컨벤션 정본으로 확장하고 CLAUDE.md에서 가져온다.
- rescue-check 스킬을 .agents/skills에 두고 .claude/skills에서 상대 symlink로 공유한다.
- 설치하지 않는 임시 Swift 컴파일 명령과 하네스 연결 검사를 추가한다.
- 개발 안내에 새 세션, 역할별 검토, 로컬 상태와 공개 기록의 경계를 기록한다.
- 기기별 권한/설정은 ignore 처리하며 전역 설정이나 모델 설정은 변경하지 않는다.

## 검증

- bash scripts/verify.sh: 기존 테스트 35개, Python 문법, 하네스 검사 통과.
- python3 scripts/build-check.py: 실제 Swift 컴파일 통과, 임시 출력 삭제.
- skill-creator quick_validate와 Horbis live inventory: 공유 스킬 1개, 연결 오류 없음.
- 실제 Claude/Codex 새 대화에서의 스킬 호출은 별도 세션에서 확인할 항목이다.

## 범위

사용 중인 앱 설치/실행, 사용자 프로세스 종료, SSH 설정, 원격 저장소는 변경하지 않았다.
