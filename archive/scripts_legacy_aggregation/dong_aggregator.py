"""
법정동 단위 cortarNo로 정밀 호출 후 시구별 합산.

각 시구별로 하위 동 cortarNo 목록 → 동별 평형 markers 수집 → 시구 단위 집계.
bbox가 동 단위로 작아 cortarNo 외 단지 흡수 문제 최소화.
"""
import csv
import sys
import time
from datetime import datetime

from naver_realty_new import setup_driver, bootstrap_token, fetch_json
from regional_aggregator import (
    fetch_markers, PYEONG_BUCKETS, SEOUL_DISTRICTS,
    weighted_avg, avg,
)

# 산정 방식 환경변수: METHOD=g (기본) / e (max × dealCount) / b (median 평균)
import os as _os
METHOD = _os.environ.get("METHOD", "g").lower()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DELAY = 0.5  # 동 단위는 호출 많아 약간 단축
TOKEN_REFRESH_INTERVAL_SEC = 1500  # 25분마다 토큰 재발급 검토


def fetch_dongs(driver, district_cortarNo, auth):
    """시구 cortarNo의 하위 법정동(sec) 목록."""
    res = fetch_json(driver, f"/api/regions/list?cortarNo={district_cortarNo}", auth)
    if isinstance(res, dict) and "_error" in res:
        return [], res["_error"]
    if isinstance(res, dict):
        regions = res.get("regionList") or []
        # cortarType=sec (법정동) 만
        return [r for r in regions if r.get("cortarType") == "sec"], None
    return [], None


def fetch_markers_with_retry(driver, cortarNo, trade_type, area_min, area_max, auth_holder, bbox=None):
    """Authorization 만료 감지 시 재발급. auth_holder=[token]."""
    res = fetch_markers(driver, cortarNo, trade_type, area_min, area_max, auth_holder[0], bbox)
    if isinstance(res, dict) and "_error" in res and "401" in str(res.get("_error", "")):
        print("  [경고] 401 — 토큰 만료, 재발급")
        auth_holder[0] = bootstrap_token(driver)
        res = fetch_markers(driver, cortarNo, trade_type, area_min, area_max, auth_holder[0], bbox)
    if isinstance(res, list):
        return res
    return []


def dong_bbox(dong):
    """동 dict의 centerLat/Lon에서 작은 bbox 생성."""
    lat = dong.get("centerLat")
    lon = dong.get("centerLon")
    if not lat or not lon:
        return None
    return {
        "leftLon": lon - 0.02,
        "rightLon": lon + 0.02,
        "topLat": lat + 0.015,
        "bottomLat": lat - 0.015,
    }


