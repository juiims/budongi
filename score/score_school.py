"""학군 점수화 모듈 — 성취율·특목고 진학을 0-100 점수로 변환.

설계:
  - 학군_성취율 (한강이남 분포: min 60.6 / 25% 70.9 / mean 74.0 / 75% 76.8 / max 85.7)
  - 학군_특목고 (인근 중학교 평균 특목고 진학 수)

기본 변환 (선형 클리핑):
  성취율: 60점 → 0, 85점 → 100  (한강이남 max 85.7 기준)
  특목고: 0명 → 0, 20명 → 100  (한강이남 99% 분위수 ≈ 20)

결합: weight_ach * 성취점수 + weight_spec * 특목점수 (기본 0.7 / 0.3)

사용:
    from score_school import compute_school_score
    df = compute_school_score(df)  # 컬럼 추가: 점수_성취율, 점수_특목고, 점수_학군
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# 기본 컷오프 — 한강이남 실제 분포에 맞춰 설정
DEFAULT_ACH_FLOOR = 60.0
DEFAULT_ACH_CEILING = 85.0
DEFAULT_SPEC_FLOOR = 0.0
DEFAULT_SPEC_CEILING = 20.0
DEFAULT_W_ACH = 0.7
DEFAULT_W_SPEC = 0.3


def _linear_score(s: pd.Series, floor: float, ceiling: float) -> pd.Series:
    """floor 이하 → 0, ceiling 이상 → 100, 그 사이는 선형."""
    if ceiling <= floor:
        raise ValueError(f"ceiling({ceiling}) > floor({floor}) 이어야 함")
    score = (s - floor) / (ceiling - floor) * 100.0
    return score.clip(lower=0, upper=100)


def compute_school_score(
    df: pd.DataFrame,
    *,
    ach_col: str = "학군_성취율",
    spec_col: str = "학군_특목고",
    ach_floor: float = DEFAULT_ACH_FLOOR,
    ach_ceiling: float = DEFAULT_ACH_CEILING,
    spec_floor: float = DEFAULT_SPEC_FLOOR,
    spec_ceiling: float = DEFAULT_SPEC_CEILING,
    weight_ach: float = DEFAULT_W_ACH,
    weight_spec: float = DEFAULT_W_SPEC,
) -> pd.DataFrame:
    """학군 데이터 → 0-100 점수 컬럼 추가.

    Returns
    -------
    DataFrame
        원본 + 점수_성취율 / 점수_특목고 / 점수_학군 컬럼 추가.
    """
    if abs((weight_ach + weight_spec) - 1.0) > 1e-6:
        # 합이 1이 아니면 정규화
        total = weight_ach + weight_spec
        weight_ach /= total
        weight_spec /= total

    out = df.copy()
    out["점수_성취율"] = _linear_score(out[ach_col], ach_floor, ach_ceiling)
    out["점수_특목고"] = _linear_score(out[spec_col], spec_floor, spec_ceiling)
    out["점수_학군"] = (
        weight_ach * out["점수_성취율"] + weight_spec * out["점수_특목고"]
    )
    # 학군 데이터가 NaN인 행은 점수도 NaN으로
    nan_mask = out[ach_col].isna() & out[spec_col].isna()
    out.loc[nan_mask, ["점수_성취율", "점수_특목고", "점수_학군"]] = np.nan
    return out


def main():
    """검증용 CLI — data/catalog_with_school.csv에 점수 추가 후 산출."""
    in_path = Path("data/catalog_with_school.csv")
    out_path = Path("data/catalog_with_school_scored.csv")

    df = pd.read_csv(in_path)
    print(f"입력: {in_path} ({len(df):,}행)")
    print()
    print(f"파라미터:")
    print(f"  성취율 변환: {DEFAULT_ACH_FLOOR}점 → 0 ~ {DEFAULT_ACH_CEILING}점 → 100")
    print(f"  특목고 변환: {DEFAULT_SPEC_FLOOR}명 → 0 ~ {DEFAULT_SPEC_CEILING}명 → 100")
    print(f"  가중: 성취 {DEFAULT_W_ACH} + 특목 {DEFAULT_W_SPEC}")
    print()

    scored = compute_school_score(df)
    scored.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"산출: {out_path}")
    print()

    print("점수 분포:")
    for col in ["점수_성취율", "점수_특목고", "점수_학군"]:
        s = scored[col]
        print(f"  {col}: min {s.min():.1f} / 25% {s.quantile(0.25):.1f} / "
              f"median {s.median():.1f} / 75% {s.quantile(0.75):.1f} / "
              f"max {s.max():.1f}")
    print()

    # 점수 학군 상위 10개 단지 (검증용)
    print("학군 점수 TOP 10 단지:")
    top = scored.nlargest(10, "점수_학군")[
        ["지역구분", "시구", "동", "단지명",
         "학군_성취율", "학군_특목고", "점수_학군", "학군_매칭"]
    ]
    print(top.to_string(index=False))
    print()

    # 시구별 평균 학군 점수
    print("시구별 평균 학군 점수 TOP 15:")
    by_sigu = (
        scored.groupby(["지역구분", "시구"])["점수_학군"]
        .agg(["mean", "count"])
        .sort_values("mean", ascending=False)
        .head(15)
    )
    print(by_sigu.to_string())


if __name__ == "__main__":
    main()
