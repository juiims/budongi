"""Naver 단지 detail API에서 지하철 관련 필드 검사.

여러 단지로 테스트하고 발견된 구조를 JSON으로 출력.
"""
import json
import sys
from pathlib import Path

from naver_realty_new import setup_driver, bootstrap_token, fetch_json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TARGETS = [
    ("103305", "강서힐스테이트"),
]

# 추가 후보 엔드포인트 (지하철 정보가 별도 API로 분리되어 있을 가능성)
EXTRA_ENDPOINTS = [
    "/api/complexes/overview/{id}",
    "/api/complexes/{id}/subway",
    "/api/complexes/{id}/transit",
    "/api/complexes/{id}/info",
    "/api/complexes/{id}/nearbyFacility",
    "/api/complexes/{id}/facility",
    "/api/complexes/{id}/around",
]


def find_subway_keys(obj, path="", results=None):
    """딕셔너리·리스트 재귀 탐색 — 지하철 관련 키 path 모두 수집."""
    if results is None:
        results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if any(s in kl for s in ["subway", "station", "transit", "walk", "transport"]) \
               or any(s in str(k) for s in ["역", "지하철"]):
                results.append((f"{path}.{k}", v))
            find_subway_keys(v, f"{path}.{k}", results)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):  # 리스트는 처음 3개만
            find_subway_keys(v, f"{path}[{i}]", results)
    return results


def main():
    driver = setup_driver(headless=True)
    try:
        print("토큰 발급 중...")
        auth = bootstrap_token(driver)
        print(f"토큰 OK: {auth[:30]}...\n")

        all_findings = {}
        for cid, label in TARGETS:
            print(f"=== {label} (id={cid}) ===")
            try:
                detail = fetch_json(driver, f"/api/complexes/{cid}?sameAddressGroup=false", auth)
            except Exception as e:
                print(f"  ✗ 호출 실패: {e}\n")
                continue

            top_keys = list(detail.keys())
            print(f"  최상위 키 {len(top_keys)}개: {top_keys}")

            # complexDetail 전체 키 출력
            cd = detail.get("complexDetail") or {}
            print(f"  complexDetail 키 {len(cd)}개:")
            for k in sorted(cd.keys()):
                v = cd[k]
                vtype = type(v).__name__
                if isinstance(v, (str, int, float, bool)) or v is None:
                    print(f"    {k} ({vtype}) = {str(v)[:80]}")
                elif isinstance(v, list):
                    print(f"    {k} (list[{len(v)}])"
                          + (f" first: {json.dumps(v[0], ensure_ascii=False)[:120]}" if v else ""))
                elif isinstance(v, dict):
                    print(f"    {k} (dict keys: {list(v.keys())[:8]})")

            # 지하철 관련 키 모두 탐색 (기존)
            findings = find_subway_keys(detail)
            print(f"  지하철 관련 필드 {len(findings)}건 발견 (재귀 탐색)")
            for path, v in findings[:30]:
                preview = json.dumps(v, ensure_ascii=False)[:200] if not isinstance(v, (str, int, float)) else str(v)[:200]
                print(f"    {path} = {preview}")

            if not all_findings and findings:
                all_findings[label] = findings

            # 추가 후보 엔드포인트 시도
            print(f"  추가 엔드포인트 시도:")
            for ep in EXTRA_ENDPOINTS:
                url = ep.format(id=cid)
                try:
                    resp = fetch_json(driver, url, auth)
                    if isinstance(resp, dict):
                        keys = list(resp.keys())[:5]
                        print(f"    ✓ {ep} → keys {keys}")
                    elif isinstance(resp, list):
                        print(f"    ✓ {ep} → list[{len(resp)}]")
                    else:
                        print(f"    ✓ {ep} → {type(resp).__name__}")
                except Exception as e:
                    msg = str(e)[:80]
                    print(f"    ✗ {ep} → {msg}")

            print()

        # 발견 구조를 JSON 파일에 저장 (참조용)
        if all_findings:
            out = Path("data/naver_subway_inspect.json")
            out.parent.mkdir(parents=True, exist_ok=True)
            serializable = {
                k: [(p, v if isinstance(v, (str, int, float, bool, type(None))) else json.loads(json.dumps(v, default=str)))
                    for p, v in vs]
                for k, vs in all_findings.items()
            }
            out.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n저장: {out}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
