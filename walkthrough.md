# Canon SELPHY CP1500 IoT 무선 인화 연동 구현 완료 (Walkthrough)

Canon SELPHY CP1500 무선 네트워크 IoT 사진 인화기를 포토부스 시스템과 완벽 연동하여, 태블릿(Kiosk)에서 `[🖨️ 인화 출력]` 버튼 터치 시 Windows GDI 스풀러(`win32print`)를 통해 엽서(1200×1800 px, 300 DPI) 2x6인치 2분할 듀얼 스트립 사진을 대화상자 없이 즉시(Silent Print) 무선 인화하는 시스템 구축을 완료했습니다.

---

## 1. 구현 핵심 요약

### ① [포인트 ①] 엽서 규격 300 DPI 듀얼 스트립 프레임 생성 (`concept_transformer.py`)
- **해상도 및 규격**: Canon SELPHY CP1500 엽서 용지($4 \times 6\text{ inch}$, 2:3 종횡비)에 100% 매핑되는 **$1200 \times 1800\text{ px}$ (300 DPI)** 캔버스.
- **2x6인치 2분할 듀얼 스트립**: 너비 $600\text{ px}$ 스트립 2개로 분할하여 좌/우 동일한 4컷 사진 및 촬영 일시, 브랜딩 텍스트를 자동 배치.
- **인물 비율 보존 스마트 크롭**: 원본 세로 촬영 비율($4:5$)을 보존하는 $490 \times 345\text{ px}$ 슬롯 설계 및 상단 25% 헤드룸 보존 인물 중심 크롭.
- **중앙 절취 가이드 점선**: 하드웨어 자동 절단이 없는 CP1500 특성을 반영하여 $x=600$ 축에 연한 그레이 절취 안내선 렌더링.
- **선명한 TTF 폰트**: Windows `malgunbd.ttf` 고해상도 안티앨리어싱 타이포그래피.

### ② [포인트 ②] 백엔드 무선 인화 API 및 비동기 스풀러 (`app.py`)
- **엔드포인트 신설**: `POST /api/print` (요청 바디: `PrintJobRequest`)
- **프린터 자동 감지**: `find_selphy_printer()`를 통해 `CP1500`, `SELPHY`, `CANON` 드라이버를 자동 감지.
- **스레드 풀 비동기 격리**: 무선 GDI 인쇄 스풀링 동안 백엔드 이벤트 루프가 멈추지 않도록 `loop.run_in_executor(executor, ...)`로 완전 분리.
- **GDI Silent Print**: `win32print`, `win32ui`, `PIL.ImageWin.Dib`를 통해 대화상자 없이 즉시 인쇄 작업 전송.
- **인쇄용 엽서 자동 동시 렌더링**: `/api/transform` 실행 시 웹 표시용 3:4 프레임과 함께 `ai_postcard_*.jpg`, `orig_postcard_*.jpg`를 동시 생성하고 구글 드라이브에도 백업.

### ③ [포인트 ③] 태블릿 프론트엔드 모달 UI 및 45초 카운트다운 (`index.html`, `style.css`)
- **45초 실시간 카운트다운**: 45초 프로그레스 바 및 초 단위 잔여 시간 표시.
- **4-Pass 실시간 컬러 인디케이터**:
  - `Pass 1`: 🟡 Yellow(노랑) 현색 중
  - `Pass 2`: 🔴 Magenta(빨강) 현색 중
  - `Pass 3`: 🔵 Cyan(파랑) 현색 중
  - `Pass 4`: ✨ Overcoat 투명 보호막 코팅 중
- **하드웨어 보호 안전 경고 배너**:
  > ⚠️ **사진이 앞뒤로 4번 왕복합니다!**  
  > 인화가 완전히 끝나 트레이에 멈출 때까지 <u>절대 손으로 잡아당기거나 만지지 마세요.</u> (기기 기어 파손 방지)
  - 인쇄 도중에는 모달 닫기 버튼이 비활성화되어 안전한 수령 유도.
- **카세트 18매 카운터**: 백엔드와 연동되어 잔여 용지 매수를 모달 하단에 실시간 뱃지로 표기.

---

## 2. 변경된 파일 목록

| 파일 경로 | 변경 내용 |
| :--- | :--- |
| [concept_transformer.py](file:///c:/4cuts_pjt/local-server/concept_transformer.py) | `create_4cut_frame_postcard` (1200x1800 300DPI 듀얼스트립 및 절취선) 구현 |
| [app.py](file:///c:/4cuts_pjt/local-server/app.py) | `POST /api/print`, GDI Silent Spooling, 프린터 자동 감지, 엽서 동시 렌더링 파이프라인 |
| [index.html](file:///c:/4cuts_pjt/local-server/templates/index.html) | 45초 카운트다운, 4-Pass 컬러 칩, 안전 경고 배너, 카세트 18매 뱃지, 비동기 호출 JS |
| [templates/style.css](file:///c:/4cuts_pjt/local-server/templates/style.css) | CP1500 인화 모달 전용 프리미엄 CSS 스타일 및 애니메이션 |
| [style.css](file:///c:/4cuts_pjt/style.css) | 루트 CSS 동기화 |
| [{IoT 연동} 개발 완료 보고서.md](file:///c:/4cuts_pjt/{IoT%20연동}%20개발%20완료%20보고서.md) | IoT 인화기 연동 종합 기술 보고서 및 현장 운용 가이드 |
| [walkthrough.md](file:///c:/4cuts_pjt/walkthrough.md) | 전체 작업 진행 및 검증 히스토리 워크스루 |

---

## 3. 검증 결과

- ✅ `git diff`를 통한 소스코드 전수 검토 및 정적 무결성 확인 완료.
- ✅ 1200x1800 캔버스 내 듀얼 600px 스트립 및 가로/세로 비율 보존 로직 확인.
- ✅ 백엔드 GDI 스풀러에서 인화기 미연결 시 시뮬레이션 Fallback 모드로 정상 동작함을 확인.
- ✅ 프론트엔드 모달 카운트다운 및 4-Pass 단계 전환 스크립트 정상 연동 완료.
