"""미매칭 928개 단지 원인별 분류.

분류 기준:
  (a) catalog_nan: 면적 또는 준공년월 NaN
  (b) no_trade:   RTMS에 단지명 정확/유사 매칭 없음 (임대단지/거래없음)
  (c) name_var:   단지명 표기 차이 (fuzzy 0.5~0.85 후보 있음, 면적/준공년도 검증은 실패)
  (d) geo_fail:   exact/fuzzy 매칭 있었으나 좌표 검증으로 reject됨
  (e) area_fail:  단지명 일치하나 면적 ±5㎡ 범위에서 거래 없음
  (f) other:      기타
"""
from __future__ import annotations

import difflib
import math
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from rtms_client import ALL_LAWD

CATALOG_RAW = Path("data/candidates_hangang_south_catalog.csv")
RTMS_DIR = Path("data/rtms_trades")
ENRICHED = Path("data/catalog_with_rtms.csv")
OUT_DIAG = Path("data/unmatched_diagnosis.csv")

MAX_GEO_KM_EXACT = 50.0


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
    if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
        return None
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    # 1. 데이터 로딩 — unmatched 단지번호만 추출 후 raw catalog와 직접 조인
    enriched = pd.read_csv(ENRICHED, encoding="utf-8-sig", dtype={"단지번호": str})
    unmatched_ids = set(enriched.loc[enriched["매칭_방식"] == "none", "단지번호"])
    print(f"미매칭 단지: {len(unmatched_ids):,}개")

    raw = pd.read_csv(CATALOG_RAW, encoding="utf-8-sig", dtype={"단지번호": str})
    raw = raw.drop_duplicates("단지번호")
    unmatched = raw[raw["단지번호"].isin(unmatched_ids)].copy()
    print(f"  raw catalog에서 확보: {len(unmatched):,}개")

    # 2. RTMS 통합 로드
    trades_parts = []
    for f in sorted(RTMS_DIR.glob("*.parquet")):
        df = pd.read_parquet(f)
        df["__district"] = f.stem
        trades_parts.append(df)
    all_trades = pd.concat(trades_parts, ignore_index=True)
    all_trades["__norm"] = all_trades["aptNm"].apply(_normalize_name)
    all_trades["sggCd"] = all_trades["sggCd"].astype(str).str.strip()
    norm_groups = all_trades.groupby("__norm").groups
    norm_index = {k: list(v) for k, v in norm_groups.items()}
    fuzzy_candidates = list(norm_index.keys())
    print(f"RTMS unique 단지명: {len(fuzzy_candidates):,}")

    # 3. 자치구 중심점
    centroids = {}
    raw_all = pd.read_csv(CATALOG_RAW, encoding="utf-8-sig", dtype={"단지번호": str})
    raw_all = raw_all.dropna(subset=["위도", "경도"])
    for label, lawd in ALL_LAWD.items():
        sub = raw_all[raw_all["시구"] == label]
        if len(sub) == 0:
            base = label.split()[0]
            sub = raw_all[raw_all["시구"].str.startswith(base, na=False)]
        if len(sub) >= 3:
            centroids[lawd] = (float(sub["위도"].median()), float(sub["경도"].median()))

    # 4. 단지별 진단
    reasons = []
    detail_examples = {k: [] for k in ["a", "b", "c", "d", "e", "f"]}
    for _, row in unmatched.iterrows():
        cat_name = str(row["단지명"])
        cat_norm = _normalize_name(cat_name)
        area_min = row.get("최소면적_㎡")
        area_max = row.get("최대면적_㎡")
        build_yr = None
        if pd.notna(row.get("준공년월")):
            try:
                build_yr = int(str(row["준공년월"])[:4])
            except Exception:
                pass
        cat_lat = row.get("위도")
        cat_lng = row.get("경도")

        # (a) NaN 정보
        if pd.isna(area_min) or pd.isna(area_max) or build_yr is None:
            reasons.append("a_catalog_nan")
            if len(detail_examples["a"]) < 5:
                detail_examples["a"].append((cat_name, row["시구"]))
            continue

        # (b) RTMS에 정확/유사 단지명 후보 없음
        exact_hit = cat_norm in norm_index
        fuzzy_loose = difflib.get_close_matches(cat_norm, fuzzy_candidates, n=3, cutoff=0.5)
        if not exact_hit and not fuzzy_loose:
            reasons.append("b_no_trade")
            if len(detail_examples["b"]) < 5:
                detail_examples["b"].append((cat_name, row["시구"]))
            continue

        # (d) exact 매칭됐지만 좌표 검증 실패
        if exact_hit:
            cands = all_trades.loc[norm_index[cat_norm]]
            # 면적 검증
            area_pass = cands[
                (cands["excluUseAr"] >= area_min - 5) & (cands["excluUseAr"] <= area_max + 5)
            ]
            if len(area_pass) == 0:
                reasons.append("e_area_fail")
                if len(detail_examples["e"]) < 5:
                    rtms_areas = sorted(set(cands["excluUseAr"].round(1).tolist()))[:5]
                    detail_examples["e"].append(
                        (cat_name, row["시구"], f"cat:{area_min}-{area_max}", f"rtms:{rtms_areas}")
                    )
                continue
            # 좌표 검증 - 매칭된 sggCd centroid 거리
            dom_sgg = area_pass["sggCd"].mode().iloc[0]
            centroid = centroids.get(dom_sgg)
            if centroid:
                d = haversine_km(cat_lat, cat_lng, centroid[0], centroid[1])
                if d and d > MAX_GEO_KM_EXACT:
                    reasons.append("d_geo_fail")
                    if len(detail_examples["d"]) < 5:
                        detail_examples["d"].append(
                            (cat_name, row["시구"], f"RTMS sgg={dom_sgg}", f"dist={d:.0f}km")
                        )
                    continue

        # (c) fuzzy 후보는 있는데 모든 검증 실패
        if fuzzy_loose:
            # 0.5~0.85 사이 후보 있는지 확인
            mid_fuzzy = [m for m in fuzzy_loose
                         if 0.5 <= difflib.SequenceMatcher(None, cat_norm, m).ratio() < 0.85]
            if mid_fuzzy:
                reasons.append("c_name_var")
                if len(detail_examples["c"]) < 5:
                    detail_examples["c"].append((cat_name, row["시구"], mid_fuzzy[:2]))
                continue

        reasons.append("f_other")
        if len(detail_examples["f"]) < 5:
            detail_examples["f"].append((cat_name, row["시구"]))

    # 5. 집계
    cnt = Counter(reasons)
    total = len(reasons)
    print(f"\n=== 미매칭 원인 분류 ({total}개) ===")
    label_map = {
        "a_catalog_nan": "(a) catalog 면적/준공년월 NaN",
        "b_no_trade":    "(b) RTMS 거래 없음 (이름 매칭 안 됨)",
        "c_name_var":    "(c) 단지명 표기 차이 (fuzzy 0.5~0.85)",
        "d_geo_fail":    "(d) 좌표 검증 실패 (분류 오류)",
        "e_area_fail":   "(e) 단지명 일치, 면적 범위 불일치",
        "f_other":       "(f) 기타",
    }
    for k in ["a_catalog_nan", "b_no_trade", "c_name_var", "d_geo_fail", "e_area_fail", "f_other"]:
        n = cnt.get(k, 0)
        bar = "█" * int(n / total * 40) if total else ""
        print(f"  {label_map[k]:40s} {n:4d} ({n/total*100:5.1f}%) {bar}")

    print("\n=== 샘플 ===")
    for k, ex in detail_examples.items():
        if ex:
            print(f"\n({k}):")
            for e in ex:
                print(f"  {e}")

    # 결과 CSV 저장
    unmatched["원인"] = reasons
    unmatched[["단지번호", "단지명", "시구", "동", "원인",
               "최소면적_㎡", "최대면적_㎡", "준공년월", "위도", "경도"]] \
        .to_csv(OUT_DIAG, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT_DIAG}")


if __name__ == "__main__":
    main()
