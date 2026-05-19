"""
스크린샷 강남구(2026.04) 값을 역산.
markers 데이터에서 여러 산정 방식 적용 → 스크린샷과 비교 → 가장 가까운 방식 선정.
"""
import sys
import time

from naver_realty_new import setup_driver, bootstrap_token
from regional_aggregator import (
    fetch_cortar_bbox, fetch_markers, PYEONG_BUCKETS, SEOUL_DISTRICTS
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 스크린샷 강남구 (2026.04)
SCREENSHOT_GANGNAM = {
    "평당매매": 10299,
    "평당전세": 3269,
    "18기준 매매": 131346, "18기준 전세": 47196,
    "21기준 매매": 231987, "21기준 전세": 68712,
    "24기준 매매": 265128, "24기준 전세": 78528,
    "33기준 매매": 344256, "33기준 전세": 109494,
}


def methods_for_lease(markers):
    leases = [m for m in markers if (m.get("leaseCount") or 0) > 0]

    def avg(xs):
        xs = [x for x in xs if isinstance(x, (int, float)) and x > 0]
        return int(sum(xs) / len(xs)) if xs else 0

    def wavg(pairs):
        pairs = [(p, w) for p, w in pairs if p > 0 and w > 0]
        if not pairs:
            return 0
        return int(sum(p * w for p, w in pairs) / sum(w for _, w in pairs))

    methods = {}
    methods["A. min 평균"] = avg([m.get("minLeasePrice") for m in leases])
    methods["B. max 평균"] = avg([m.get("maxLeasePrice") for m in leases])
    methods["C. (min+max)/2 평균"] = avg(
        [(m.get("minLeasePrice", 0) + m.get("maxLeasePrice", 0)) / 2
         for m in leases if m.get("minLeasePrice", 0) > 0 and m.get("maxLeasePrice", 0) > 0]
    )
    methods["D. min × leaseCount 가중"] = wavg(
        [(m.get("minLeasePrice", 0), m.get("leaseCount", 0)) for m in leases]
    )
    methods["E. max × leaseCount 가중"] = wavg(
        [(m.get("maxLeasePrice", 0), m.get("leaseCount", 0)) for m in leases]
    )
    methods["F. mid × leaseCount 가중"] = wavg(
        [((m.get("minLeasePrice", 0) + m.get("maxLeasePrice", 0)) / 2, m.get("leaseCount", 0))
         for m in leases if m.get("minLeasePrice", 0) > 0 and m.get("maxLeasePrice", 0) > 0]
    )
    methods["G. min × 세대수 가중"] = wavg(
        [(m.get("minLeasePrice", 0), m.get("totalHouseholdCount", 0)) for m in leases]
    )
    methods["H. max × 세대수 가중"] = wavg(
        [(m.get("maxLeasePrice", 0), m.get("totalHouseholdCount", 0)) for m in leases]
    )
    return methods, len(leases)


def methods_for_deal(markers):
    deals = [m for m in markers if (m.get("dealCount") or 0) > 0]

    def avg(xs):
        xs = [x for x in xs if isinstance(x, (int, float)) and x > 0]
        return int(sum(xs) / len(xs)) if xs else 0

    def wavg(pairs):
        pairs = [(p, w) for p, w in pairs if p > 0 and w > 0]
        if not pairs:
            return 0
        return int(sum(p * w for p, w in pairs) / sum(w for _, w in pairs))

    methods = {}
    methods["A. min 평균"] = avg([m.get("minDealPrice") for m in deals])
    methods["B. median 평균(현재)"] = avg([m.get("medianDealPrice") for m in deals])
    methods["C. max 평균"] = avg([m.get("maxDealPrice") for m in deals])
    methods["D. (min+max)/2 평균"] = avg(
        [(m.get("minDealPrice", 0) + m.get("maxDealPrice", 0)) / 2
         for m in deals if m.get("minDealPrice", 0) > 0 and m.get("maxDealPrice", 0) > 0]
    )
    methods["E. max × dealCount 가중"] = wavg(
        [(m.get("maxDealPrice", 0), m.get("dealCount", 0)) for m in deals]
    )
    methods["F. max × 세대수 가중"] = wavg(
        [(m.get("maxDealPrice", 0), m.get("totalHouseholdCount", 0)) for m in deals]
    )
    methods["G. median × 세대수 가중"] = wavg(
        [(m.get("medianDealPrice", 0), m.get("totalHouseholdCount", 0)) for m in deals]
    )
    def cym(m):
        v = m.get("completionYearMonth")
        try:
            return int(v) if v else 0
        except (ValueError, TypeError):
            return 0

    big = [m for m in deals if (m.get("totalHouseholdCount") or 0) >= 500]
    methods["H. 500세대+ max 평균"] = avg([m.get("maxDealPrice") for m in big])
    new = [m for m in deals if cym(m) >= 201001]
    methods["I. 2010+ max 평균"] = avg([m.get("maxDealPrice") for m in new])
    new_big = [m for m in deals if cym(m) >= 201001 and (m.get("totalHouseholdCount") or 0) >= 300]
    methods["J. 2010+&300세대+ max 평균"] = avg([m.get("maxDealPrice") for m in new_big])

    return methods, len(deals)


def main():
    cortarNo = SEOUL_DISTRICTS["강남구"]

    driver = setup_driver(headless=False)
    try:
        auth = bootstrap_token(driver)
        cortar = fetch_cortar_bbox(driver, cortarNo, auth)
        time.sleep(0.6)
        bbox = None
        if cortar:
            lat, lon = cortar.get("centerLat"), cortar.get("centerLon")
            if lat and lon:
                bbox = {
                    "leftLon": lon - 0.07,
                    "rightLon": lon + 0.07,
                    "topLat": lat + 0.05,
                    "bottomLat": lat - 0.05,
                }

        print("강남구 매매가 산정 방식 비교 (스크린샷 4월값과 차이율)")
        print("=" * 75)

        for pyeong, (a_min, a_max) in PYEONG_BUCKETS.items():
            print(f"\n=== {pyeong}기준 매매 ({a_min}~{a_max}㎡) ===")
            a1 = fetch_markers(driver, cortarNo, "A1", a_min, a_max, auth, bbox)
            time.sleep(0.6)
            if not isinstance(a1, list):
                print(f"  매매 응답 비정상")
                continue

            screenshot_val = SCREENSHOT_GANGNAM[f"{pyeong}기준 매매"]
            methods, n_deals = methods_for_deal(a1)
            print(f"  매매 매물있는 단지: {n_deals}개  /  스크린샷: {screenshot_val:,}")

            ranked = sorted(methods.items(), key=lambda x: abs(x[1] - screenshot_val))
            for name, val in ranked[:5]:  # 상위 5개만
                diff_pct = (val - screenshot_val) / screenshot_val * 100 if screenshot_val else 0
                bar = "★" if abs(diff_pct) < 5 else ("○" if abs(diff_pct) < 15 else " ")
                print(f"    {bar} {name:30s}: {val:>10,} (Δ {diff_pct:+6.1f}%)")

        print("\n" + "=" * 75)
        print("강남구 전세가 산정 방식 비교")
        print("=" * 75)

        for pyeong, (a_min, a_max) in PYEONG_BUCKETS.items():
            print(f"\n=== {pyeong}기준 전세 ({a_min}~{a_max}㎡) ===")
            b1 = fetch_markers(driver, cortarNo, "B1", a_min, a_max, auth, bbox)
            time.sleep(0.6)
            if not isinstance(b1, list):
                continue

            screenshot_val = SCREENSHOT_GANGNAM[f"{pyeong}기준 전세"]
            methods, n_leases = methods_for_lease(b1)
            print(f"  전세 매물있는 단지: {n_leases}개  /  스크린샷: {screenshot_val:,}")
            ranked = sorted(methods.items(), key=lambda x: abs(x[1] - screenshot_val))
            for name, val in ranked[:5]:
                diff_pct = (val - screenshot_val) / screenshot_val * 100 if screenshot_val else 0
                bar = "★" if abs(diff_pct) < 5 else ("○" if abs(diff_pct) < 15 else " ")
                print(f"    {bar} {name:30s}: {val:>10,} (Δ {diff_pct:+6.1f}%)")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
