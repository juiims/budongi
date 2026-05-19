"""단지 페이지 접속 시 호출되는 모든 /api/* endpoint dump.

목적: 지하철·주변환경 정보를 제공하는 endpoint가 따로 있는지 찾기.
"""
import json
import sys
import time
from naver_realty_new import setup_driver, bootstrap_token, fetch_json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TARGET = "102874"  # 신정이펜하우스1단지

driver = setup_driver(headless=False)
try:
    print("단지 페이지 로드…")
    driver.get(f"https://new.land.naver.com/complexes/{TARGET}")
    time.sleep(10)

    # 페이지 안 모든 API 호출 수집
    logs = driver.get_log("performance")
    api_paths = set()
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
        except Exception:
            continue
        if msg.get("method") != "Network.requestWillBeSent":
            continue
        url = msg.get("params", {}).get("request", {}).get("url", "")
        if "new.land.naver.com/api/" not in url:
            continue
        path = url.split("new.land.naver.com")[1].split("?")[0]
        api_paths.add(path)

    print(f"\n호출된 endpoint {len(api_paths)}개:")
    for p in sorted(api_paths):
        print(f"  {p}")

    # 지하철 관련 키워드 매칭
    subway_paths = [p for p in api_paths if any(k in p.lower() for k in
                    ["subway", "station", "around", "nearby", "info", "transit", "walk"])]
    if subway_paths:
        print(f"\n지하철 후보 endpoint:")
        for p in subway_paths:
            print(f"  {p}")

    # 토큰 가로채서 직접 호출 시도 — 알려진 패턴들
    auth = None
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
        except Exception:
            continue
        if msg.get("method") != "Network.requestWillBeSent":
            continue
        for k, v in (msg["params"]["request"].get("headers") or {}).items():
            if k.lower() == "authorization" and v.lower().startswith("bearer "):
                auth = v
                break
        if auth:
            break

    if auth:
        print("\n추측 endpoint 직접 호출 시도:")
        candidates = [
            f"/api/complexes/{TARGET}/around",
            f"/api/complexes/{TARGET}/subway",
            f"/api/complexes/{TARGET}/transit",
            f"/api/complexes/{TARGET}/nearby",
            f"/api/complexes/{TARGET}/info",
            f"/api/complexes/{TARGET}/environment",
            f"/api/complexes/{TARGET}/facility",
            f"/api/complexes/{TARGET}/landmarks",
            f"/api/around/{TARGET}",
            f"/api/transit/around/{TARGET}",
        ]
        for path in candidates:
            res = fetch_json(driver, path, auth)
            time.sleep(0.5)
            if isinstance(res, dict) and "_error" in res:
                print(f"  ❌ {path} → {res['_error']}")
            else:
                # 응답이 있다면 키 일부 출력
                if isinstance(res, dict):
                    keys = list(res.keys())[:8]
                    print(f"  ✅ {path} → keys={keys}")
                elif isinstance(res, list):
                    print(f"  ✅ {path} → list[{len(res)}]")
finally:
    driver.quit()
