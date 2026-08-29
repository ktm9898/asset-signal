# Asset Signal | ETF 동적 자산배분 & 조건부 리밸런싱 시스템 (asset-signal)

미국 및 한국 주요 ETF(QQQ, QLD, TQQQ, SCHD, SPY, TLT 등)를 대상으로 기준 지수의 고점 대비 낙폭(MDD)과 시장 국면에 따라 포트폴리오 비중을 동적으로 조절하고, 장기 백테스트를 통해 검증된 최적의 리밸런싱 신호를 제공하는 웹앱 및 자동화 시스템입니다.

---

## 🌟 주요 기능

1. **동적 상태 머신(State Machine) & 조건부 리밸런싱**:
   - **평시 국면 (Normal)**: 기본 자산 배분 (예: QQQ 60% : SCHD 40%)으로 복리 성장 및 배당 수취
   - **낙폭 진입 국면 (MDD Escalation)**: 고점 대비 -20%, -30%, -40% 폭락 시 2X/3X 레버리지(QLD, TQQQ)를 분할 편입하여 저점 매수 단가 극대화
   - **비대칭 계단식 복귀 국면 (Hysteresis Recovery)**: 반등 시 가장 위험한 TQQQ(-25%) $\rightarrow$ QLD(-15%) $\rightarrow$ 기본 자산(-5%) 순으로 선제 익절하여 레버리지 음의 복리 완벽 차단
   - **상승기 이익 실현 (Gain/Drift Rebalance)**: 총자산 +20% 상승 또는 비중 이탈 시 이익을 확정 짓고 안전자산으로 리밸런싱

2. **벤치마크 4종 실시간 비교 백테스트 랩 (`admin.html`)**:
   - 전략 성과를 `QQQ 단순보유(1X)`, `TQQQ 단순보유(3X)`, `정적 60:40 B&H`, `SPY 단순보유`와 다각도 비교
   - CAGR, MDD, Sharpe Ratio, Sortino Ratio, 총 리밸런싱 횟수 및 자산 성장 곡선 실시간 시각화
   - 10개 전략 프리셋 슬롯 지원 및 구글 시트 클라우드 1-클릭 동기화

3. **일일 모니터링 & 권장 비중 신호 대시보드 (`index.html`)**:
   - 기준 지수(QQQ 등)의 당일 종가, 최고가(ATH), 현재 낙폭(MDD) 및 국면 상태 실시간 표시
   - 자산별 목표 비중(Target Weight %) 도넛 차트 및 조정 폭(Delta %p) 체크리스트
   - 사용자 총 투자금액 입력 시 ETF별 목표 매매 금액 자동 산출

4. **클라우드 자동화 파이프라인**:
   - **GitHub Actions**: 미국 장 마감 후 매일 06:30 KST 자동 실행 (`screener.yml`)
   - **Google Apps Script & Sheets**: 일일 리밸런싱 신호, 사용자 보유 자산, 전략 슬롯 DB 연동

---

## 🛠️ 기술 스택

- **Backend / Engine**: Python 3.10, `yfinance`, `pandas`, `numpy`
- **Database / Cloud API**: Google Sheets, Google Apps Script (Web App REST API)
- **CI/CD & Scheduler**: GitHub Actions, GAS Time-driven Triggers
- **Frontend**: Vanilla HTML5, Modern CSS (Glassmorphic Dark Theme), Chart.js, Font Awesome
