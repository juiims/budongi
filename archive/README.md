# archive/ — 이전 작업 보관소

Phase 1 워크플로우와 무관하거나 1회 사용 후 종료된 파일들의 안전망 보관소.
**용도가 명확히 끝났음**이 확인되면 archive 폴더 자체를 통째로 삭제해도 됩니다.

## 구조

### scripts_legacy_aggregation/ — 시·구 시세 집계 작업 (사용자 평가 "실패")
4월(스크린샷) vs 5월(Naver) 시구별 평균 시세 비교를 시도했던 작업물. 데이터 출처 차이로 의미 없는 비교가 되어 폐기.

- `dong_aggregator.py` — 동 단위 시세 집계 (G 방식 채택)
- `regional_aggregator.py` 는 루트에 남아 있음 — Phase 1의 `screen_candidates.py`가 `PYEONG_BUCKETS`·`fetch_markers`·`fetch_markers_adaptive`·`weighted_avg`·`avg` 함수를 import 의존. **삭제 금지**
- `reverse_engineer.py` / `reverse_engineer_outliers.py` — 시세 산정 방식 역산
- `compare_to_screenshot.py` / `compare_detailed.py` — 4월 스크린샷 vs 5월 비교
- `make_report.py` — 4월/5월 HTML/CSV 비교 장표
- `summary_table.py` — 단지 단위 평형 표 변환

### scripts_inspection/ — 1회용 검증 도구 (완료)
API 응답 구조나 데이터 출처 검증용. 검증 결과는 `MEMORY/project-naver-api-findings.md` 또는 `MEMORY/reference-external-data.md`에 저장됨.

- `inspect_gyeonggi.py` — 경기도 `/api/regions/list` 응답 구조 확인
- `inspect_complex_detail.py` — 단지 detail에 지하철 필드 있는지 확인
- `inspect_complex_apis.py` — 단지 페이지의 모든 호출 endpoint 확인
- `inspect_subway_csv.py` — 사용자 제공 서울교통공사 CSV 구조 확인 (좌표 없음 확인)
- `parse_subway.py` — Gist JSON5 → CSV 변환 (광역시 한정, 미채택)

### docs/
- `README_사용법.md` — 옛 단지 스크래퍼 단독 사용 가이드 (Phase 1 워크플로우 무관)

### data/ — 이전 단계 산출물
- `candidates_hangang_south.csv` / `candidates_scored.csv` — 9억 이하 한정 raw·점수 (가격 무관 catalog가 대체)
- `candidates_hangang_south_smoke.csv` — 양천구 스모크 결과
- `regional_summary*.csv` — 시구 시세 집계 결과 (3개)
- `report_4월_5월_비교.*` — 실패 평가된 비교 장표
- `summary_table.csv` / `naver_new_results.*` — 단지 5개 데모 결과
- `korean_subway_raw.json5` — 광역시 한정 지하철 데이터 (미채택)
- `서울교통공사_노선별 지하철역 정보.csv` — 좌표 없는 데이터 (미채택)

## 30일 후 권장

archive 폴더 안 어느 것이라도 필요하지 않다고 확신하면:

```bash
rm -rf archive/
```

archive 안에서 살릴 게 있다면 해당 파일만 루트로 다시 이동.
