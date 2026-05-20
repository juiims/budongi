"""
한강 이남 단지 1차 후보군 추출.

규칙:
- 매매가 9억 이하 (priceMax=90000)
- 300세대 이상 (totalHouseholdCount >= 300)
- APT (realEstateTypeCode == 'APT')
- 단지명에 '주상복합' 미포함
- 평형: 18(55-66) / 21(66-76) / 24(76-90) / 33(95-120) 중 하나라도 매물 있으면 후보

출력:
- 단지 단위 1행 (동·단지명·세대수·매매가범위·강남/회사1/회사2 직선거리)
- 평형은 중복 제거 후 단일 단지로 집계 (어느 평형에서 발견됐는지 표시)

스모크 모드: SCREEN_SMOKE=강서구 또는 SCREEN_SMOKE=강서구,양천구
전체 모드: SCREEN_GEONGGI=1 추가 시 경기 남부 포함
가격 무관: SCREEN_NO_PRICE_FILTER=1 (catalog 빌드용, 9억 컷 해제)
"""
import csv
import math
import os
import sys
import time
from datetime import datetime

from lib.naver_realty_new import setup_driver, bootstrap_token, fetch_json
from lib.regional_aggregator import PYEONG_BUCKETS, fetch_markers

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DELAY = 0.5
TOKEN_REFRESH_INTERVAL_SEC = 1500

# ============================================================
# 좌표 (직선거리 기준점)
# ============================================================
# 강남역 2호선/신분당선 — 검증된 좌표
GANGNAM_STN = (37.4979, 127.0276)
# 합정역 2호선/6호선 — Naver 지도에서 재확인 필요 (현재는 일반 알려진 값)
HAPJEONG_STN = (37.5497, 126.9136)
# 현대자동차 남양기술연구소 (화성시 남양읍) — Naver 지도에서 재확인 필요
NAMYANG_RND = (37.2178, 126.7977)

# ============================================================
# 한강 이남 cortarNo
# ============================================================
SEOUL_SOUTH_DISTRICTS = {
    "강서구": "1150000000",
    "양천구": "1147000000",
    "영등포구": "1156000000",
    "구로구": "1153000000",
    "금천구": "1154500000",
    "동작구": "1159000000",
    "관악구": "1162000000",
    "서초구": "1165000000",
    "강남구": "1168000000",
    "송파구": "1171000000",
    "강동구": "1174000000",
}

# 경기 남부 시군명 (한강 이남) — cortarNo는 런타임에 /api/regions/list 로 조회
GYEONGGI_SOUTH_NAMES = {
    "광명시", "안양시", "과천시", "군포시", "의왕시", "안산시", "시흥시",
    "부천시", "성남시", "하남시", "김포시", "화성시", "수원시", "용인시",
    "평택시", "오산시", "안성시",
}
GYEONGGI_DO_CORTAR = "4100000000"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def fetch_gyeonggi_south_districts(driver, auth):
    """경기도 하위 시군구에서 한강 이남 화이트리스트만 추출.

    자치구 있는 시(성남·수원·용인·안양·안산·부천·화성)는
    "성남시 분당구" 식으로 cortarType=dvsn 으로 펼쳐져 있어 시 이름 부분일치로 매칭.
    """
    res = fetch_json(driver, f"/api/regions/list?cortarNo={GYEONGGI_DO_CORTAR}", auth)
    if isinstance(res, dict) and "_error" in res:
        print(f"[경고] 경기도 시군구 조회 실패: {res['_error']}")
        return {}
    out = {}
    for r in (res.get("regionList") or []):
        name = r.get("cortarName", "")
        for target in GYEONGGI_SOUTH_NAMES:
            # 직접 매칭(자치구 없는 시) 또는 "성남시 분당구" 같이 시 이름으로 시작
            if name == target or name.startswith(target + " "):
                out[name] = r["cortarNo"]
                break
    return out


def fetch_subregions(driver, parent_cortarNo, auth):
    """하위 행정구역 (자치구 또는 법정동)."""
    res = fetch_json(driver, f"/api/regions/list?cortarNo={parent_cortarNo}", auth)
    if isinstance(res, dict) and "_error" in res:
        return []
    return res.get("regionList") or []


