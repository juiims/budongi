"""catalog 단지별 가장 가까운 지하철역 정보 enrich.

산출 컬럼 (단지번호 단위):
  - 가까운역_이름
  - 가까운역_노선
  - 가까운역_km           (직선)
  - 가까운역_도보분        (km × 12, 보행속도 5km/h 가정)
  - 가까운역_강남까지_km   (그 역 → 강남역 직선)

산출: data/catalog_subway.csv
"""
import math
from pathlib import Path

import pandas as pd

CATALOG = Path("data/candidates_hangang_south_catalog.csv")
SUBWAY = Path("data/subway_stations.csv")
OUT = Path("data/catalog_subway.csv")

GANGNAM_LAT, GANGNAM_LNG = 37.4979, 127.0276
WALK_MIN_PER_KM = 12  # 보행속도 5km/h


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    catalog = pd.read_csv(CATALOG, encoding="utf-8-sig", dtype={"단지번호": str})
    catalog = catalog.drop_duplicates("단지번호").reset_index(drop=True)
    subway = pd.read_csv(SUBWAY, encoding="utf-8-sig")
    print(f"catalog {len(catalog):,}개 · subway {len(subway):,}개역")

    # 역 → 강남까지 미리 계산 (역 1개당 1회)
    subway = subway.copy()
    subway["강남까지_km"] = subway.apply(
        lambda r: round(haversine_km(r["lat"], r["lng"], GANGNAM_LAT, GANGNAM_LNG), 2),
        axis=1,
    )
    # 역명·노선 그룹핑 (환승역은 여러 line_no → 콤마 결합)
    station_meta = (
        subway.groupby("station_name")
        .agg(
            lat=("lat", "mean"),
            lng=("lng", "mean"),
            lines=("line_no", lambda x: ", ".join(sorted(set(str(v) for v in x)))),
            강남까지_km=("강남까지_km", "min"),
        )
        .reset_index()
    )
    print(f"unique 역 {len(station_meta):,}개 (환승역 통합)")

    lats = station_meta["lat"].values
    lngs = station_meta["lng"].values
    names = station_meta["station_name"].values
    lines = station_meta["lines"].values
    gn = station_meta["강남까지_km"].values

    rows = []
    for _, r in catalog.iterrows():
        lat, lon = r["위도"], r["경도"]
        if pd.isna(lat) or pd.isna(lon):
            rows.append({
                "단지번호": r["단지번호"],
                "가까운역_이름": None, "가까운역_노선": None,
                "가까운역_km": None, "가까운역_도보분": None, "가까운역_강남까지_km": None,
            })
            continue
        # 모든 역까지 거리 (vectorized)
        dlat = [(la - lat) for la in lats]
        # 빠른 근사 → 정확한 haversine 한 번에
        dists = [haversine_km(lat, lon, la, lo) for la, lo in zip(lats, lngs)]
        idx = min(range(len(dists)), key=lambda i: dists[i])
        d = round(dists[idx], 3)
        rows.append({
            "단지번호": r["단지번호"],
            "가까운역_이름": names[idx],
            "가까운역_노선": lines[idx],
            "가까운역_km": d,
            "가까운역_도보분": round(d * WALK_MIN_PER_KM, 1),
            "가까운역_강남까지_km": round(float(gn[idx]), 2),
        })

    enriched = pd.DataFrame(rows)
    enriched.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT} — {len(enriched):,}행")

    # 분포 요약
    valid = enriched.dropna(subset=["가까운역_km"])
    print("\n=== 분포 ===")
    print(f"가까운역_km     평균 {valid['가까운역_km'].mean():.2f} / 중간 {valid['가까운역_km'].median():.2f} / 최대 {valid['가까운역_km'].max():.2f}")
    print(f"가까운역_도보분  평균 {valid['가까운역_도보분'].mean():.1f}분 / 중간 {valid['가까운역_도보분'].median():.1f}분")
    print(f"역→강남_km      평균 {valid['가까운역_강남까지_km'].mean():.2f} / 중간 {valid['가까운역_강남까지_km'].median():.2f} / 최대 {valid['가까운역_강남까지_km'].max():.2f}")

    print("\n=== 가장 많이 매칭된 역 TOP 10 ===")
    print(enriched["가까운역_이름"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
