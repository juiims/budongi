"""RTMS 거래 시계열 → catalog 단지별 가격 지표 집계.

매칭 전략 (catalog 동 분류가 부정확한 것으로 확인됨 — 동 키 사용 안 함):
  1차 exact:   자치구 내 정규화 단지명 완전 일치 + 면적 ∈ [최소,최대] ± 1㎡
  2차 fuzzy:   자치구 내 단지명 difflib ratio ≥ 0.75 + 면적 + 준공년도 일치
  3차 fallback: 자치구 내 면적 + 준공년도 단독 매칭 (단지명 매칭 완전 실패 시)

산출 컬럼 (catalog 단지별):
  - 전고점_만원 / 전고점_거래일
  - 전저점_만원 / 전저점_거래일
  - 직전거래_만원 / 직전거래_거래일
  - 회복률_pct   (직전거래 ÷ 전고점 × 100)
  - 최근6개월_거래수
  - 매칭_거래수
  - 매칭_방식    (exact / fuzzy / fallback / none)

사용:
    python enrich_with_rtms.py 강남구
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

import pandas as pd

CATALOG_PATH = Path("data/candidates_hangang_south_catalog.csv")
RTMS_DIR = Path("data/rtms_trades")
OUT_PATH = Path("data/catalog_rtms_enriched.csv")


def _normalize_name(s: str) -> str:
    """단지명 정규화 — 공백·괄호·차수 제거."""
    if pd.isna(s):
        return ""
    s = str(s)
    s = re.sub(r"\([^)]*\)", "", s)        # 괄호 내용 제거
    s = re.sub(r"\d+차", "", s)             # "2차" 제거
    s = re.sub(r"\d+단지", "", s)           # "5단지" 제거
    s = re.sub(r"\s+", "", s)               # 공백 제거
    return s


def _name_keywords(s: str) -> set[str]:
    """단지명에서 핵심 키워드 추출 (3글자 이상)."""
    norm = _normalize_name(s)
    # 영문/숫자 제외하고 한글 2글자 이상 토큰
    tokens = re.findall(r"[가-힣]{2,}", norm)
    return set(tokens)


def match_catalog_to_trades(cat_row: pd.Series, trades_district: pd.DataFrame,
                             unique_names_cache: dict | None = None) -> tuple[pd.DataFrame, str]:
    """단일 catalog 단지 → 매칭된 거래 DataFrame + 매칭 방식.

    trades_district: 해당 자치구 전체 거래 (동 무관)
    """
    cat_name = str(cat_row["단지명"])
    cat_norm = _normalize_name(cat_name)
    area_min = cat_row.get("최소면적_㎡")
    area_max = cat_row.get("최대면적_㎡")
    build_yr = None
    if pd.notna(cat_row.get("준공년월")):
        try:
            build_yr = int(str(cat_row["준공년월"])[:4])
        except Exception:
            pass

    if len(trades_district) == 0:
        return pd.DataFrame(), "none"

    if "__norm" not in trades_district.columns:
        trades_district = trades_district.copy()
        trades_district["__norm"] = trades_district["aptNm"].apply(_normalize_name)

    # 1차 exact: 정규화 단지명 완전 일치만 (면적 무관 — catalog 면적 범위는 신뢰성 낮음)
    exact = trades_district[trades_district["__norm"] == cat_norm]
    if len(exact) > 0:
        # 단지명 일치 + 면적 ±5㎡ 검증 통과하면 신뢰
        if pd.notna(area_min) and pd.notna(area_max):
            verified = exact[
                (exact["excluUseAr"] >= area_min - 5)
                & (exact["excluUseAr"] <= area_max + 5)
            ]
            if len(verified) > 0:
                return verified, "exact"
        return exact, "exact"

    # 2차 fuzzy: difflib ratio ≥ 0.78
    unique_norms = (unique_names_cache.get("norms")
                    if unique_names_cache else trades_district["__norm"].unique())
    candidates = difflib.get_close_matches(cat_norm, unique_norms, n=3, cutoff=0.78)
    if candidates:
        fuzzy = trades_district[trades_district["__norm"].isin(candidates)]
        # fuzzy는 보조 검증 (면적 또는 준공년도) 통과 시만
        if pd.notna(area_min) and pd.notna(area_max):
            verified = fuzzy[
                (fuzzy["excluUseAr"] >= area_min - 5)
                & (fuzzy["excluUseAr"] <= area_max + 5)
            ]
            if len(verified) > 0:
                return verified, "fuzzy"
        elif build_yr:
            verified = fuzzy[fuzzy["buildYear"] == build_yr]
            if len(verified) > 0:
                return verified, "fuzzy"

    return pd.DataFrame(), "none"


def aggregate_trades(matched: pd.DataFrame) -> dict:
    """매칭된 거래 → 단지별 집계 지표."""
    if len(matched) == 0:
        return {}
    sorted_ = matched.sort_values("거래일")
    high = sorted_.loc[sorted_["dealAmount_만원"].idxmax()]
    low = sorted_.loc[sorted_["dealAmount_만원"].idxmin()]
    last = sorted_.iloc[-1]

    # 최근 6개월 거래수
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
    recent6 = (sorted_["거래일"] >= cutoff).sum()

    recovery = round(last["dealAmount_만원"] / high["dealAmount_만원"] * 100, 1) \
        if high["dealAmount_만원"] else None

    return {
        "전고점_만원": int(high["dealAmount_만원"]),
        "전고점_거래일": str(high["거래일"].date()),
        "전저점_만원": int(low["dealAmount_만원"]),
        "전저점_거래일": str(low["거래일"].date()),
        "직전거래_만원": int(last["dealAmount_만원"]),
        "직전거래_거래일": str(last["거래일"].date()),
        "회복률_pct": recovery,
        "최근6개월_거래수": int(recent6),
        "매칭_거래수": len(matched),
    }


def enrich(district_label: str) -> pd.DataFrame:
    catalog = pd.read_csv(CATALOG_PATH, encoding="utf-8-sig", dtype={"단지번호": str})
    cat = catalog[catalog["시구"] == district_label].drop_duplicates("단지번호").reset_index(drop=True)

    rtms_path = RTMS_DIR / f"{district_label}.parquet"
    if not rtms_path.exists():
        raise SystemExit(f"RTMS 파일 없음: {rtms_path} — 먼저 fetch_rtms_district.py 실행")

    trades = pd.read_parquet(rtms_path)
    trades["거래일"] = pd.to_datetime(trades["거래일"])
    trades["__norm"] = trades["aptNm"].apply(_normalize_name)
    print(f"{district_label}: catalog {len(cat)}개 단지, RTMS {len(trades):,}건 거래")
    name_cache = {"norms": trades["__norm"].unique().tolist()}

    out_rows = []
    methods = {"exact": 0, "fuzzy": 0, "none": 0}
    for _, row in cat.iterrows():
        matched, method = match_catalog_to_trades(row, trades, name_cache)
        methods[method] += 1
        agg = aggregate_trades(matched) if method != "none" else {}
        out_rows.append({
            "단지번호": row["단지번호"],
            "단지명": row["단지명"],
            "동": row["동"],
            "시구": row["시구"],
            "매칭_방식": method,
            **agg,
        })

    out = pd.DataFrame(out_rows)
    total = len(cat)
    print(f"\n매칭 결과 ({district_label}):")
    for m, n in methods.items():
        print(f"  {m:9s}: {n:4d}개 ({n/total*100:5.1f}%)")
    matched_total = methods["exact"] + methods["fuzzy"]
    print(f"  -------")
    print(f"  매칭 합계: {matched_total}개 ({matched_total/total*100:.1f}%)")

    return out


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "강남구"
    df = enrich(label)
    print(f"\n샘플 (회복률 낮은 순 5개):")
    sample = df[df["매칭_방식"] != "none"].sort_values("회복률_pct").head(5)
    print(sample[["단지명", "동", "매칭_방식", "전고점_만원", "직전거래_만원",
                  "회복률_pct", "매칭_거래수"]].to_string(index=False))
    print(f"\n샘플 (전고점 갱신 — 회복률 ≥ 100):")
    high = df[(df["매칭_방식"] != "none") & (df["회복률_pct"] >= 100)].head(5)
    print(high[["단지명", "동", "전고점_만원", "직전거래_만원", "회복률_pct"]].to_string(index=False))

    out_path = Path(f"data/rtms_enriched_{label}.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")
