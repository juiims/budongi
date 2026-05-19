"""
시·구·시 단위 평형별 매도 호가/전세가 집계 (스크린샷 양식).

Naver land /api/complexes/single-markers/2.0 에 cortarNo + areaMin/areaMax 필터
"""
import json
import sys
import time
import csv
from datetime import datetime

from naver_realty_new import setup_driver, bootstrap_token, fetch_json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DELAY = 0.6

# 평형 → 전용면적(㎡) 범위 (1평 ≈ 3.3㎡)
# Naver API의 areaMin/areaMax는 전용면적 ㎡ 단위
PYEONG_BUCKETS = {
    18: (55, 66),
    21: (66, 76),
    24: (76, 90),
    33: (95, 120),
}
# 마커 가격 후보 키 (호가 평균 추정)
DEAL_UNIT_KEYS = ("medianDealUnitPrice", "maxDealUnitPrice", "minDealUnitPrice")
LEASE_UNIT_KEYS = ("medianLeaseUnitPrice", "maxLeaseUnitPrice", "minLeaseUnitPrice")
DEAL_PRICE_KEYS = ("medianDealPrice", "maxDealPrice", "minDealPrice")
LEASE_PRICE_KEYS = ("medianLeasePrice", "maxLeasePrice", "minLeasePrice")

SEOUL_DISTRICTS = {
    "종로구": "1111000000",
    "중구": "1114000000",
    "용산구": "1117000000",
    "성동구": "1120000000",
    "광진구": "1121500000",
    "동대문구": "1123000000",
    "중랑구": "1126000000",
    "성북구": "1129000000",
    "강북구": "1130500000",
    "도봉구": "1132000000",
    "노원구": "1135000000",
    "은평구": "1138000000",
    "서대문구": "1141000000",
    "마포구": "1144000000",
    "양천구": "1147000000",
    "강서구": "1150000000",
    "구로구": "1153000000",
    "금천구": "1154500000",
    "영등포구": "1156000000",
    "동작구": "1159000000",
    "관악구": "1162000000",
    "서초구": "1165000000",
    "강남구": "1168000000",
    "송파구": "1171000000",
    "강동구": "1174000000",
}

def fetch_cortar_bbox(driver, cortarNo, auth):
    """cortarNo의 위경도 경계 조회."""
    res = fetch_json(driver, f"/api/cortars?cortarNo={cortarNo}", auth)
    if isinstance(res, dict) and "_error" not in res:
        return res
    return None


def fetch_markers(driver, cortarNo, trade_type, area_min, area_max, auth, bbox=None):
    bbox_q = ""
    if bbox:
        bbox_q = (
            f"&leftLon={bbox['leftLon']}&rightLon={bbox['rightLon']}"
            f"&topLat={bbox['topLat']}&bottomLat={bbox['bottomLat']}"
        )
    path = (
        "/api/complexes/single-markers/2.0"
        f"?cortarNo={cortarNo}"
        f"&realEstateType=APT"
        f"&tradeType={trade_type}"
        f"&priceType=RETAIL"
        f"&zoom=14"
        f"&areaMin={area_min}&areaMax={area_max}"
        f"&priceMin=0&priceMax=900000000"
        f"&rentPriceMin=0&rentPriceMax=900000000"
        f"&showArticle=false&sameAddressGroup=false"
        f"&minHouseHoldCount=&maxHouseHoldCount="
        f"&minMaintenanceCost=&maxMaintenanceCost="
        f"&oldBuildYears=&recentlyBuildYears="
        f"&directions=&tag=%3A%3A%3A%3A%3A%3A%3A%3A"
        + bbox_q
    )
    res = fetch_json(driver, path, auth)
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        if "_error" in res:
            return {"_error": res["_error"]}
        return res.get("complexList") or res.get("data") or res.get("markers") or []
    return []


def avg(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and x > 0]
    return int(sum(xs) / len(xs)) if xs else None


def extract_price_field(complex_item, *candidates):
    """단지 dict에서 후보 키들 중 첫 번째 양의 정수 값을 반환."""
    for k in candidates:
        v = complex_item.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return v
    return None


