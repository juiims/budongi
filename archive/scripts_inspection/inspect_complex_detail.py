"""Naver 단지 detail API 응답에서 지하철 관련 필드 검사."""
import json
import sys
import re
from naver_realty_new import setup_driver, bootstrap_token, fetch_json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 1801개 중 top1 단지 — 평촌엘프라우드 (complexNo=?)
# 임의 단지 — 신정이펜하우스1단지 (양천구, 102874)
TARGET = "102874"

driver = setup_driver(headless=False)
try:
    auth = bootstrap_token(driver)
    detail = fetch_json(driver, f"/api/complexes/{TARGET}?sameAddressGroup=false", auth)

    # 지하철 관련 키 검색
    flat = json.dumps(detail, ensure_ascii=False)
    keywords = ["지하철", "subway", "station", "역", "도보", "walk", "transit", "transport"]
    print("=" * 60)
    print("지하철 관련 키워드 매칭 (응답 본문)")
    print("=" * 60)
    for kw in keywords:
        cnt = flat.count(kw)
        if cnt > 0:
            print(f"  '{kw}' {cnt}회 등장")

    # 최상위 키
    print("\n최상위 키:")
    for k in detail.keys():
        print(f"  {k}")

    # complexDetail 안 키
    cd = detail.get("complexDetail") or {}
    print(f"\ncomplexDetail 키 ({len(cd)}개):")
    for k in cd.keys():
        v = cd[k]
        if isinstance(v, (str, int, float)) or v is None:
            print(f"  {k} = {v}")
        elif isinstance(v, list):
            print(f"  {k} = list[{len(v)}]")
        elif isinstance(v, dict):
            print(f"  {k} = dict (keys: {list(v.keys())[:5]})")

    # 지하철·역 단어 포함 키 찾기
    print("\n지하철/역 관련 키:")
    for k in cd.keys():
        kl = k.lower()
        if any(s in kl for s in ["subway", "station", "transit", "walk", "transport"]) or any(s in k for s in ["역", "지하철"]):
            print(f"  {k}: {cd[k]}")

    # detail 안 다른 dict 검사
    print("\ndetail 다른 키들의 dict 검사:")
    for k, v in detail.items():
        if k == "complexDetail":
            continue
        if isinstance(v, dict):
            subway_keys = [sk for sk in v.keys() if any(s in sk.lower() for s in ["subway","station","walk","transit"]) or any(s in sk for s in ["역","지하철"])]
            if subway_keys:
                print(f"  detail.{k} 안 subway 키: {subway_keys}")
                for sk in subway_keys:
                    print(f"    {sk} = {v[sk]}")
        elif isinstance(v, list) and v:
            if isinstance(v[0], dict):
                first_keys = list(v[0].keys())
                subway_keys = [sk for sk in first_keys if any(s in sk.lower() for s in ["subway","station","walk","transit"]) or any(s in sk for s in ["역","지하철"])]
                if subway_keys:
                    print(f"  detail.{k}[0] 안 subway 키: {subway_keys}")

finally:
    driver.quit()
