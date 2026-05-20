# 진행 상황 (2026-05-19 기준)

## 사용자 목표

**"예산 X억 입력 → 한강 이남 한도 안 매물 → 입지 좋은 순 추천"**

## Phase 1 MVP 완성 ✅

### 워크플로우
```
사용자: "8억" 입력
  ↓
python budget_search.py 80000 [top_n]
  ↓
catalog_scored.csv 에서 가격 ±5천만원 매칭
  ↓
입지 점수(0-100) 순 정렬 → 상위 N개 출력
```

### 핵심 산출물
- **`data/catalog_scored.csv`** — 2,469개 단지 (한강 이남, dedup, 점수 부여)
- **`data/subway_stations.csv`** — 수도권 741개 지하철역 좌표

### 핵심 스크립트
| 파일 | 용도 |
|---|---|
| `screen_candidates.py` | 한강 이남 단지 스크리닝 (가격 필터 옵션) |
| `score_candidates.py` | 입지 점수화 (5요소 연속점수 가중합) |
| `budget_search.py` | 예산 → 입지순 추천 (메인 사용자 도구) |
| `build_subway_db.py` | parquet → CSV 변환 (1회용) |
| `patch_catalog.py` | catalog 빌드 traceback 시 누락 자치구 보강 |

## 점수화 (확정)

5요소 연속점수(0-100) 가중합. 학군은 데이터 부재로 1차 미측정.

| 요소 | 서울 | 경기 | 컷오프 (0점 거리) |
|---|---:|---:|---|
| 직장/서울접근성 | 40 | 25 | 강남역 15km / 30km |
| 교통(지하철) | 25 | 15 | 가장 가까운 역 1.5km |
| 자체일자리(경기) | — | 20 | 판교/분당/과천/광교/마곡 10km |
| 환경 | 15 | 15 | 세대수 300-1500 + 신축 5-30년 |
| 개인직장(합정) | 20 | 25 | 합정역 12km |

**남양**: 사용자 결정으로 셔틀 통근 → 교통 점수가 대체. 거리 컬럼만 참고용 유지.

## 검증된 분포 (2,469개)

- 서울 738개: 평균 37.5 / 최대 75.0 (메이플자이)
- 경기 1731개: 평균 20.3 / 최대 63.3
- 70+ 4개 / 60-69 53개 / 50-59 132개 / 40-49 209개

## 검증된 예산 시나리오

| 예산 | 매칭 단지 | 상위 패턴 |
|---|---:|---|
| 7억 | 448개 | 평촌 초원·영등포 대림·동작 신대방 (지하철+합정) |
| 8억 | 320개 | 안양 비산동(안양역)·분당 야탑·수원 매교 |
| 12억 | 209개 | 동작 상도·영등포 당산·신길·양천 목동 |
| 15억 | 159개 | 사당롯데·여의도·관악·평촌 인덕원 |

## Phase 1.5 / Phase 2 대기

| Phase | 작업 | 우선 |
|---|---|---|
| 1.6 | 가중치 사용자 정의 가능하게 (회사 가중 ↑ 등) | 사용자 결정 |
| 1.7 | 평수 필터 추가 (`--pyeong 24`) | 옵션 |
| 1.8 | 매물 단위 (articles 호출, 4층+ 최저호가) | 옵션 |
| 2.0 | 학군 데이터 (학원가 좌표 + 학업성취도) | 외부 데이터 |
| 2.1 | RTMS 시계열 (전고점·전저점·직전거래) | 외부 API |
| 2.2 | 호재 데이터 (`/api/developmentplan/rail/list` 검증됨) | 미사용 자원 |
| 2.3 | 30컬럼 사양 — 추천 단지 상세 페이지 | RTMS 등 의존 |

## 데이터 출처

- **단지**: Naver 부동산 `/api/complexes/single-markers/2.0` (markers)
- **지하철 좌표**: GitHub `stripe2933/SeoulMetropolitanSubway` parquet (수도권 741개)
- **자체일자리 거점**: 판교(37.3947,127.1112) · 분당 서현(37.3812,127.1187) · 과천 정부청사(37.4292,126.9879) · 광교중앙(37.2861,127.0566) · 마곡(37.5602,126.8255)

## 검증 사항

- 자치구 경계 단지 dedup (markerId, 3509→2469)
- 누락 7개 시 보강 (자치구 매칭 부분일치 수정)
- 평택 → 화성 5개 자치구 traceback 후 patch_catalog로 208개 보강
- 회사2(남양) 인근 화성 동탄 95개 추가 포함 완료

## 사용자 결정 사항 기록

1. ✅ 점수화 방식: **연속점수(0-100) 가중합** (B 등급에서 전환)
2. ✅ 회사 반영: 5요소 + **개인직장(합정)**, **남양은 교통 점수로 대체**
3. ✅ 진행 순서: **1차 부분점수 먼저** → catalog → budget_search → 교통 추가
4. ✅ 카탈로그 범위: **한강 이남 전체 가격대**
5. ✅ 스캔 범위: 서울 11구 + 경기 남부 17개 시
6. ✅ 의심거래 기준: 동일 기간 동일 평형 정상거래 대비 3억↓ 직거래 (Phase 2 시 적용)

## 디렉토리 구조

자세한 분류는 `README.md` 참조. 요약:

```
budong/
├── streamlit_app.py · budget_search.py    # 엔트리 (루트)
├── lib/    # naver_realty_new · rtms_client · regional_aggregator · screen_candidates
├── fetch/  # fetch_rtms_{district,all_districts,rent_all} · fetch_apt2_school · fetch_apt_recovery
├── enrich/ # enrich_with_{subway,rtms,rtms_global,supply_price,district_supply,jeonse_ratio} · enrich_catalog_apt2
├── score/  # score_candidates · score_school(_v2) · school_district
├── utils/  # build_subway_db · patch_catalog · extract_school_only · analyze_apt2_school · diagnose_unmatched
├── data/   # 정형 데이터
├── archive/ # 폐기·1회성 (archive/README.md)
└── scratch/ # 디버그 HTML/로그 (gitignored)
```

실행은 `python -m <package>.<module>` (예: `python -m lib.screen_candidates`). subprocess 호출도 모두 `-m` 방식으로 갱신됨.

## 일반 사용법 빠른 참조

```powershell
# 8억 검색 (가장 흔한 사용)
python budget_search.py 80000

# 12억, 상위 20개
python budget_search.py 120000 20

# 서울만, ±7천만원
python budget_search.py 90000 --region 서울 --range 7000

# 입지점수 40 이상만
python budget_search.py 100000 --min-score 40

# 점수 재계산 (가중치 조정 후)
$env:SCORE_INPUT='data/candidates_hangang_south_catalog.csv'
$env:SCORE_OUTPUT='data/catalog_scored.csv'
python score_candidates.py

# catalog 재빌드 (가격 변동 반영, 25-30분)
$env:SCREEN_GYEONGGI='1'
$env:SCREEN_NO_PRICE_FILTER='1'
python screen_candidates.py
```
