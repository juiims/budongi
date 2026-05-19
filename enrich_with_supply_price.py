"""청약홈 APT 분양정보 + 주택형별 분양정보 → catalog 단지별 분양가 매칭.

데이터 소스 (data.go.kr, CP949 CSV):
  - 한국부동산원_청약홈_APT 분양정보_20251128.csv (15101046) — 주택명·공급위치·모집공고일
  - 한국부동산원_청약홈_APT 주택형별 분양정보_20251128.csv (15101047) — 주택공급면적·공급금액_분양최고금액(만원)

JOIN 키: 주택관리번호

매칭 단계:
  1차 exact:  정규화 주택명 == 정규화 catalog 단지명 + 면적 ±5㎡
  2차 fuzzy:  difflib ratio ≥ 0.78 + 면적 ±5㎡ + 자치구 일치

산출 컬럼 (catalog 단지별):
  - 분양가_만원 (해당 단지 분양가 — 평형별 평균)
  - 분양가_면적 (매칭된 주택공급면적 ㎡)
  - 모집공고일
  - 공급위치
  - 분양가매칭_방식 (exact / fuzzy / none)

산출: data/catalog_with_supply.csv  (catalog_with_rtms.csv 확장)
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

import pandas as pd

CATALOG_WITH_RTMS = Path("data/catalog_with_rtms.csv")
SUPPLY_INFO = Path("data/한국부동산원_청약홈_APT 분양정보_20251128.csv")
SUPPLY_DETAIL = Path("data/한국부동산원_청약홈_APT 주택형별 분양정보_20251128.csv")
OUT = Path("data/catalog_with_supply.csv")


def _normalize_name(s):
    if pd.isna(s):
        return ""
    s = str(s)
    s = re.sub(r"\([^)]*\)", "", s)        # 괄호 제거 (본청약/공공분양 등)
    s = re.sub(r"[A-Z]-?\d+블록", "", s)    # "A-24블록" 제거
    s = re.sub(r"\d+차", "", s)
    s = re.sub(r"\d+단지", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def load_supply() -> pd.DataFrame:
    """두 파일 JOIN → 단지별 평형별 분양가 테이블."""
    info = pd.read_csv(SUPPLY_INFO, encoding="cp949", dtype=str)
    detail = pd.read_csv(SUPPLY_DETAIL, encoding="cp949", dtype=str)
    print(f"분양정보 {len(info):,}건 · 주택형별 {len(detail):,}건")

    info_cols = ["주택관리번호", "주택명", "공급위치", "공급지역명", "공급규모", "모집공고일"]
    info_cols = [c for c in info_cols if c in info.columns]
    detail_cols = ["주택관리번호", "주택형", "주택공급면적", "공급금액_분양최고금액"]
    detail_cols = [c for c in detail_cols if c in detail.columns]

    joined = detail[detail_cols].merge(info[info_cols], on="주택관리번호", how="inner")
    joined["주택공급면적"] = pd.to_numeric(joined["주택공급면적"], errors="coerce")
    joined["공급금액_분양최고금액"] = pd.to_numeric(joined["공급금액_분양최고금액"], errors="coerce")
    joined["모집공고일"] = pd.to_datetime(joined["모집공고일"], errors="coerce")
    joined = joined.dropna(subset=["주택공급면적", "공급금액_분양최고금액"])

    # 분양가 0원 제거 (특별공급만 있는 행 등)
    joined = joined[joined["공급금액_분양최고금액"] > 0]
    print(f"JOIN 결과: {len(joined):,}건 (분양가 > 0)")
    print(f"  주택관리번호 unique: {joined['주택관리번호'].nunique():,}")
    print(f"  주택명 unique: {joined['주택명'].nunique():,}")
    print(f"  연도 범위: {joined['모집공고일'].dt.year.min()}~{joined['모집공고일'].dt.year.max()}")
    return joined


def aggregate_to_complex(supply: pd.DataFrame) -> pd.DataFrame:
    """주택관리번호 단위로 집계 (평형별 분양가 보유)."""
    grouped = supply.groupby("주택관리번호").agg(
        주택명=("주택명", "first"),
        공급위치=("공급위치", "first"),
        공급지역명=("공급지역명", "first"),
        모집공고일=("모집공고일", "first"),
        평형수=("주택형", "nunique"),
        면적_min=("주택공급면적", "min"),
        면적_max=("주택공급면적", "max"),
        분양가_min=("공급금액_분양최고금액", "min"),
        분양가_max=("공급금액_분양최고금액", "max"),
        분양가_median=("공급금액_분양최고금액", "median"),
    ).reset_index()
    grouped["주택명_정규"] = grouped["주택명"].apply(_normalize_name)
    return grouped


def _parse_build_year(s):
    if pd.isna(s):
        return None
    try:
        return int(str(s)[:4])
    except Exception:
        return None


def _date_ok(chosen, build_yr) -> bool:
    """모집공고일과 catalog 준공년월 시점 일관성 — 분양→입주 보통 2-4년.

    catalog 준공년 - 분양 공고년 ∈ [-1, +5] 만 허용.
    -1 이하 = 이미 준공된 구축 단지 + 신규 분양정보 매칭 = fuzzy 오매칭
    """
    if build_yr is None or pd.isna(chosen.get("모집공고일")):
        return True
    diff = build_yr - chosen["모집공고일"].year
    return -1 <= diff <= 5


def match_catalog_to_supply(catalog: pd.DataFrame, supply_agg: pd.DataFrame) -> pd.DataFrame:
    """catalog 단지별 분양가 매칭."""
    supply_norm_map = {}
    for idx, name in zip(supply_agg.index, supply_agg["주택명_정규"]):
        supply_norm_map.setdefault(name, []).append(idx)
    fuzzy_candidates = list(supply_norm_map.keys())

    rows = []
    methods = {"exact": 0, "fuzzy": 0, "date_reject": 0, "none": 0}
    for _, cat in catalog.iterrows():
        cat_name = str(cat.get("단지명", ""))
        cat_norm = _normalize_name(cat_name)
        area_min = pd.to_numeric(cat.get("최소면적_㎡"), errors="coerce")
        area_max = pd.to_numeric(cat.get("최대면적_㎡"), errors="coerce")
        build_yr = _parse_build_year(cat.get("준공년월"))

        out = {"단지번호": cat["단지번호"]}
        method = "none"
        chosen = None
        date_failed = False

        def _try_pick(cands):
            nonlocal date_failed
            if pd.notna(area_min) and pd.notna(area_max):
                cands = cands[
                    (cands["면적_min"] <= area_max + 5) & (cands["면적_max"] >= area_min - 5)
                ]
            for _, c in cands.iterrows():
                if _date_ok(c, build_yr):
                    return c
                date_failed = True
            return None

        # 1차 exact
        if cat_norm in supply_norm_map:
            chosen = _try_pick(supply_agg.loc[supply_norm_map[cat_norm]])
            if chosen is not None:
                method = "exact"

        # 2차 fuzzy
        if chosen is None and cat_norm:
            matches = difflib.get_close_matches(cat_norm, fuzzy_candidates, n=3, cutoff=0.78)
            for m in matches:
                idxs = supply_norm_map.get(m)
                if not idxs:
                    continue
                chosen = _try_pick(supply_agg.loc[idxs])
                if chosen is not None:
                    method = "fuzzy"
                    break

        if chosen is not None:
            out["분양가_만원"] = int(chosen["분양가_median"])
            out["분양가_min_만원"] = int(chosen["분양가_min"])
            out["분양가_max_만원"] = int(chosen["분양가_max"])
            out["분양_면적_min"] = round(float(chosen["면적_min"]), 1)
            out["분양_면적_max"] = round(float(chosen["면적_max"]), 1)
            out["모집공고일"] = str(chosen["모집공고일"].date()) if pd.notna(chosen["모집공고일"]) else None
            out["공급위치"] = chosen.get("공급위치")
        if method == "none" and date_failed:
            method = "date_reject"
        out["분양가매칭_방식"] = method
        methods[method] += 1
        rows.append(out)

    result = pd.DataFrame(rows)
    total = len(catalog)
    print(f"\n=== 분양가 매칭 ({total}개 catalog) ===")
    for k in ["exact", "fuzzy", "date_reject", "none"]:
        n = methods.get(k, 0)
        print(f"  {k:11s}: {n:5d}개 ({n/total*100:5.1f}%)")
    matched = methods["exact"] + methods["fuzzy"]
    print(f"  매칭 합계: {matched}개 ({matched/total*100:.1f}%)")
    print(f"  시점 reject(오매칭 방지): {methods['date_reject']}개")
    return result


def main():
    catalog = pd.read_csv(CATALOG_WITH_RTMS, encoding="utf-8-sig", dtype={"단지번호": str})
    print(f"catalog (RTMS enrich): {len(catalog):,}개")

    supply = load_supply()
    supply_agg = aggregate_to_complex(supply)
    print(f"분양 단지(집계): {len(supply_agg):,}개")

    matched = match_catalog_to_supply(catalog, supply_agg)

    out = catalog.merge(matched, on="단지번호", how="left")

    # 분양가 대비 시세 계산
    out["분양가대비_pct"] = None
    cond = out["분양가_만원"].notna() & out["직전거래_만원"].notna()
    out.loc[cond, "분양가대비_pct"] = (
        out.loc[cond, "직전거래_만원"] / out.loc[cond, "분양가_만원"] * 100
    ).round(1)

    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT} — {len(out):,}행")

    # 매칭 샘플
    matched_only = out[out["분양가_만원"].notna()].copy()
    print(f"\n=== 분양가 매칭 단지 분포 ({len(matched_only)}개) ===")
    if len(matched_only):
        print(f"분양가_만원      평균 {matched_only['분양가_만원'].mean():,.0f} / 중간 {matched_only['분양가_만원'].median():,.0f}")
        if (matched_only["분양가대비_pct"].notna()).sum() > 0:
            ratio = matched_only["분양가대비_pct"].dropna()
            print(f"분양가대비_pct  평균 {ratio.mean():.1f}% / 중간 {ratio.median():.1f}% / 최대 {ratio.max():.1f}%")
            print(f"\n샘플 (분양가 대비 가장 많이 오른 단지 top 5):")
            top = matched_only.sort_values("분양가대비_pct", ascending=False).head(5)
            print(top[["단지명", "시구", "분양가_만원", "직전거래_만원", "분양가대비_pct", "분양가매칭_방식"]].to_string(index=False))


if __name__ == "__main__":
    main()
