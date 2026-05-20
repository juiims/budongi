"""RTMS 매매 + 전월세 통합 → 자치구별 전세가율 산출.

전세가율 = (자치구 평균 전세보증금) / (자치구 평균 매매가) × 100

평형 분리:
  - 84㎡(국평) 기준: excluUseAr ∈ [80, 88]
  - 전체 평형 기준 (대안)

기간:
  - 최근 12개월 (현재 수급 신호)
  - 최근 24개월 (안정성)

산출 컬럼 (catalog 단지별, 자치구 단위 신호):
  - 자치구_전세가율_84㎡ (최근 12개월)
  - 자치구_전세가율_전체 (최근 12개월)
  - 자치구_월세비중 (월세 ≥ 1만원 비율) — 보조 신호
  - 자치구_전세거래수_12M

산출: data/catalog_with_jeonse.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CATALOG_RAW = Path("data/candidates_hangang_south_catalog.csv")
RTMS_TRADES_DIR = Path("data/rtms_trades")
RTMS_RENTS_DIR = Path("data/rtms_rents")
OUT = Path("data/catalog_with_jeonse.csv")

GUKPYEONG_MIN = 80   # ㎡
GUKPYEONG_MAX = 88


def load_district_data(dir_: Path) -> pd.DataFrame:
    parts = []
    for f in sorted(dir_.glob("*.parquet")):
        df = pd.read_parquet(f)
        df["__district"] = f.stem
        parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def main():
    catalog = pd.read_csv(CATALOG_RAW, encoding="utf-8-sig", dtype={"단지번호": str})
    catalog = catalog.drop_duplicates("단지번호").reset_index(drop=True)
    print(f"catalog {len(catalog):,}개 단지")

    trades = load_district_data(RTMS_TRADES_DIR)
    rents = load_district_data(RTMS_RENTS_DIR)
    print(f"매매 {len(trades):,}건 · 전월세 {len(rents):,}건")

    if len(rents) == 0:
        raise SystemExit("전월세 데이터 없음 — fetch_rtms_rent_all.py 먼저 실행")

    trades["거래일"] = pd.to_datetime(trades["거래일"])
    rents["거래일"] = pd.to_datetime(rents["거래일"])

    cutoff12 = pd.Timestamp.now() - pd.DateOffset(months=12)

    # 매매 최근 12개월 + 자치구 단위 (84㎡)
    trade12 = trades[trades["거래일"] >= cutoff12].copy()
    trade12_gp = trade12[(trade12["excluUseAr"] >= GUKPYEONG_MIN) & (trade12["excluUseAr"] <= GUKPYEONG_MAX)]
    매매_84 = trade12_gp.groupby("__district")["dealAmount_만원"].mean()
    매매_전체 = trade12.groupby("__district")["dealAmount_만원"].mean()

    # 전세(순수) 최근 12개월
    rent12 = rents[(rents["거래일"] >= cutoff12) & rents["순수전세"]].copy()
    rent12_gp = rent12[(rent12["excluUseAr"] >= GUKPYEONG_MIN) & (rent12["excluUseAr"] <= GUKPYEONG_MAX)]
    전세_84 = rent12_gp.groupby("__district")["deposit_만원"].mean()
    전세_전체 = rent12.groupby("__district")["deposit_만원"].mean()

    # 월세 비중 (월세 1만원+)
    rent12_all = rents[rents["거래일"] >= cutoff12]
    월세비중 = rent12_all.groupby("__district").apply(
        lambda g: round(((g["monthlyRent_만원"] >= 1).sum() / len(g)) * 100, 1) if len(g) else None
    )

    # 자치구 단위 전세가율 산출
    districts = sorted(set(trades["__district"].unique()) & set(rents["__district"].unique()))
    rows = []
    for d in districts:
        s_매84 = 매매_84.get(d)
        s_전84 = 전세_84.get(d)
        s_매A = 매매_전체.get(d)
        s_전A = 전세_전체.get(d)
        ratio_84 = round(s_전84 / s_매84 * 100, 1) if (s_매84 and s_전84) else None
        ratio_전체 = round(s_전A / s_매A * 100, 1) if (s_매A and s_전A) else None
        rows.append({
            "자치구": d,
            "자치구_전세가율_84㎡": ratio_84,
            "자치구_전세가율_전체": ratio_전체,
            "자치구_월세비중_pct": 월세비중.get(d),
            "자치구_전세거래수_12M": int(rent12[rent12["__district"] == d].shape[0]),
            "자치구_매매거래수_12M": int(trade12[trade12["__district"] == d].shape[0]),
        })
    district_df = pd.DataFrame(rows)
    print(f"\n자치구 전세가율 산출: {len(district_df)}개")

    # 자치구 분포 출력
    print("\n=== 전세가율(84㎡) 분포 ===")
    valid = district_df.dropna(subset=["자치구_전세가율_84㎡"])
    if len(valid):
        print(f"  min/25%/중간/75%/max: {valid['자치구_전세가율_84㎡'].min():.1f} / "
              f"{valid['자치구_전세가율_84㎡'].quantile(0.25):.1f} / "
              f"{valid['자치구_전세가율_84㎡'].median():.1f} / "
              f"{valid['자치구_전세가율_84㎡'].quantile(0.75):.1f} / "
              f"{valid['자치구_전세가율_84㎡'].max():.1f}")

    print("\n=== 전세가율 상위 5 / 하위 5 ===")
    print(district_df.sort_values("자치구_전세가율_84㎡", ascending=False).head(5)[
        ["자치구", "자치구_전세가율_84㎡", "자치구_월세비중_pct"]].to_string(index=False))
    print("---")
    print(district_df.sort_values("자치구_전세가율_84㎡", ascending=True).head(5)[
        ["자치구", "자치구_전세가율_84㎡", "자치구_월세비중_pct"]].to_string(index=False))

    # catalog 단지에 시구 매칭하여 자치구 신호 부여
    def match_district(시구):
        if pd.isna(시구):
            return None
        for d in districts:
            if d == 시구:
                return d
        # prefix 매칭 (화성시 동탄구 → 화성시)
        base = str(시구).split()[0]
        for d in districts:
            if d.startswith(base):
                return d
        return None

    catalog["__matched_district"] = catalog["시구"].apply(match_district)
    catalog_out = catalog[["단지번호", "__matched_district"]].merge(
        district_df, left_on="__matched_district", right_on="자치구", how="left"
    ).drop(columns=["__matched_district", "자치구"])

    catalog_out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT} — {len(catalog_out)}행")


if __name__ == "__main__":
    main()