def fetch_dong_list(driver, district_cortarNo, auth, region_name=""):
    """시구 → 법정동 목록. 성남/수원/용인처럼 자치구가 있으면 한 단계 더 들어감."""
    regions = fetch_subregions(driver, district_cortarNo, auth)
    if not regions:
        return []
    # cortarType=sec 이면 법정동, 다른 값(자치구)이면 한 단계 더
    dongs = []
    for r in regions:
        ctype = r.get("cortarType")
        if ctype == "sec":
            dongs.append(r)
        else:
            # 자치구 → 다시 동 조회
            sub = fetch_subregions(driver, r["cortarNo"], auth)
            time.sleep(DELAY)
            for s in sub:
                if s.get("cortarType") == "sec":
                    s["_parent"] = r.get("cortarName")
                    dongs.append(s)
    return dongs


def dong_bbox(dong):
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


def is_jusangbokhap(name: str) -> bool:
    if not name:
        return False
    return "주상복합" in name


def screen_district(driver, name, district_cortarNo, auth_holder, region_label):
    """시구 단위로 한강 이남 단지 1차 후보 수집."""
    print(f"\n[{region_label}/{name}] cortarNo={district_cortarNo}")
    dongs = fetch_dong_list(driver, district_cortarNo, auth_holder[0], name)
    time.sleep(DELAY)
    if not dongs:
        print(f"  [경고] 동 목록 없음")
        return []
    print(f"  하위 동 {len(dongs)}개")

    # markerId 중복 제거 (같은 단지가 여러 평형 버킷에 잡힐 수 있음)
    seen_markers = {}  # markerId -> (단지dict, 발견 평형 set)

    for di, dong in enumerate(dongs):
        bbox = dong_bbox(dong)
        if not bbox:
            continue
        for pyeong, (a_min, a_max) in PYEONG_BUCKETS.items():
            res = fetch_markers(
                driver, dong["cortarNo"], "A1", a_min, a_max,
                auth_holder[0], bbox,
            )
            time.sleep(DELAY)
            if isinstance(res, dict) and "_error" in res:
                if "401" in str(res.get("_error", "")):
                    print(f"  [경고] 401 토큰 만료 — 재발급")
                    auth_holder[0] = bootstrap_token(driver)
                    res = fetch_markers(
                        driver, dong["cortarNo"], "A1", a_min, a_max,
                        auth_holder[0], bbox,
                    )
                else:
                    continue
            if not isinstance(res, list):
                continue

            for m in res:
                mid = m.get("markerId")
                if not mid:
                    continue
                # 필터
                if m.get("realEstateTypeCode") != "APT":
                    continue
                hh = m.get("totalHouseholdCount") or 0
                if hh < 300:
                    continue
                cname = m.get("complexName") or ""
                if is_jusangbokhap(cname):
                    continue
                # 9억 이하 필터 (SCREEN_NO_PRICE_FILTER=1 시 해제, catalog 빌드용)
                min_deal = m.get("minDealPrice")
                if os.environ.get("SCREEN_NO_PRICE_FILTER") != "1":
                    if not min_deal or min_deal > 90000:
                        continue
                else:
                    # 가격 무관 모드: 매물 있는 단지만 (minDealPrice 존재)
                    if not min_deal:
                        continue

                if mid not in seen_markers:
                    m["_dong"] = dong.get("cortarName")
                    m["_dong_parent"] = dong.get("_parent", "")
                    seen_markers[mid] = (m, set())
                seen_markers[mid][1].add(pyeong)

    rows = []
    for mid, (m, pyeongs) in seen_markers.items():
        lat = m.get("latitude")
        lon = m.get("longitude")
        d_gangnam = haversine_km(lat, lon, *GANGNAM_STN) if lat and lon else None
        d_hapjeong = haversine_km(lat, lon, *HAPJEONG_STN) if lat and lon else None
        d_namyang = haversine_km(lat, lon, *NAMYANG_RND) if lat and lon else None
        rows.append({
            "시구": name,
            "자치구": m.get("_dong_parent", ""),
            "동": m.get("_dong", ""),
            "단지명": m.get("complexName"),
            "단지번호": m.get("markerId"),
            "세대수": m.get("totalHouseholdCount"),
            "동수": m.get("totalDongCount"),
            "준공년월": m.get("completionYearMonth"),
            "평형구간": ",".join(str(p) for p in sorted(pyeongs)),
            "최저매매가_만원": m.get("minDealPrice"),
            "중위매매가_만원": m.get("medianDealPrice"),
            "최고매매가_만원": m.get("maxDealPrice"),
            "매매건수": m.get("dealCount"),
            "전세건수": m.get("leaseCount"),
            "최소면적_㎡": m.get("minArea"),
            "최대면적_㎡": m.get("maxArea"),
            "위도": lat,
            "경도": lon,
            "강남까지_km": round(d_gangnam, 2) if d_gangnam else None,
            "회사1_합정_km": round(d_hapjeong, 2) if d_hapjeong else None,
            "회사2_남양_km": round(d_namyang, 2) if d_namyang else None,
        })
    print(f"  → 후보 단지 {len(rows)}개")
    return rows


