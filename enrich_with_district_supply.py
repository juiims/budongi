"""자치구 수급 신호 — RTMS 매매 데이터 자체에서 derive.

외부 API/다운로드 없이 우리가 가진 자료로 자치구별 신호 산출:
  - 최근 12개월 거래량 vs 5년 평균 거래량 비율 → "거래 활성도"
  - 최근 12개월 평균가 vs 5년 평균가 비율 → "가격 모멘텀"
  - catalog 2020+ 신축 단지 비율 → "공급 추정"

산출 컬럼 (단지 단위, 단지번호 기준):
  - 자치구_거래활성도 (1.0 = 5년 평균, >1 = 증가, <1 = 감소)
  - 자치구_가격모멘텀 (1.0 = 5년 평균)
  - 자치구_신축비율 (2020+ 입주 단지 비율, 0~1)
  - 자치구_수급점수 (0~100, 세 요소 가중)

산출: data/catalog_with_district_supply.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CATALOG_RAW = Path("data/candidates_hangang_south_catalog.csv")
RTMS_DIR = Path("data/rtms_trades")
OUT = Path("data/catalog_with_district_supply.csv")


def load_all_trades() -> pd.DataFrame:
    parts = []
    for f in sorted(RTMS_DIR.glob("*.parquet")):
        df = pd.read_parquet(f)
        df["__district"] = f.stem
        parts.append(df)
    all_df = pd.concat(parts, ignore_index=True)
    all_df["거래일"] = pd.to_datetime(all_df["거래일"])
    return all_df


def compute_district_signals(trades: pd.DataFrame) -> pd.DataFrame:
    """자치구별 수급 신호 산출."""
    now = pd.Timestamp.now()
    cutoff12 = now - pd.DateOffset(months=12)

    out = []
    for district, grp in trades.groupby("__district"):
        recent = grp[grp["거래일"] >= cutoff12]
        if len(grp) < 100:  # 데이터 부족 자치구 스킵
            continue
        # 거래량 활성도: 최근 12M 월평균 ÷ 전체기간 월평균
        total_months = max(
            1, ((grp["거래일"].max() - grp["거래일"].min()).days // 30) or 1
        )
        avg_monthly_total = len(grp) / total_months
        avg_monthly_recent = len(recent) / 12 if len(recent) > 0 else 0
        activity = (avg_monthly_recent / avg_monthly_total) if avg_monthly_total > 0 else 0

        # 가격 모멘텀: 최근 12M 평균가 ÷ 전체 평균가
        if len(recent) > 0:
            momentum = recent["dealAmount_만원"].mean() / grp["dealAmount_만원"].mean()
        else:
            momentum = None

        out.append({
            "자치구": district,
            "전체거래수": len(grp),
            "최근12M거래수": len(recent),
            "월평균_전체": round(avg_monthly_total, 1),
            "월평균_최근12M": round(avg_monthly_recent, 1),
            "자치구_거래활성도": round(activity, 3),
            "자치구_가격모멘텀": round(momentum, 3) if momentum else None,
        })
    return pd.DataFrame(out)


def compute_district_new_ratio(catalog: pd.DataFrame) -> pd.DataFrame:
    """자치구별 신축(2020+) 단지 비율."""
    catalog = catalog.dropna(subset=["준공년월"]).copy()
    catalog["__year"] = catalog["준공년월"].astype(str).str[:4].apply(
        lambda s: int(s) if s.isdigit() else None
    )
    catalog = catalog.dropna(subset=["__year"])
    grouped = catalog.groupby("시구").apply(
        lambda g: (g["__year"] >= 2020).sum() / len(g)
    ).reset_index(name="자치구_신축비율")
    grouped["자치구_신축비율"] = grouped["자치구_신축비율"].round(3)
    return grouped


def main():
    catalog = pd.read_csv(CATALOG_RAW, encoding="utf-8-sig", dtype={"단지번호": str})
    catalog = catalog.drop_duplicates("단지번호").reset_index(drop=True)
    print(f"catalog {len(catalog):,}개 단지")

    trades = load_all_trades()
    print(f"통합 거래 {len(trades):,}건 · {trades['__district'].nunique()}개 자치구")

    district_sig = compute_district_signals(trades)
    new_ratio = compute_district_new_ratio(catalog)
    print(f"\n자치구 신호 {len(district_sig)}개 / 신축비율 {len(new_ratio)}개")

    # catalog 시구 → 자치구 매핑 (대부분 일치, "화성시 동탄구" 같이 가짜는 prefix)
    # 자치구 컬럼(parquet 파일명)과 catalog 시구가 다를 수 있어 prefix 매칭
    def match_district(catalog_시구):
        if pd.isna(catalog_시구):
            return None
        # 직접 매칭
        match = district_sig[district_sig["자치구"] == catalog_시구]
        if len(match) > 0:
            return match.iloc[0]
        # prefix 매칭 (화성시 동탄구 → 화성시)
        base = str(catalog_시구).split()[0]
        match = district_sig[district_sig["자치구"].str.startswith(base, na=False)]
        if len(match) > 0:
            return match.iloc[0]
        return None

    rows = []
    for _, c in catalog.iterrows():
        sig = match_district(c["시구"])
        new_r = new_ratio[new_ratio["시구"] == c["시구"]]
        new_r_val = new_r.iloc[0]["자치구_신축비율"] if len(new_r) else None

        row = {"단지번호": c["단지번호"]}
        if sig is not None:
            row["자치구_거래활성도"] = sig["자치구_거래활성도"]
            row["자치구_가격모멘텀"] = sig["자치구_가격모멘텀"]
        row["자치구_신축비율"] = new_r_val

        # 수급점수: 활성도(50%) + 가격모멘텀(30%) + 신축비율 역(20%)
        # 임계값은 catalog 한강이남 실제 분포 percentile 기반 (2026-05 검증):
        #   거래활성도 0.95 → 0점, 1.25 → 100점 (25/75 percentile)
        #   가격모멘텀 1.35 → 0점, 1.55 → 100점 (한강이남 전반 상승 시장 베이스)
        #   신축비율 0 → 100점, 0.30 → 0점 (90 percentile 초과는 공급 과잉)
        score = 0
        weight = 0
        if pd.notna(row.get("자치구_거래활성도")):
            s = max(0, min(100, (row["자치구_거래활성도"] - 0.95) / 0.30 * 100))
            score += s * 50
            weight += 50
        if pd.notna(row.get("자치구_가격모멘텀")):
            s = max(0, min(100, (row["자치구_가격모멘텀"] - 1.35) / 0.20 * 100))
            score += s * 30
            weight += 30
        if pd.notna(row.get("자치구_신축비율")):
            s = max(0, min(100, (0.30 - row["자치구_신축비율"]) / 0.30 * 100))
            score += s * 20
            weight += 20
        row["자치구_수급점수"] = round(score / weight, 1) if weight > 0 else None
        rows.append(row)

    result = pd.DataFrame(rows)
    result.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT} — {len(result)}행")

    valid = result.dropna(subset=["자치구_수급점수"])
    print(f"\n=== 자치구 수급점수 분포 ({len(valid)}개) ===")
    print(f"평균 {valid['자치구_수급점수'].mean():.1f} / 중간 {valid['자치구_수급점수'].median():.1f}")
    print(f"\n자치구별 신호 상위 5 / 하위 5:")
    summary = result.merge(catalog[["단지번호", "시구"]], on="단지번호", how="left") \
        .groupby("시구").agg(
            거래활성도=("자치구_거래활성도", "first"),
            가격모멘텀=("자치구_가격모멘텀", "first"),
            신축비율=("자치구_신축비율", "first"),
            수급점수=("자치구_수급점수", "first"),
        ).dropna()
    print(summary.sort_values("수급점수", ascending=False).head(5).to_string())
    print("---")
    print(summary.sort_values("수급점수", ascending=True).head(5).to_string())


if __name__ == "__main__":
    main()
