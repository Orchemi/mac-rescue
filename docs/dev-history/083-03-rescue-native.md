# 083-03: Rescue 네이티브 Mac 앱

## 요청과 변경

사용자가 PC GUI를 실제 Mac 앱으로 요청했다. 기본 `rescue gui`와 Rescue.app을 SwiftUI
실행 파일로 전환하고, 웹 버전은 명시적인 `--web` / `--url` 옵션으로 유지한다.

- macOS 기본 사이드바·Table·검색·상세 inspector·확인 sheet·메뉴/단축키
- 메모리 압력·footprint·스왑·디스크 카드, 그룹/프로세스 조회와 필터·정렬
- 전용 Python 도우미와 JSON stdin/stdout 통신, 네트워크 소켓 없음
- 종료 미리보기·정확한 문구·60초 만료·PID 정체성 검증은 기존 정책 재사용
- 앱 창 닫기/종료 시 전용 도우미 EOF 종료, 활성 앱만 15초 갱신
- 설치 시 Swift 컴파일, 앱에 조회 엔진 포함, Python 경로를 설치 시 기록
- 실행 파일은 교체 파일로 업데이트하며 다른 앱/명령 덮어쓰기 방지 유지

## 검증

- Red: 네이티브 bridge 모듈 없음으로 테스트 실패 확인
- Green: 네이티브 dispatch 정책 3개, 기존 CLI 14개·GUI 정책 7개·설치기 3개 통과
- 첫 개발용 빌드는 빌드 중 소스 갱신을 컴파일러가 감지해 중단됐다. 설치기에서는 해시로
  고정한 버전 소스를 컴파일하여 개발 중 원본 변경과 분리한다.

## 한계

macOS 14 이상, Python 3, 설치 시 Swift 컴파일러가 필요하다. App Store 배포/공증된
배포본은 포함하지 않는다. 현재 Mac의 로컬 설치이며 원격 Git 백업 완료를 뜻하지 않는다.

## 실행 검수와 독립 저장소

- 상속된 SDKROOT가 선택된 Xcode Swift 컴파일러와 불일치했다. 설치기에 `xcrun --sdk macosx --show-sdk-path`로 선택한 SDK를 명시하여 전역 설정 변경 없이 빌드 성공
- macOS 툴바 검색 항목 중복 예외를 기본 NSSearchField로 교체하여 해결
- 파이프의 고정 크기 읽기 대기를 availableData 기반 프레이밍으로 교체하여 실제 상태 조회 성공
- 실제 Mac 앱에서 일회용 Node 서버 검색·그룹 상세·미리보기·문구 입력 전 차단 검증
- 정확한 확인 문구 이후 1개 SIGTERM 결과 확인, ps에서 테스트 PID 소멸 확인
- 사용자 작업 프로세스는 종료하지 않음. Cmd-Q 이후 Rescue 및 전용 도우미 종료 확인
- Horbis 전체 verify 통과 후 전용 `repositories/tools/mac-rescue`로 22개 초안 파일 이동
- 독립 저장소의 테스트 27개와 Python 문법 검증 통과
- VERSION/CHANGELOG/SemVer 태그·Mac CI·복원 README 추가
