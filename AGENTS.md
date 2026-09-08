# mac-rescue

macOS 전용 개인 도구. 사용자 작업 프로세스를 테스트 대상으로 종료하지 않는다.
종료 정책 변경은 PID 정체성·사용자·보호 대상·확인 문구·만료 검증을 유지한다.
테스트는 자체 생성한 임시 프로세스만 종료하고 시스템 설정·로그인 항목을 변경하지 않는다.

## 개발과 Git 컨벤션

- 기본 브랜치: main. 신규 빈 저장소의 최초 커밋으로 초기화하고 이후 기능은 작업 브랜치/PR 사용.
- GitHub 계정: Orchemi. 비공개 origin: git@github-personal:Orchemi/mac-rescue.git.
- 커밋: 한국어 conventional commits, 이슈 번호 선택 사항.
- 검증: 저장소 루트에서 `bash scripts/verify.sh`; 실제 앱 빌드 `python3 scripts/install-rescue.py`.
- 버전: VERSION의 SemVer, CHANGELOG.md, v 접두 Git 태그. GitHub Release 게시와 공증은 별도 요청.
- 소스·테스트·문서만 추적한다. 설치본·스크린샷·프로세스 기록·키·비밀번호는 커밋하지 않는다.