def save_csv(rows, filename):
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
    smoke = os.environ.get("SCREEN_SMOKE")  # 예: "강서구" or "강서구,양천구"
    include_gyeonggi = os.environ.get("SCREEN_GYEONGGI") == "1"

    driver = setup_driver(headless=False)
    rows = []
    start = time.time()
    try:
        auth_holder = [bootstrap_token(driver)]
        last_refresh = time.time()

        # 대상 시구 빌드
        targets = []  # list of (region_label, name, cortarNo)
        if smoke:
            names = [n.strip() for n in smoke.split(",")]
            for n in names:
                if n in SEOUL_SOUTH_DISTRICTS:
                    targets.append(("서울(스모크)", n, SEOUL_SOUTH_DISTRICTS[n]))
                else:
                    print(f"[경고] 스모크 대상 '{n}' 서울 한강 이남 11구 외 — 스킵")
        else:
            for n, c in SEOUL_SOUTH_DISTRICTS.items():
                targets.append(("서울", n, c))
            if include_gyeonggi:
                print("[경기 남부] /api/regions/list 로 cortarNo 조회 중...")
                gg = fetch_gyeonggi_south_districts(driver, auth_holder[0])
                time.sleep(DELAY)
                print(f"  발견된 시군: {list(gg.keys())}")
                missing = GYEONGGI_SOUTH_NAMES - set(gg.keys())
                if missing:
                    print(f"  [주의] 미발견: {missing}")
                for n, c in gg.items():
                    targets.append(("경기", n, c))

        print(f"\n총 {len(targets)}개 시구 처리 예정")

        for i, (label, name, cortarNo) in enumerate(targets):
            elapsed = (time.time() - start) / 60
            print(f"\n[{i+1}/{len(targets)}] {label}/{name}  경과 {elapsed:.1f}분")
            if time.time() - last_refresh > TOKEN_REFRESH_INTERVAL_SEC:
                print("  [info] 토큰 사전 재발급")
                auth_holder[0] = bootstrap_token(driver)
                last_refresh = time.time()
            try:
                drows = screen_district(driver, name, cortarNo, auth_holder, label)
                rows.extend(drows)
            except Exception as e:
                import traceback
                traceback.print_exc()
                rows.append({"시구": name, "에러": str(e)})
            # 중간 저장
            suffix = "_smoke" if smoke else ""
            if os.environ.get("SCREEN_NO_PRICE_FILTER") == "1":
                suffix = "_catalog"
            save_csv(rows, f"data/candidates_hangang_south{suffix}.csv")
    finally:
        driver.quit()
        suffix = "_smoke" if smoke else ""
        if os.environ.get("SCREEN_NO_PRICE_FILTER") == "1":
            suffix = "_catalog"
        save_csv(rows, f"data/candidates_hangang_south{suffix}.csv")
        print(f"\n총 경과: {(time.time()-start)/60:.1f}분")


if __name__ == "__main__":
    main()
