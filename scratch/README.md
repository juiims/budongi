# scratch/ — 디버그·탐색용 임시 산출물

`.gitignore`에서 `_*` 패턴으로 제외되는 파일들의 보관소. **언제 통째로 삭제해도 됨**.

## 구조

- `apt2_html/` — apt2.me에서 가져온 자치구별 HTML 캐시 (26개). 파싱 결과는 `data/apt2_*.csv`로 추출됨.
- `debug_scripts/` — 한 번 쓰고 끝난 진단/탐색 스크립트 (`_debug_*`, `_diag_*`, `_probe_*`, `_test_*`, `_analyze_*`).
- `outputs/` — 스크립트 실행 결과 txt/json 로그.

루트의 `analyze_apt2_school.py` / `diagnose_unmatched.py` 같은 **유지보수용 진단 도구**는 scratch가 아니라 루트에 둠 — 향후 재실행 가능성.
