# KR Valuation Tool

**IB · Equity Research · VC 포트폴리오급 한국 상장사 가치평가 자동화**

> DART OpenAPI로 재무제표를 자동 수집한 뒤 DCF, 시나리오 분석, LBO, Trading Comps, VC Unit Economics까지 한 화면에서 실행하는 Streamlit 기반 분석 도구입니다.

---

## 주요 기능

| 모듈 | 내용 |
|------|------|
| **Segmented Revenue** | 사업부별 P×Q 분해, 연도별 성장률 개별 설정 |
| **DCF + Scenario** | Bull/Base/Bear 3-케이스 확률가중 가치 산출, WACC × TGR 민감도 테이블 |
| **Football Field** | Goldman Sachs 방식 가로 바 차트 — Bear/Base/Bull DCF + EV/EBITDA Comps 범위 통합 |
| **LBO** | Entry EV → 부채구조 → 연도별 운영 모델 → Exit IRR/MOIC, Target IRR별 최대 인수 배수 |
| **Trading Comps** | DART 기반 동종업계 자동 수집 — EV/EBITDA, EV/Revenue, P/E, P/B, 피어 중앙값 Implied Equity |
| **VC Unit Economics** | LTV/CAC, Payback, Rule of 40, 24개월 코호트 분석, Magic Number |
| **Investment Verdict** | DCF(60%) + Comps(40%) 종합 업사이드 → BUY/HOLD/SELL 자동 판정 + 투자 논거 |
| **Export** | 수식이 살아있는 Excel DCF 모델 (Assumptions → DCF Model 교차시트 수식), fpdf2 PDF 1-Page Summary |

---

## 기술 스택

```
Python 3.11+   Streamlit 1.32    Plotly 5.18
pandas 2.0     numpy 1.24        openpyxl 3.1
fpdf2 2.7      requests 2.31     pykrx 1.0
```

**데이터 소스**
- [DART OpenAPI](https://opendart.fss.or.kr) — 금융감독원 전자공시 (재무제표, 주식수, 기업개황)
- pykrx — 한국거래소 주가 OHLCV

---

## 아키텍처

```
valuation-tool/
├── app.py                      # Streamlit 8-탭 메인
├── src/
│   ├── data/
│   │   ├── dart_api.py         # DART API 래퍼 (법인코드 XML, 재무제표, 주식수)
│   │   ├── market_data.py      # pykrx 주가·시총
│   │   └── peer_comps.py       # 동종업계 피어 멀티플 자동 수집
│   ├── models/
│   │   ├── dcf.py              # DCF · WACC · Hamada Beta · 민감도
│   │   ├── scenario.py         # Bull/Base/Bear 3-Scenario Engine
│   │   ├── lbo.py              # LBO IRR/MOIC · 민감도 테이블
│   │   └── unit_economics.py   # LTV/CAC · Rule of 40 · Cohort
│   └── charts/
│       ├── football_field.py   # Football Field · Waterfall Bridge
│       ├── excel_export.py     # openpyxl 수식 Excel 모델
│       └── pdf_report.py       # fpdf2 1-Page PDF Summary
└── requirements.txt
```

---

## DCF 모델 세부 구현

### 영업레버리지 (Operating Leverage)
EBITDA 마진을 기준연도에서 매년 `margin_expansion_annual` bps씩 상승 적용.

```
margin_t = base_margin + t × Δmargin
EBITDA_t = Revenue_t × margin_t
```

### CapEx-D&A 커플링
신규 CapEx를 내용연수로 나눠 증분 D&A를 매년 누적 반영. 과도한 D&A 누적은 dampener(0.3) 적용.

### Hamada 공식 (레버드 베타)
```
β_L = β_U × (1 + (1 − t) × D/E)
Ke  = Rf + β_L × ERP
WACC = E/(E+D) × Ke + D/(E+D) × Kd × (1−t)
```

### Terminal Value
- **Gordon Growth**: `TV = FCF_n × (1+g) / (WACC − g)`
- **Exit Multiple**: `TV = EBITDA_n × EV/EBITDA`

### 금융업 처리
부채비율 > 85% → `net_debt = 0` 자동 설정 + P/B · DDM 병행 권장 경고 표시.

---

## 실행 방법

### 로컬 실행

```bash
git clone https://github.com/YOUR_ID/kr-valuation-tool.git
cd kr-valuation-tool

pip install -r requirements.txt

# DART API 키 설정
mkdir -p .streamlit
echo 'DART_API_KEY = "YOUR_KEY"' > .streamlit/secrets.toml

streamlit run app.py
```

DART API 키 무료 발급: https://opendart.fss.or.kr/uss/usei/openapiUseInfoPage.do

### Streamlit Cloud 배포

1. 이 레포를 GitHub에 push
2. [share.streamlit.io](https://share.streamlit.io) → New app → 레포 연결
3. **Secrets** 탭에 `DART_API_KEY = "..."` 입력
4. Deploy

---

## 사용 예시

1. 사이드바에서 **기업명 검색** (예: `카카오`, `삼성전자`, `기업은행`)
2. 검색 결과에서 기업 선택 → **재무데이터 불러오기**
3. **사업부별 매출** 탭에서 세그먼트 구성 및 성장률 입력
4. **DCF + 시나리오** 탭에서 WACC, 마진, 성장률 조정 → 자동 계산
5. **Football Field** 탭에서 전체 밸류에이션 범위 확인
6. **LBO** 탭에서 PE 관점 IRR/MOIC 분석
7. **Trading Comps** 탭에서 피어 기업 추가 및 멀티플 비교
8. **투자 결론** 탭에서 BUY/HOLD/SELL 자동 판정 확인
9. **Export** 탭에서 Excel 모델 및 PDF 1-Page Summary 다운로드

---

## 주요 기술적 고려사항

- **NaN 안전 처리**: `float('nan')` 은 Python에서 truthy → `nan or 0 = nan`. `v != v` 체크로 해결.
- **DART `corpCode.xml`**: 기업 검색은 `/company.json`이 아닌 ZIP 파일 로컬 파싱 방식 사용 (API 제한).
- **pykrx 대응**: `get_market_cap_by_date` 등 시총 함수 broken → DART 주식수 × pykrx OHLCV 종가로 대체.
- **은행 주식수**: `isu_stock_totqy = '-'` 케이스 처리 → `istc_totqy` → `now_to_isu_stock_totqy` → `distb_stock_co` 순 fallback.
- **LBO IRR**: `numpy.irr` deprecated → Newton-Raphson 직접 구현.

---

## 라이선스

MIT License — 포트폴리오·학습 목적 자유 사용 가능.

---

*본 도구는 DART 공시 데이터 기반 자동 생성 결과입니다. 투자 결정의 근거로 단독 사용하지 마십시오.*
