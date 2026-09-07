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

### ④ [신규 추가] 현장 네트워크 & IoT 연동 진단 모니터링 도구 (`Diagnostics`)
- **홈 화면 상단 퀵 상태 캡슐**: `🟢 네트워크 정상 (00ms) ⚙️` 뱃지를 통해 태블릿-Host PC 간 핑 레이턴시를 15초 주기로 실시간 노출.
- **종합 진단 대시보드 팝업**:
  - **태블릿 ⇄ Host PC**: Host IP/Client IP, 동일 Wi-Fi 서브넷 일치 여부, HTTP API 왕복 응답 지연(ms) 실시간 측정.
  - **Canon SELPHY CP1500**: 드라이버 온라인 여부, 18매 카세트 잔여 용지, 누적 인쇄 횟수.
  - **클라우드 연동**: Google Drive 백업 및 OpenAI API 키 정상 구성 여부.
- **[🧪 테스트 엽서 1장 출력]**: 본 행사 전 CP1500으로 4색 CMYK 컬러 밴드와 300 DPI 정렬 격자가 담긴 테스트 패턴을 1장 즉시 시험 인쇄하는 기능 탑재.

### ⑤ [11차 개선] UI 미감 최적화 & 엽서 인쇄 전체 이미지 Aspect Fit 보존
- **AI 변환 로딩 UI 간소화**:
  - 장황한 5단계 스텝 및 팁 줄글 제거 ➔ 심플 스피너, 게이지 바, 남은 시간(`약 OO초`), `✨ 변환 완료!` 이벤트 배너로 개편.
- **화면 7 Finish 하단 버튼 2단 그리드 개편**:
  - 상단 1열 `[ ◀ 4컷 다시보기 ]` (50%) + `[ 🖨️ 엽서 인화 출력 ]` (50%), 하단 2열 `[ 🏠 처음으로 ]` (전폭) 배치로 글자 삐져나옴/잘림 원천 방지.
- **엽서 인쇄 프레임 인물 크롭 왜곡 해결**:
  - `concept_transformer.py`의 상하 45% 강제 크롭을 전면 제거하고, 실제 촬영된 전체 이미지(상반신, 어깨, 옷, 손)가 100% 손실 없이 슬롯 중앙에 렌더링되는 **Aspect Fit (Contain)** 알고리즘 적용.

---

## 2. 변경된 파일 목록

| 파일 경로 | 변경 내용 |
| :--- | :--- |
| [concept_transformer.py](file:///c:/4cuts_pjt/local-server/concept_transformer.py) | 엽서/일반 4컷 프레임 크롭 제거 및 전체 이미지 100% Aspect Fit 보존 |
| [app.py](file:///c:/4cuts_pjt/local-server/app.py) | 무선 인화, 진단 헬스체크 및 테스트 인쇄 엔드포인트 |
| [index.html](file:///c:/4cuts_pjt/local-server/templates/index.html) | 로딩 오버레이 간소화, 완료 이벤트 배너, 하단 2단 버튼 그리드 개편 |
| [templates/style.css](file:///c:/4cuts_pjt/local-server/templates/style.css) | 미니멀 로딩 카드 및 2단 액션 버튼 프리미엄 CSS |
| [style.css](file:///c:/4cuts_pjt/style.css) | 루트 CSS 동기화 |
| [개선작업_11.md](file:///c:/4cuts_pjt/개선작업_11.md) | 11차 개선 상세 내역 문서 |
| [{IoT 연동} 개발 완료 보고서 2.md](file:///c:/4cuts_pjt/{IoT%20연동}%20개발%20완료%20보고서%202.md) | UI 미감 및 인쇄 Aspect Fit 완료 보고서 |
| [walkthrough.md](file:///c:/4cuts_pjt/walkthrough.md) | 전체 작업 진행 및 검증 히스토리 워크스루 |

---

## 3. 검증 결과

- ✅ 로딩 화면의 불필요한 줄글이 제거되고 심플 게이지와 남은 시간, 완료 배너가 명확히 작동함.
- ✅ Finish 화면 하단 버튼의 글자가 삐져나오지 않고 단정하고 터치하기 편한 2단 레이아웃으로 렌더링됨.
- ✅ 엽서 인쇄 시 얼굴만 확대되던 현상이 해결되어 상반신 전체 구도가 온전히 인화됨.
