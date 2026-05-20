"""catalog_with_school_scored.csv에서 학군 관련 컬럼만 분리한 파일 생성.

입력: data/catalog_with_school_scored.csv
출력: data/catalog_school_only.csv

목적:
  - 학군 데이터를 단지 단위 독립 파일로 제공
  - streamlit/budget_search 가 필요할 때만 join 해서 쓰도록 분리
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

SRC = Path("data/catalog_with_school_scored.csv")
OUT = Path("data/catalog_school_only.csv")

KEY_COLS = ["단지번호", "단지명", "시구", "자치구", "동", "위도", "경도"]

SCHOOL_COLS = [
    # 동 단위 (가장 정확)
    "학교수", "성취_평균_avg", "성취_평균_max",
    "특목고진학_합", "특목고진학_avg", "사립여부_비율",
    # 시구 fallback
    "시구_학교수", "시구_성취_평균_avg", "시구_성취_평균_max",
    "시구_특목고진학_avg", "시구_특목고진학_max",
    # 시 fallback
    "시_학교수", "시_성취_평균_avg", "시_성취_평균_max",
    "시_특목고진학_avg", "시_특목고진학_max",
    # 최종 선택값 (매칭 단계 + 사용된 값)
    "학군_매칭", "학군_성취율", "학군_특목고",
    # 0-100 점수
    "점수_성취율", "점수_특목고", "점수_학군",
]


def main():
    df = pd.read_csv(SRC, encoding="utf-8-sig")
    missing_key = [c for c in KEY_COLS if c not in df.columns]
    missing_school = [c for c in SCHOOL_COLS if c not in df.columns]
    if missing_key:
        raise SystemExit(f"키 컬럼 누락: {missing_key}")
    if missing_school:
        print(f"  ! 학군 컬럼 일부 누락 (스킵): {missing_school}")

    cols = KEY_COLS + [c for c in SCHOOL_COLS if c in df.columns]
    out = df[cols].copy()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")

    print(f"단지 수: {len(out)}")
    print(f"컬럼: {len(cols)}개 (키 {len(KEY_COLS)} + 학군 {len(cols)-len(KEY_COLS)})")
    print(f"→ {OUT}")

    print("\n학군_매칭 분포:")
    print(out["학군_매칭"].value_counts(dropna=False).to_string())

    print("\n점수_학군 분포:")
    print(out["점수_학군"].describe().to_string())


if __name__ == "__main__":
    main()