def fetch_markers_adaptive(driver, cortarNo, trade_type, area_min, area_max, auth, bbox, depth=0):
    """500개 상한 도달 시 bbox를 4분할해 추가 수집. markerId 중복 제거."""
    res = fetch_markers(driver, cortarNo, trade_type, area_min, area_max, auth, bbox)
    time.sleep(DELAY)
    if not isinstance(res, list):
        return []
    # 500 미만 또는 더 분할 불가하면 그대로
    if len(res) < 500 or not bbox or depth >= 2:
        return res

    mid_lon = (bbox["leftLon"] + bbox["rightLon"]) / 2
    mid_lat = (bbox["topLat"] + bbox["bottomLat"]) / 2
    quadrants = [
        {"leftLon": bbox["leftLon"], "rightLon": mid_lon, "topLat": bbox["topLat"], "bottomLat": mid_lat},
        {"leftLon": mid_lon, "rightLon": bbox["rightLon"], "topLat": bbox["topLat"], "bottomLat": mid_lat},
        {"leftLon": bbox["leftLon"], "rightLon": mid_lon, "topLat": mid_lat, "bottomLat": bbox["bottomLat"]},
        {"leftLon": mid_lon, "rightLon": bbox["rightLon"], "topLat": mid_lat, "bottomLat": bbox["bottomLat"]},
    ]

    seen = set()
    merged = []
    for m in res:
        mid = m.get("markerId")
        if mid and mid not in seen:
            seen.add(mid)
            merged.append(m)

    for q in quadrants:
        sub = fetch_markers_adaptive(driver, cortarNo, trade_type, area_min, area_max, auth, q, depth + 1)
        for m in sub:
            mid = m.get("markerId")
            if mid and mid not in seen:
                seen.add(mid)
                merged.append(m)
    return merged


def weighted_avg(pairs):
    """(value, weight) 리스트의 가중평균."""
    pairs = [(p, w) for p, w in pairs if p > 0 and w > 0]
    if not pairs:
        return None
    return int(sum(p * w for p, w in pairs) / sum(w for _, w in pairs))


def aggregate(driver, name, cortarNo, auth, debug=False):
    """
    스크린샷 4월 데이터에 가장 가까운 방식 (역산 결과):
      - 평형별 매매가 = max × dealCount 가중평균 (E 방식)
      - 평형별 전세가 = max × leaseCount 가중평균
      - 평당매매/전세 = 4개 평형 (매매가 / 평수) 의 단순 평균
    """
    out = {"지역": name, "cortarNo": cortarNo}

    cortar_info = fetch_cortar_bbox(driver, cortarNo, auth)
    time.sleep(DELAY)
    bbox = None
    if cortar_info:
        lat = cortar_info.get("centerLat") or cortar_info.get("latitude")
        lon = cortar_info.get("centerLon") or cortar_info.get("longitude")
        if lat and lon:
            bbox = {
                "leftLon": lon - 0.07,
                "rightLon": lon + 0.07,
                "topLat": lat + 0.05,
                "bottomLat": lat - 0.05,
            }

    pyeongdang_deal = []   # 4개 평형 평당가 (매매)
    pyeongdang_lease = []  # 4개 평형 평당가 (전세)
    total_deal_units = 0
    total_lease_units = 0

    for pyeong, (a_min, a_max) in PYEONG_BUCKETS.items():
        a1 = fetch_markers_adaptive(driver, cortarNo, "A1", a_min, a_max, auth, bbox)
        b1 = fetch_markers_adaptive(driver, cortarNo, "B1", a_min, a_max, auth, bbox)
        if isinstance(a1, dict):
            a1 = []
        if isinstance(b1, dict):
            b1 = []
        a1_deals = [c for c in a1 if (c.get("dealCount") or 0) > 0]
        b1_leases = [c for c in b1 if (c.get("leaseCount") or 0) > 0]

        # 매매: max × dealCount 가중평균 (E)
        deal_price = weighted_avg([
            (c.get("maxDealPrice", 0), c.get("dealCount", 0)) for c in a1_deals
        ])
        # 전세: min 단순 평균 (A) — 호가 max는 신축 outlier 영향이 커서 부적합
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

        print(f"    {pyeong}평: 매매 {len(a1_deals)}/{len(a1)} 단지, 전세 {len(b1_leases)}/{len(b1)} 단지")

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


def save_csv(rows, filename="regional_summary.csv"):
    if not rows:
        print("저장할 데이터 없음")
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
    print(f"\nCSV: {filename} ({len(rows)}행)")


def main():
    targets = SEOUL_DISTRICTS  # 서울 25개 구 전체

    driver = setup_driver(headless=False)
    rows = []
    try:
        auth = bootstrap_token(driver)
        for i, (name, cortarNo) in enumerate(targets.items()):
            print(f"\n[{i+1}/{len(targets)}] {name} ({cortarNo})")
            try:
                row = aggregate(driver, name, cortarNo, auth, debug=False)
                rows.append(row)
                print(f"  평당매매={row.get('평당매매')} 평당전세={row.get('평당전세')} "
                      f"전세가율={row.get('전세가율')} 단지수={row.get('단지수_매매')}")
            except Exception as e:
                import traceback
                traceback.print_exc()
                rows.append({"지역": name, "cortarNo": cortarNo, "에러": str(e)})
    finally:
        driver.quit()
        save_csv(rows, "regional_summary.csv")


if __name__ == "__main__":
    main()
