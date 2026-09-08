# 083-01: Mac 메모리 점검과 원격 복구 CLI

## 관련 문서

- plan: [083-mac-rescue.md](../plan/083-mac-rescue.md)
- 사용 안내: [mac-rescue.md](../mac-rescue.md)
- 구현 범위: 로컬 진단과 SSH 복구

## [DEV] 개발 — 2026-09-08

### 개발 중점

RSS만으로 놓치는 큰 압축·스왑 프로세스를 physical footprint로 보여준다. 실행 그룹별
프로젝트·작업 디렉터리·포트·부모 관계를 확인한 뒤, 사용자가 입력한 대상만 종료한다.
조회·watch는 무신호이며 stale 여부는 검토 근거로만 제시한다.

### 변경 파일

- `scripts/mac-rescue.py`: 진단·그룹 상세·종료 미리보기·명시 실행·로그·SSH 점검
- `scripts/mac_rescue_test.py`, `scripts/mac-rescue.test.sh`: 안전 정책과 임시 트리 실종료
- `docs/mac-rescue.md`, `docs/plan/083-mac-rescue.md`: 사용 방법과 구현 범위

설치본은 `~/.local/bin/mac-rescue`에 독립 복사했다. 상주 서비스·추가 의존성은 설치하지 않았다.

### 트러블슈팅

실측에서 shell wrapper 때문에 같은 개발 서버가 두 그룹에 잡혔다. 최상위 감지 그룹을
선택해 그룹 PID 집합이 겹치지 않게 수정하고 회귀 테스트와 live JSON 검증을 추가했다.
실행 파일 인수는 내부 분류에만 사용하며 JSON·기록에는 노출하지 않는다.

### 품질 게이트

- Red: 구현 파일이 없는 상태에서 신규 테스트 실패 확인
- Green: `bash scripts/mac-rescue.test.sh` — 14개 통과
- 통합: 생성한 임시 Python/sleep 부모·자식만 실제 SIGTERM 종료, 작업 앱 미종료
- Live: 실제 Mac의 조회·inspect·stop 미리보기·JSON 검증, 그룹 중복 없음
- Live: watch 2회와 JSONL 기록 2회, 설치본과 소스 일치
- 전체: `node scripts/verify.mjs` — exit 0, harness parity divergence 0
- `git diff --check` — 통과
- 별도 lint/typecheck/build 명령은 대상에 없음

### 원격 접속 상태

macOS 원격 로그인 활성화 이후 SSH handshake와 호스트 공개키 확인 절차를 검증했다.
계정·IP·개별 권한 설정은 공개 기록에 남기지 않는다. 설정 변경과 인증은 사용자가 직접 한다.

### 미처리 항목

모바일 실제 연결과 잠자기·재부팅·FileVault 잠금 해제 전 가용성은 별도 기기에서
검증해야 한다. 공개키/비밀번호는 코드·문서에 보관하지 않는다.

POSIX PID 신호 전달의 최종 identity 확인 이후 경쟁 구간은 남는다. 새 자식과 잔존 프로세스는
자동 종료·자동 강제 종료하지 않고 사용자에게 다시 표시한다.
