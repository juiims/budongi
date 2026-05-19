"""
Outlier 구(양천/종로/중구/성북/금천)에 대해 동 단위 markers를 모은 뒤
여러 산정 방식을 비교 → 어떤 방식이 스크린샷에 가장 가까운지 확인.
"""
import sys
import time

from naver_realty_new import setup_driver, bootstrap_token
from regional_aggregator import fetch_markers, PYEONG_BUCKETS, SEOUL_DISTRICTS
from dong_aggregator import fetch_dongs, dong_bbox, fetch_markers_with_retry
from reverse_engineer import methods_for_deal, methods_for_lease

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DELAY = 0.5

# 스크린샷 평형별 매매 / 전세 (2026.04)
SCREENSHOT = {
    "양천구": {
        "18기준 매매": 100908, "18기준 전세": 28782,
        "21기준 매매": 140385, "21기준 전세": 44982,
        "24기준 매매": 160440, "24기준 전세": 51408,
        "33기준 매매": 178068, "33기준 전세": 72930,
    },
    "종로구": {
        "18기준 매매": 49104, "18기준 전세": 33264,
        "21기준 매매": 96957, "21기준 전세": 49182,
        "24기준 매매": 110808, "24기준 전세": 56208,
        "33기준 매매": 160941, "33기준 전세": 80949,
    },
    "성북구": {
        "18기준 매매": 39798, "18기준 전세": 31626,
        "21기준 매매": 81207, "21기준 전세": 45323,
        "24기준 매매": 92808, "24기준 전세": 49512,
        "33기준 매매": 104412, "33기준 전세": 60621,
    },
    "금천구": {
        "18기준 매매": 38610, "18기준 전세": 24210,
        "21기준 매매": 52374, "21기준 전세": 31941,
        "24기준 매매": 59856, "24기준 전세": 36504,
        "33기준 매매": 74613, "33기준 전세": 47487,
    },
}


def collect_dong_markers(driver, district_cortarNo, auth_holder):
    """동 단위로 markers를 합쳐 (deduped) 평형별 dict 반환."""
    dongs, _ = fetch_dongs(driver, district_cortarNo, auth_holder[0])
    time.sleep(DELAY)
    bucket_a1 = {p: {} for p in PYEONG_BUCKETS}
    bucket_b1 = {p: {} for p in PYEONG_BUCKETS}
    for dong in dongs:
        bbox = dong_bbox(dong)
        for pyeong, (a_min, a_max) in PYEONG_BUCKETS.items():
            a1 = fetch_markers_with_retry(driver, dong["cortarNo"], "A1", a_min, a_max, auth_holder, bbox)
            time.sleep(DELAY)
            b1 = fetch_markers_with_retry(driver, dong["cortarNo"], "B1", a_min, a_max, auth_holder, bbox)
            time.sleep(DELAY)
            for m in a1:
                bucket_a1[pyeong][m.get("markerId")] = m
            for m in b1:
                bucket_b1[pyeong][m.get("markerId")] = m
    return bucket_a1, bucket_b1


def analyze(driver, name, auth_holder):
    print(f"\n{'='*78}")
    print(f"  {name} 분석")
    print(f"{'='*78}")
    cortarNo = SEOUL_DISTRICTS[name]
    bucket_a1, bucket_b1 = collect_dong_markers(driver, cortarNo, auth_holder)

    for pyeong in PYEONG_BUCKETS:
        a_markers = list(bucket_a1[pyeong].values())
        b_markers = list(bucket_b1[pyeong].values())

        print(f"\n--- {pyeong}기준 매매 (markers: {len(a_markers)}, 매물있음: "
              f"{sum(1 for m in a_markers if (m.get('dealCount') or 0)>0)}) ---")
        screen = SCREENSHOT[name].get(f"{pyeong}기준 매매", 0)
        methods, _ = methods_for_deal(a_markers)
        print(f"   스크린샷: {screen:,}")
        for n, v in sorted(methods.items(), key=lambda x: abs(x[1] - screen))[:5]:
            d = (v - screen) / screen * 100 if screen else 0
            bar = "★" if abs(d) < 5 else ("○" if abs(d) < 15 else " ")
            print(f"     {bar} {n:30s}: {v:>10,} (Δ {d:+6.1f}%)")

        print(f"\n--- {pyeong}기준 전세 (markers: {len(b_markers)}, 매물있음: "
              f"{sum(1 for m in b_markers if (m.get('leaseCount') or 0)>0)}) ---")
        screen = SCREENSHOT[name].get(f"{pyeong}기준 전세", 0)
        methods, _ = methods_for_lease(b_markers)
        print(f"   스크린샷: {screen:,}")
        for n, v in sorted(methods.items(), key=lambda x: abs(x[1] - screen))[:5]:
            d = (v - screen) / screen * 100 if screen else 0
            bar = "★" if abs(d) < 5 else ("○" if abs(d) < 15 else " ")
            print(f"     {bar} {n:30s}: {v:>10,} (Δ {d:+6.1f}%)")


def main():
    targets = ["양천구", "종로구", "성북구", "금천구"]
    driver = setup_driver(headless=False)
    try:
        auth_holder = [bootstrap_token(driver)]
        for name in targets:
            analyze(driver, name, auth_holder)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
