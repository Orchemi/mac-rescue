# 083: Mac 메모리 점검과 독립 원격 복구

소스 정본: https://github.com/Orchemi/mac-rescue

## 목표

macOS 메모리 부족 경고의 원인을 프로젝트 실행 그룹으로 파악하고, 사용자가 확인한 대상만
종료한다. Orca 장애에 영향을 받지 않는 Tailscale + macOS SSH 복구 절차를 제공한다.

## 구현 범위

- [x] 표준 라이브러리 CLI로 RAM·압력·스왑·footprint·부모 관계·프로젝트·포트 조회
- [x] 중복 없는 개발/자동화 Chrome 실행 그룹과 stale 검토 근거
- [x] PID/그룹 종료 미리보기, 명시 확인, PID 재사용/보호 대상 검증
- [x] 반복 측정과 최근 240회 선택 로그, 원격 접속 상태 점검
- [x] 로컬 실행 파일 설치와 사용자 안내
- [x] 사용자 관리자 인증 후 원격 로그인 활성화·계정 허용·SSH handshake 확인
- [x] 모바일 실제 접속 검증 (모바일 SSH 로그인·CLI 출력 확인)
- [x] PC GUI: 상태 요약·검색·필터·정렬·개별/그룹 종료 미리보기·확인
- [x] `rescue` 명령·Rescue.app·멱등 설치기와 포맷 후 복원 절차
- [x] SwiftUI 네이티브 앱으로 기본 GUI 전환·전용 파이프 도우미·실제 창 검증

## 검증

종료 정책 단위 테스트, 임시 프로세스 트리 실종료, 실제 Mac 조회·미리보기·JSON·로그 검증,
`node scripts/verify.mjs`를 실행한다. 기존 개발 서버·작업 앱은 검증 목적으로 종료하지 않는다.

## 비범위

자동 stale 확정·자동 kill, 시스템 서비스 삭제, production/DB 변경, 공개 웹 서버,
Orca 전체 Helper 일괄 종료, Mac 관리자 비밀번호 수집은 포함하지 않는다.

기본 GUI는 SwiftUI 네이티브 앱과 전용 stdin/stdout 도우미를 사용한다. 웹 화면은 `--web`으로
선택할 때만 loopback 서버를 시작한다. 자동 실행 서비스는 설치하지 않는다.
원격 백업은 별도 Git 승인·push 완료가 필요하다.
