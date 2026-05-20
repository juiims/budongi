"""모든 자치구 RTMS 거래를 통합하여 catalog 전체에 가격 지표 부여.

핵심: catalog 시구 분류 오류(반포자이가 강남구로 잘못 들어옴 등)를 우회하기 위해
       자치구 키를 무시하고 단지명+면적+준공년도+좌표로 매칭.

매칭 단계:
  1차 exact:   정규화 단지명 완전 일치 + 면적 ±5㎡ + 좌표 ≤ EXACT_MAX_GEO_KM
  2차 fuzzy:   difflib ratio ≥ 0.85 + 면적 ±3㎡ + 준공년도 일치 + 좌표 ≤ FUZZY_MAX_GEO_KM
  3차 geo:     단지명 무시 + 좌표 인근 (sggCd,umdNm) ±2km + 면적 ±3㎡ + 준공년도 일치
               → 가장 흔한 aptNm 선택 (단지명 표기 차이 우회)

산출: data/catalog_with_rtms.csv (catalog_scored.csv 컬럼 + 가격 지표)
"""
from __future__ import annotations

import difflib
import math
import re
import time
from pathlib import Path

import pandas as pd

from lib.rtms_client import ALL_LAWD

CATALOG_SCORED = Path("data/catalog_scored.csv")
CATALOG_RAW = Path("data/candidates_hangang_south_catalog.csv")
RTMS_DIR = Path("data/rtms_trades")
OUT_PATH = Path("data/catalog_with_rtms.csv")

FUZZY_CUTOFF = 0.85
EXACT_AREA_TOL = 5    # ㎡
FUZZY_AREA_TOL = 3    # ㎡
EXACT_MAX_GEO_KM = 10.0   # exact: "래미안"·"푸르지오" 등 흔한 정규화명의 동명단지 매칭 방지 (다른 시 유입 차단)
FUZZY_MAX_GEO_KM = 15.0   # fuzzy: 자치구 인접 정도만 허용
GEO_UMD_RADIUS_KM = 2.0   # 3차 geo: 인근 (sggCd, umdNm) 후보 반경
GEO_AREA_TOL = 3      # 3차 geo: 면적 ±3㎡


