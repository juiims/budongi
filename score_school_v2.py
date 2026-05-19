"""학군 점수 v2 — apt2.me 데이터 기반 (중·고·5년추세·특목 통합).

설계 원칙:
  - [[feedback-cross-source-comparison]] 준수: apt2 컬럼만 사용. [필디] 컬럼과 섞지 않음.
  - 5개 sub-score 산출 → 가중 결합으로 최종 학군 점수 v2.

Sub-score (모두 0~100, 한강이남 catalog 분포 기준 선형 클리핑):
  1) 점수_중성취_v2  — apt2_중_평균 (mean 77.9, max 89.5) → 70→0 / 88→100
  2) 점수_고성취_v2  — apt2_고_평균 (mean 73.5, max 94.1) → 60→0 / 90→100
  3) 점수_중추세_v2  — apt2_중_2025 (mean 34.4, max 56.8) + 연속상승비율 보너스
       2025값 50% + 연속상승비율 50% (각 0~100 정규화 후 평균)
  4) 점수_고추세_v2  — apt2_고_2025 (mean 22.8, max 63.2) 동일 방식
  5) 점수_특목_v2    — apt2_특목비율 (mean 1.96%, max 14.2%) → 0→0 / 10→100

최종 가중 (변경 가능):
  점수_학군_v2 = 0.30·중성취 + 0.20·고성취 + 0.15·중추세 + 0.10·고추세 + 0.25·특목

근거:
  - 중학교가 부동산 시장 영향 더 큼 (중학교 기준 이사 수요) → 중 0.45 / 고 0.30
  - 추세는 미래 지향, 안정성보다 낮은 가중 (성취 0.50, 추세 0.25)
  - 특목은 상위층 차별화 지표 → 0.25

입력:  data/catalog_apt2_school.csv  (enrich_catalog_apt2.py 산출)
출력:  data/catalog_apt2_school_scored.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "data"

# 분포 기반 선형 클리핑 컷오프 (한강이남 catalog 분포에서 결정)
MID_AVG_FLOOR, MID_AVG_CEIL = 70.0, 88.0
HI_AVG_FLOOR,  HI_AVG_CEIL  = 60.0, 90.0
MID_2025_FLOOR, MID_2025_CEIL = 20.0, 55.0
HI_2025_FLOOR,  HI_2025_CEIL  = 10.0, 50.0
SPEC_FLOOR, SPEC_CEIL = 0.0, 10.0   # 특목 비율 %

# 최종 가중치 — 사용자 튜닝 결과 (고등학교 강조 2:3 + 추세 강화 3:2 + 특목 유지)
#   중:고 = 40:60,  성취:추세 = 60:40,  특목 = 0.25
#   비특목 0.75 → 성취 0.45 / 추세 0.30
#     성취: 중 0.18 / 고 0.27   ·  추세: 중 0.12 / 고 0.18
W_MID_ACH   = 0.18
W_HI_ACH    = 0.27
W_MID_TREND = 0.12
W_HI_TREND  = 0.18
W_SPEC      = 0.25


def linear(s: pd.Series, floor: float, ceil: float) -> pd.Series:
    return ((s - floor) / (ceil - floor) * 100.0).clip(lower=0, upper=100)


def compute(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["점수_중성취_v2"] = linear(out["apt2_중_평균"], MID_AVG_FLOOR, MID_AVG_CEIL)
    out["점수_고성취_v2"] = linear(out["apt2_고_평균"], HI_AVG_FLOOR, HI_AVG_CEIL)

    # 추세: 2025 A% 절대값 + 연속상승 비율 (각 50%)
    중_2025_s = linear(out["apt2_중_2025"], MID_2025_FLOOR, MID_2025_CEIL)
    중_up_s   = (out["apt2_중_연속상승비율"].fillna(0) * 100).clip(0, 100)
    out["점수_중추세_v2"] = 0.5 * 중_2025_s + 0.5 * 중_up_s

    고_2025_s = linear(out["apt2_고_2025"], HI_2025_FLOOR, HI_2025_CEIL)
    고_up_s   = (out["apt2_고_연속상승비율"].fillna(0) * 100).clip(0, 100)
    out["점수_고추세_v2"] = 0.5 * 고_2025_s + 0.5 * 고_up_s

    out["점수_특목_v2"] = linear(out["apt2_특목비율"], SPEC_FLOOR, SPEC_CEIL)

    out["점수_학군_v2"] = (
        W_MID_ACH   * out["점수_중성취_v2"]
        + W_HI_ACH    * out["점수_고성취_v2"]
        + W_MID_TREND * out["점수_중추세_v2"]
        + W_HI_TREND  * out["점수_고추세_v2"]
        + W_SPEC      * out["점수_특목_v2"]
    )
    return out


def report(df: pd.DataFrame):
    print("\n── sub-score 분포 ──")
    for col in ["점수_중성취_v2","점수_고성취_v2","점수_중추세_v2","점수_고추세_v2","점수_특목_v2","점수_학군_v2"]:
        s = df[col]
        print(f"  {col}: min {s.min():.1f} / p25 {s.quantile(0.25):.1f} / "
              f"p50 {s.median():.1f} / p75 {s.quantile(0.75):.1f} / max {s.max():.1f}")

    print("\n── 학군 점수 v2 TOP 15 단지 ──")
    top = df.nlargest(15, "점수_학군_v2")[
        ["지역구분","시구","동","단지명","점수_중성취_v2","점수_고성취_v2",
         "점수_중추세_v2","점수_고추세_v2","점수_특목_v2","점수_학군_v2"]
    ]
    print(top.to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    print("\n── 시구별 평균 학군 점수 v2 TOP 15 ──")
    by = (df.groupby(["지역구분","시구"])["점수_학군_v2"]
            .agg(["mean","count"])
            .sort_values("mean", ascending=False)
            .head(15))
    by["mean"] = by["mean"].round(1)
    print(by.to_string())

    print("\n── 기존 점수_학군 (v1, [필디] 기반) vs 점수_학군_v2 상관 ──")
    if "점수_학군" in df.columns:
        c = df[["점수_학군","점수_학군_v2"]].corr().iloc[0,1]
        print(f"  Pearson 상관: {c:.3f}  (1.0=완전일치, 0.0=무관)")


def main():
    in_path = DATA / "catalog_apt2_school.csv"
    out_path = DATA / "catalog_apt2_school_scored.csv"

    df = pd.read_csv(in_path)
    print(f"입력: {in_path.name} ({len(df):,}행)")
    print(f"가중치: 중성취 {W_MID_ACH} + 고성취 {W_HI_ACH} + 중추세 {W_MID_TREND} + 고추세 {W_HI_TREND} + 특목 {W_SPEC}")

    scored = compute(df)
    scored.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"산출: {out_path.name}")

    report(scored)


if __name__ == "__main__":
    main()