def aggregate_district(driver, name, district_cortarNo, auth_holder):
    """시구를 법정동 단위로 호출 후 평형 버킷별로 합산."""
    out = {"지역": name, "cortarNo": district_cortarNo}

    dongs, err = fetch_dongs(driver, district_cortarNo, auth_holder[0])
    time.sleep(DELAY)
    if err:
        out["에러"] = f"동 목록 실패: {err}"
        return out
    if not dongs:
        out["에러"] = "동 목록 없음"
        return out

    print(f"  하위 동 {len(dongs)}개: {', '.join(d.get('cortarName','') for d in dongs[:5])}{'...' if len(dongs)>5 else ''}")

    # 평형 버킷별로 markers를 모아 둘 곳
    bucket_a1 = {p: [] for p in PYEONG_BUCKETS}  # 매매 markers (merged)
    bucket_b1 = {p: [] for p in PYEONG_BUCKETS}
    seen_a1 = {p: set() for p in PYEONG_BUCKETS}  # markerId 중복 제거
    seen_b1 = {p: set() for p in PYEONG_BUCKETS}

    for di, dong in enumerate(dongs):
        dong_cortar = dong["cortarNo"]
        bbox = dong_bbox(dong)
        for pyeong, (a_min, a_max) in PYEONG_BUCKETS.items():
            a1 = fetch_markers_with_retry(driver, dong_cortar, "A1", a_min, a_max, auth_holder, bbox)
            time.sleep(DELAY)
            b1 = fetch_markers_with_retry(driver, dong_cortar, "B1", a_min, a_max, auth_holder, bbox)
            time.sleep(DELAY)

            for m in a1:
                mid = m.get("markerId")
                if mid and mid not in seen_a1[pyeong]:
                    seen_a1[pyeong].add(mid)
                    bucket_a1[pyeong].append(m)
            for m in b1:
                mid = m.get("markerId")
                if mid and mid not in seen_b1[pyeong]:
                    seen_b1[pyeong].add(mid)
                    bucket_b1[pyeong].append(m)

    # 집계
    pyeongdang_deal = []
    pyeongdang_lease = []
    total_deal_units = 0
    total_lease_units = 0
    for pyeong in PYEONG_BUCKETS:
        a1_deals = [c for c in bucket_a1[pyeong] if (c.get("dealCount") or 0) > 0]
        b1_leases = [c for c in bucket_b1[pyeong] if (c.get("leaseCount") or 0) > 0]

        if METHOD == "e":
            # E. max × dealCount 가중 (강남 친화)
            deal_price = weighted_avg([
                (c.get("maxDealPrice", 0), c.get("dealCount", 0)) for c in a1_deals
            ])
        elif METHOD == "b":
            # B. median 평균 (외곽 친화)
            deal_price = avg([c.get("medianDealPrice") for c in a1_deals])
        else:
            # G. median × 세대수 가중 (절충안, 기본)
            deal_price = weighted_avg([
                (c.get("medianDealPrice", 0), c.get("totalHouseholdCount", 0)) for c in a1_deals
            ])
        lease_price = avg([c.get("minLeasePrice") for c in b1_leases])

        out[f"{pyeong}기준 매매"] = deal_price
        out[f"{pyeong}기준 전세"] = lease_price
        out[f"{pyeong}기준 단지수"] = len(a1_deals)

        if deal_price:
            pyeongdang_deal.append(deal_price / pyeong)
            total_deal_units += sum(c.get("dealCount", 0) for c in a1_deals)
        if lease_price:
            pyeongdang_lease.append(lease_price / pyeong)
            total_lease_units += sum(c.get("leaseCount", 0) for c in b1_leases)

        print(f"    {pyeong}평: 매매 {len(a1_deals)}단지, 전세 {len(b1_leases)}단지, "
              f"매매가={deal_price}, 전세가={lease_price}")

    out["평당매매"] = int(sum(pyeongdang_deal) / len(pyeongdang_deal)) if pyeongdang_deal else None
    out["평당전세"] = int(sum(pyeongdang_lease) / len(pyeongdang_lease)) if pyeongdang_lease else None
    out["매매물수"] = total_deal_units
    out["전세물수"] = total_lease_units
    if out["평당매매"] and out["평당전세"]:
        out["전세가율"] = f"{round(out['평당전세'] / out['평당매매'] * 100)}%"
    else:
        out["전세가율"] = ""
    out["년월"] = datetime.now().strftime("%Y.%m")
    return out


def save_partial(rows, filename=None):
    if filename is None:
        # METHOD별로 파일 분리
        suffix = {"e": "_E", "b": "_B", "g": "_G"}.get(METHOD, "")
        filename = f"regional_summary_dong{suffix}.csv"
    if not rows:
        return
    keys, seen = [], set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                keys.append(k); seen.add(k)
    try:
        fp = open(filename, "w", newline="", encoding="utf-8-sig")
    except PermissionError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filename.replace(".csv", f"_{ts}.csv")
        fp = open(filename, "w", newline="", encoding="utf-8-sig")
    with fp:
        w = csv.DictWriter(fp, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    import os
    if os.environ.get("DONG_SMOKE"):
        targets = {"강남구": SEOUL_DISTRICTS["강남구"]}
    else:
        targets = SEOUL_DISTRICTS
    start = time.time()

    driver = setup_driver(headless=False)
    rows = []
    try:
        auth_holder = [bootstrap_token(driver)]
        last_refresh = time.time()

        for i, (name, cortarNo) in enumerate(targets.items()):
            elapsed = time.time() - start
            print(f"\n[{i+1}/{len(targets)}] {name} ({cortarNo})  경과 {elapsed/60:.1f}분")

            # 25분 지나면 사전 재발급
            if time.time() - last_refresh > TOKEN_REFRESH_INTERVAL_SEC:
                print("  [info] 토큰 사전 재발급")
                auth_holder[0] = bootstrap_token(driver)
                last_refresh = time.time()

            try:
                row = aggregate_district(driver, name, cortarNo, auth_holder)
                rows.append(row)
                print(f"  → 평당매매={row.get('평당매매')} 평당전세={row.get('평당전세')} "
                      f"전세가율={row.get('전세가율')}")
            except Exception as e:
                import traceback
                traceback.print_exc()
                rows.append({"지역": name, "cortarNo": cortarNo, "에러": str(e)})

            # 시구마다 중간 저장
            save_partial(rows)
            print(f"  [save] {len(rows)}행 저장")
    finally:
        driver.quit()
        save_partial(rows)
        print(f"\n총 경과: {(time.time()-start)/60:.1f}분")


if __name__ == "__main__":
    main()