def _normalize_name(s):
    if pd.isna(s):
        return ""
    s = str(s)
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\d+차", "", s)
    s = re.sub(r"\d+단지", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def build_umd_centroids() -> dict:
    """(sggCd, umdNm) → (lat, lng) 중심점 — catalog 같은 자치구·동 단지들의 좌표 중앙값.

    catalog 동 분류 일부 오류 있지만 다수결로 중심점은 정확.
    """
    raw = pd.read_csv(CATALOG_RAW, encoding="utf-8-sig", dtype={"단지번호": str})
    raw = raw.dropna(subset=["위도", "경도", "동"])
    centroids = {}
    for (시구, 동), grp in raw.groupby(["시구", "동"]):
        if len(grp) < 2:
            continue
        # 시구 → sggCd 변환 (가짜 자치구는 prefix로)
        sgg = None
        if 시구 in ALL_LAWD:
            sgg = ALL_LAWD[시구]
        else:
            base = str(시구).split()[0]
            for label, lawd in ALL_LAWD.items():
                if label == base or label.startswith(base):
                    sgg = lawd
                    break
        if sgg is None:
            continue
        centroids[(sgg, 동)] = (float(grp["위도"].median()), float(grp["경도"].median()))
    return centroids


def build_district_centroids() -> dict:
    """LAWD → 중심점 좌표 (catalog 자체에서 시구별 좌표 중앙값으로 산출).

    catalog의 가짜 자치구 분류(화성시 동탄구/효행구 등) 대응을 위해 prefix 매칭 fallback.
    """
    raw = pd.read_csv(CATALOG_RAW, encoding="utf-8-sig", dtype={"단지번호": str})
    raw = raw.dropna(subset=["위도", "경도"])
    centroids = {}
    missing = []
    for label, lawd in ALL_LAWD.items():
        sub = raw[raw["시구"] == label]
        if len(sub) == 0:
            # "성남시 분당구" → "성남시" 시작 모두
            base = label.split()[0]
            sub = raw[raw["시구"].str.startswith(base, na=False)]
        if len(sub) >= 3:
            centroids[lawd] = (float(sub["위도"].median()), float(sub["경도"].median()))
        else:
            missing.append((label, lawd, len(sub)))
    if missing:
        print(f"  ⚠ 중심점 산출 실패 {len(missing)}개: {[m[0] for m in missing]} — 좌표검증 스킵")
    return centroids


def load_all_trades() -> pd.DataFrame:
    files = sorted(RTMS_DIR.glob("*.parquet"))
    if not files:
        raise SystemExit(f"RTMS 파일 없음: {RTMS_DIR}/*.parquet")
    parts = []
    for f in files:
        df = pd.read_parquet(f)
        df["__district"] = f.stem
        parts.append(df)
    all_df = pd.concat(parts, ignore_index=True)
    all_df["거래일"] = pd.to_datetime(all_df["거래일"])
    all_df["__norm"] = all_df["aptNm"].apply(_normalize_name)
    print(f"통합 거래: {len(all_df):,}건 · {len(files)}개 자치구 · "
          f"unique 단지명 {all_df['__norm'].nunique():,}개")
    return all_df


def _geo_verify(matched: pd.DataFrame, cat_lat: float, cat_lng: float,
                centroids: dict, max_km: float) -> bool:
    """매칭된 trades의 dominant sggCd 중심점 ↔ catalog 좌표 거리 검증."""
    if pd.isna(cat_lat) or pd.isna(cat_lng) or len(matched) == 0:
        return True
    dominant_sgg = matched["sggCd"].mode()
    if len(dominant_sgg) == 0:
        return True
    centroid = centroids.get(dominant_sgg.iloc[0])
    if centroid is None:
        return True
    d = haversine_km(cat_lat, cat_lng, centroid[0], centroid[1])
    return d <= max_km


def _select_by_geo(matched: pd.DataFrame, cat_lat: float, cat_lng: float,
                   centroids: dict, max_km: float) -> pd.DataFrame:
    """동명이단지(여러 sggCd 후보) 중 catalog 좌표와 가장 가까운 sggCd 만 선택."""
    if pd.isna(cat_lat) or pd.isna(cat_lng):
        dominant = matched["sggCd"].mode().iloc[0]
        return matched[matched["sggCd"] == dominant]
    best_sgg = None
    best_d = float("inf")
    for sgg in matched["sggCd"].unique():
        centroid = centroids.get(sgg)
        if centroid is None:
            continue
        d = haversine_km(cat_lat, cat_lng, centroid[0], centroid[1])
        if d < best_d:
            best_d = d
            best_sgg = sgg
    if best_sgg is None or best_d > max_km:
        return pd.DataFrame()
    return matched[matched["sggCd"] == best_sgg]


def match_single(cat_row: pd.Series, all_trades: pd.DataFrame,
                 norm_index: dict, fuzzy_candidates: list[str],
                 centroids: dict) -> tuple[pd.DataFrame, str]:
    cat_name = str(cat_row["단지명"])
    cat_norm = _normalize_name(cat_name)
    cat_lat = cat_row.get("위도")
    cat_lng = cat_row.get("경도")
    area_min = cat_row.get("최소면적_㎡")
    area_max = cat_row.get("최대면적_㎡")
    build_yr = None
    if pd.notna(cat_row.get("준공년월")):
        try:
            build_yr = int(str(cat_row["준공년월"])[:4])
        except Exception:
            pass

    # 1차 exact: 정규화 단지명 완전 일치
    exact_idx = norm_index.get(cat_norm)
    if exact_idx is not None and len(exact_idx) > 0:
        candidates = all_trades.loc[exact_idx]
        # 면적 필터 (있을 때만)
        # 면적 미일치 시 전체 후보로 fallback하지 않음 — catalog 공급면적 vs RTMS 전용면적
        # 차이가 커서 다 unmatch일 가능성도 있지만, 다른 단지일 가능성이 더 크기 때문.
        if pd.notna(area_min) and pd.notna(area_max):
            verified = candidates[
                (candidates["excluUseAr"] >= area_min - EXACT_AREA_TOL)
                & (candidates["excluUseAr"] <= area_max + EXACT_AREA_TOL)
            ]
        else:
            verified = candidates

        if len(verified) > 0:
            if verified["sggCd"].nunique() > 1:
                # 동명이단지 — catalog 좌표로 disambiguate
                selected = _select_by_geo(verified, cat_lat, cat_lng, centroids, EXACT_MAX_GEO_KM)
                if len(selected) > 0:
                    return selected, "exact"
            elif _geo_verify(verified, cat_lat, cat_lng, centroids, EXACT_MAX_GEO_KM):
                return verified, "exact"

    # 2차 fuzzy: cutoff 0.85 + 면적 AND 준공년도 + 좌표 검증
    matches = difflib.get_close_matches(cat_norm, fuzzy_candidates, n=5, cutoff=FUZZY_CUTOFF)
    if matches:
        idxs = []
        for m in matches:
            i = norm_index.get(m)
            if i is not None:
                idxs.extend(i)
        if idxs:
            fuzzy = all_trades.loc[idxs]
            mask = pd.Series(True, index=fuzzy.index)
            if pd.notna(area_min) and pd.notna(area_max):
                mask &= (fuzzy["excluUseAr"] >= area_min - FUZZY_AREA_TOL) \
                      & (fuzzy["excluUseAr"] <= area_max + FUZZY_AREA_TOL)
            if build_yr:
                mask &= fuzzy["buildYear"] == build_yr
            verified = fuzzy[mask]
            if len(verified) > 0 and _geo_verify(verified, cat_lat, cat_lng, centroids, FUZZY_MAX_GEO_KM):
                return verified, "fuzzy"

    return pd.DataFrame(), "none"


def match_by_geo(cat_row: pd.Series, all_trades: pd.DataFrame,
                 umd_centroids: dict, umd_trade_index: dict) -> tuple[pd.DataFrame, str]:
    """3차 geo 매칭: 단지명 무시, 좌표 인근 동 + 면적 + 준공년도로 매칭."""
    cat_lat = cat_row.get("위도")
    cat_lng = cat_row.get("경도")
    area_min = cat_row.get("최소면적_㎡")
    area_max = cat_row.get("최대면적_㎡")
    if pd.isna(cat_lat) or pd.isna(cat_lng) or pd.isna(area_min) or pd.isna(area_max):
        return pd.DataFrame(), "none"
    build_yr = None
    if pd.notna(cat_row.get("준공년월")):
        try:
            build_yr = int(str(cat_row["준공년월"])[:4])
        except Exception:
            pass
    if build_yr is None:
        return pd.DataFrame(), "none"

    # 인근 (sggCd, umdNm) 후보 — 반경 GEO_UMD_RADIUS_KM
    nearby_keys = []
    for key, (lat, lng) in umd_centroids.items():
        d = haversine_km(cat_lat, cat_lng, lat, lng)
        if d <= GEO_UMD_RADIUS_KM:
            nearby_keys.append((key, d))
    if not nearby_keys:
        return pd.DataFrame(), "none"
    nearby_keys.sort(key=lambda x: x[1])  # 가까운 순

    # 후보 키의 trades 인덱스 모으기
    all_idxs = []
    for key, _ in nearby_keys:
        idxs = umd_trade_index.get(key)
        if idxs:
            all_idxs.extend(idxs)
    if not all_idxs:
        return pd.DataFrame(), "none"

    candidates = all_trades.loc[all_idxs]
    matched = candidates[
        (candidates["excluUseAr"] >= area_min - GEO_AREA_TOL)
        & (candidates["excluUseAr"] <= area_max + GEO_AREA_TOL)
        & (candidates["buildYear"] == build_yr)
    ]
    if len(matched) == 0:
        return pd.DataFrame(), "none"

    # 가장 흔한 aptNm 선택 (단지명 표기 차이 흡수)
    dominant_apt = matched["aptNm"].mode()
    if len(dominant_apt) == 0:
        return pd.DataFrame(), "none"
    final = matched[matched["aptNm"] == dominant_apt.iloc[0]]
    return final, "geo"


def _cluster_main_pyeong(matched: pd.DataFrame) -> pd.DataFrame:
    """단지 내 거래에서 가장 거래 많은 면적대(±3㎡) 추출 — 메인 평형 한정 분석.

    단지 내 33평/24평 혼재 시 가격대 다른 거래가 섞여 회복률 outlier 발생.
    면적 분포의 최빈값을 중심으로 ±3㎡ 클러스터링.
    """
    if len(matched) == 0:
        return matched
    # 면적 반올림으로 그룹핑 후 거래 가장 많은 면적 선택
    rounded = matched["excluUseAr"].round().astype(int)
    main_area = rounded.mode().iloc[0] if len(rounded) > 0 else None
    if main_area is None:
        return matched
    return matched[(matched["excluUseAr"] >= main_area - 3)
                   & (matched["excluUseAr"] <= main_area + 3)]


def aggregate(matched: pd.DataFrame) -> dict:
    if len(matched) == 0:
        return {}
    sorted_ = matched.sort_values("거래일")
    high = sorted_.loc[sorted_["dealAmount_만원"].idxmax()]
    low = sorted_.loc[sorted_["dealAmount_만원"].idxmin()]
    last = sorted_.iloc[-1]
    first = sorted_.iloc[0]  # 첫거래 = 분양 직후 가격 대용 (옵션 C)
    cutoff6 = pd.Timestamp.now() - pd.DateOffset(months=6)
    cutoff12 = pd.Timestamp.now() - pd.DateOffset(months=12)
    recent6 = (sorted_["거래일"] >= cutoff6).sum()
    recent12 = (sorted_["거래일"] >= cutoff12).sum()
    recovery = round(last["dealAmount_만원"] / high["dealAmount_만원"] * 100, 1) \
        if high["dealAmount_만원"] else None
    first_ratio = round(last["dealAmount_만원"] / first["dealAmount_만원"] * 100, 1) \
        if first["dealAmount_만원"] else None

    # 메인 평형 한정 회복률 (33평/24평 혼재 outlier 방지)
    main = _cluster_main_pyeong(matched)
    main_sorted = main.sort_values("거래일") if len(main) > 0 else sorted_
    main_high = main_sorted.loc[main_sorted["dealAmount_만원"].idxmax()] if len(main_sorted) else high
    main_last = main_sorted.iloc[-1] if len(main_sorted) else last
    main_recovery = round(main_last["dealAmount_만원"] / main_high["dealAmount_만원"] * 100, 1) \
        if main_high["dealAmount_만원"] else None
    main_area = round(float(main["excluUseAr"].median()), 1) if len(main) > 0 else None

    # 신뢰도 라벨: 매칭 거래수 기반
    if len(matched) >= 30:
        confidence = "높음"
    elif len(matched) >= 10:
        confidence = "중간"
    elif len(matched) >= 3:
        confidence = "낮음"
    else:
        confidence = "매우낮음"

    return {
        "전고점_만원": int(high["dealAmount_만원"]),
        "전고점_거래일": str(high["거래일"].date()),
        "전저점_만원": int(low["dealAmount_만원"]),
        "전저점_거래일": str(low["거래일"].date()),
        "직전거래_만원": int(last["dealAmount_만원"]),
        "직전거래_거래일": str(last["거래일"].date()),
        "첫거래_만원": int(first["dealAmount_만원"]),
        "첫거래_거래일": str(first["거래일"].date()),
        "첫거래대비_pct": first_ratio,
        "회복률_pct": recovery,
        "메인평형_㎡": main_area,
        "메인평형_회복률_pct": main_recovery,
        "메인평형_거래수": len(main),
        "최근6개월_거래수": int(recent6),
        "최근12개월_거래수": int(recent12),
        "매칭_거래수": len(matched),
        "RTMS_신뢰도": confidence,
        "RTMS_자치구": matched["__district"].mode().iloc[0] if len(matched) else None,
    }


def main():
    t0 = time.time()
    catalog = pd.read_csv(CATALOG_SCORED, encoding="utf-8-sig", dtype={"단지번호": str})
    catalog = catalog.drop_duplicates("단지번호").reset_index(drop=True)
    # 좌표 보강 — catalog_scored에 위도/경도가 없으면 raw에서 가져옴
    if "위도" not in catalog.columns or "경도" not in catalog.columns:
        raw = pd.read_csv(CATALOG_RAW, encoding="utf-8-sig", dtype={"단지번호": str})
        raw = raw.drop_duplicates("단지번호")[["단지번호", "위도", "경도", "최소면적_㎡", "최대면적_㎡"]]
        catalog = catalog.merge(raw, on="단지번호", how="left")
    print(f"catalog: {len(catalog):,}개 단지")

    print("자치구·동 중심점 산출 중...")
    centroids = build_district_centroids()
    umd_centroids = build_umd_centroids()
    print(f"  자치구 {len(centroids)}개 · (자치구,동) {len(umd_centroids)}개")

    all_trades = load_all_trades()
    all_trades["sggCd"] = all_trades["sggCd"].astype(str).str.strip()
    all_trades["umdNm"] = all_trades["umdNm"].astype(str).str.strip()

    print("인덱스 구축 중...")
    norm_groups = all_trades.groupby("__norm").groups
    norm_index = {k: list(v) for k, v in norm_groups.items()}
    fuzzy_candidates = list(norm_index.keys())
    # (sggCd, umdNm) → trade index list (3차 geo 매칭용)
    umd_groups = all_trades.groupby(["sggCd", "umdNm"]).groups
    umd_trade_index = {k: list(v) for k, v in umd_groups.items()}
    print(f"  단지명 {len(fuzzy_candidates):,}개 · (sggCd,umdNm) {len(umd_trade_index):,}개")

    rows = []
    methods = {"exact": 0, "fuzzy": 0, "geo": 0, "none": 0}
    t1 = time.time()
    for i, row in catalog.iterrows():
        matched, method = match_single(row, all_trades, norm_index, fuzzy_candidates, centroids)
        if method == "none":
            matched, method = match_by_geo(row, all_trades, umd_centroids, umd_trade_index)
        methods[method] += 1
        agg = aggregate(matched) if method != "none" else {}
        rows.append({
            "단지번호": row["단지번호"],
            "단지명": row["단지명"],
            "원소속자치구": row["시구"],
            "동": row["동"],
            "매칭_방식": method,
            **agg,
        })
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(catalog)} — exact {methods['exact']} · "
                  f"fuzzy {methods['fuzzy']} · geo {methods['geo']} · "
                  f"none {methods['none']} ({(time.time()-t1):.0f}초)")

    enriched = pd.DataFrame(rows)
    total = len(catalog)
    matched_n = methods["exact"] + methods["fuzzy"] + methods["geo"]
    print(f"\n=== 최종 매칭 ({total}개 단지) ===")
    for m, n in methods.items():
        print(f"  {m:7s}: {n:5d}개 ({n/total*100:5.1f}%)")
    print(f"  -----")
    print(f"  매칭 합계: {matched_n}개 ({matched_n/total*100:.1f}%)")

    # 시구 분류 오류 통계
    err = enriched[
        (enriched["RTMS_자치구"].notna())
        & (enriched["원소속자치구"] != enriched["RTMS_자치구"])
    ]
    print(f"\ncatalog 시구 ≠ RTMS 매칭 자치구: {len(err)}건 (catalog 분류 오류 추정)")
    if len(err):
        print(err[["단지명", "원소속자치구", "RTMS_자치구"]].head(10).to_string(index=False))

    # 최종 병합 — 원본 catalog_scored에 가격 컬럼 추가
    merged = catalog.merge(
        enriched.drop(columns=["단지명", "원소속자치구", "동"]),
        on="단지번호", how="left",
    )
    merged.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT_PATH} — {len(merged)}행 · "
          f"총 {time.time()-t0:.0f}초")


if __name__ == "__main__":
    main()
