# 한강 이남 단지 입지 추천 시스템

**예산 입력 → 한강 이남 매물 → 입지 점수 정렬 → 추천**

Phase 1 완성 (2026-05-19). 사용자 워크플로우 작동 가능.

## 웹 UI (Streamlit)

```powershell
streamlit run streamlit_app.py
```

브라우저 자동 열림 → http://localhost:8501

- 사이드바: 예산 슬라이더·범위·지역·점수컷·상위 N
- 본문: 정렬 가능 표, Naver 링크 클릭, CSV 다운로드, 점수 분포 차트
- 사이드바 하단 "🔄 catalog 재빌드" 버튼으로 수동 갱신

## CLI 사용법

### 가장 흔한 명령

```powershell
# 8억 검색 — 당일 첫 실행이면 catalog 자동 갱신(약 25-30분) 후 검색
python budget_search.py 80000

# 12억, 상위 20개
python budget_search.py 120000 20

# 서울만, ±7천만원
python budget_search.py 90000 --region 서울 --range 7000

# 입지점수 40 이상만
python budget_search.py 100000 --min-score 40

# 갱신 건너뛰기 (오늘 데이터 없어도 기존 데이터로 즉시 검색)
python budget_search.py 80000 --no-refresh

# 강제 재빌드
python budget_search.py 80000 --force-refresh

# URL 섹션 숨기기
python budget_search.py 80000 --no-urls
```

### 자동 갱신 동작

`budget_search.py` 실행 시 `data/catalog_scored.csv` mtime 확인:
- **오늘 자정 이후** mtime → 즉시 검색
- **오늘 자정 이전** mtime → 자동으로 `screen_candidates.py` + `score_candidates.py` 호출(약 25-30분), 그 다음 검색
- 갱신 중 Ctrl+C → 기존 데이터로 즉시 검색

매일 첫 검색 시 25-30분 갱신 + 그 다음부터 당일은 즉시 응답.

### 출력 예 (9억 검색 상위)

```
  #    점수 지역 시구         동          단지명           가격대(만)   세대  강남  합정  남양
  1  49.6 서울 동작구    상도동      벽산블루밍1차     94000~110000 2105 7.34  7.24 32.9
  2  48.7 서울 양천구    목동        영등포중흥S-클래스 90000~150000 308  12.76 3.75 34.91
  3  42.2 서울 영등포구  대림동      삼성래미안        92500~92500  1244 12.02 7.16 31.14
  ...

[Naver 단지 페이지 — 클릭/복사하여 실시간 매물 확인]
   1. 벽산블루밍1차              https://new.land.naver.com/complexes/8462
   2. 영등포중흥S-클래스          https://new.land.naver.com/complexes/121758
   3. 삼성래미안                https://new.land.naver.com/complexes/3092
   ...
```

추천 결과는 catalog 스냅샷의 가격 범위. **실시간 매물 호가는 URL 클릭해서 Naver에서 확인**.

## 디렉토리

```
budong/
├── streamlit_app.py            ← 웹 UI 엔트리
├── budget_search.py            ← CLI 엔트리
│
├── lib/                        # 코어 라이브러리 (다른 패키지가 import)
│   ├── naver_realty_new.py     · Naver 부동산 클라이언트 (Selenium)
│   ├── rtms_client.py          · 국토부 RTMS API
│   ├── regional_aggregator.py  · Naver markers·평형 버킷
│   └── screen_candidates.py    · 한강 이남 단지 스크리닝
│
├── fetch/                      # 외부 데이터 수집 (5개)
│   └── fetch_{rtms_district,all_districts,rtms_rent_all,apt2_school,apt_recovery}.py
│
├── enrich/                     # catalog 보강 파이프라인 (7개)
│   └── enrich_with_{subway,rtms,rtms_global,supply_price,district_supply,jeonse_ratio}.py · enrich_catalog_apt2.py
│
├── score/                      # 점수화 (4개)
│   └── score_candidates.py · score_school.py · score_school_v2.py · school_district.py
│
├── utils/                      # 유틸·진단 (5개)
│   └── build_subway_db.py · patch_catalog.py · extract_school_only.py
│       analyze_apt2_school.py · diagnose_unmatched.py
│
├── data/                       # 정형 데이터 (catalog·subway·rtms·school·apt2)
├── archive/                    # 폐기·1회성 (archive/README.md)
├── scratch/                    # 디버그 HTML·로그 (gitignored)
├── .streamlit/                 # Streamlit 설정
└── PROGRESS.md · README.md · requirements.txt
```

스크립트 실행은 `python -m` 패키지 경로 사용:
```powershell
python -m lib.screen_candidates       # catalog raw 빌드
python -m score.score_candidates      # 입지 점수
python -m fetch.fetch_all_districts   # RTMS 자치구별 10년치
python -m enrich.enrich_with_rtms_global
```

## 점수화

5요소 연속점수(0-100) 가중합:

| 요소 | 서울 | 경기 | 컷오프 |
|---|---:|---:|---|
| 직장/서울접근성 | 40 | 25 | 강남역 15km / 30km |
| 교통(지하철) | 25 | 15 | 가장 가까운 역 1.5km |
| 자체일자리 | — | 20 | 판교·분당·과천·광교·마곡 10km |
| 환경 | 15 | 15 | 세대 300-1500 + 신축 5-30년 |
| 개인직장(합정) | 20 | 25 | 합정역 12km |

남양연구소는 셔틀 이용 → 교통(지하철) 점수가 대체. 거리는 참고용 컬럼에만.

## 데이터 갱신

```powershell
# catalog 재빌드 (가격 변동 반영, 25-30분 백그라운드)
$env:SCREEN_GYEONGGI='1'
$env:SCREEN_NO_PRICE_FILTER='1'
python -m lib.screen_candidates

# 점수 재계산 (가중치·컷오프 수정 후)
$env:SCORE_INPUT='data/candidates_hangang_south_catalog.csv'
$env:SCORE_OUTPUT='data/catalog_scored.csv'
python -m score.score_candidates
```

## 데이터 출처

- 단지: Naver 부동산 `/api/complexes/single-markers/2.0` (markers)
- 지하철: [stripe2933/SeoulMetropolitanSubway](https://github.com/stripe2933/SeoulMetropolitanSubway) parquet
- 자체일자리 거점: 판교·분당·과천·광교·마곡 좌표 (코드 상수)

## 의존성

```bash
pip install selenium webdriver-manager pandas pyarrow
```

Chrome 브라우저 필요 (Selenium 토큰 가로채기용).

## 진행 상황 / Phase 2 후보

`PROGRESS.md` 참조.
