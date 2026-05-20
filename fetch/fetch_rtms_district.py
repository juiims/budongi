"""특정 자치구의 N개월치 RTMS 실거래 시계열 수집 → parquet 저장.

사용:
    python fetch_rtms_district.py 11680 120     # 강남구 최근 120개월(10년)
    python fetch_rtms_district.py 11680 120 강남구  # 파일명 지정
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from lib.rtms_client import fetch_trades


def month_range(end_year: int, end_month: int, count: int) -> list[str]:
    """현재 또는 지정 시점에서 거꾸로 N개월의 YYYYMM 리스트."""
    out = []
    y, m = end_year, end_month
    for _ in range(count):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12; y -= 1
    return list(reversed(out))


def fetch_district(lawd_cd: str, months: int, label: str | None = None) -> Path:
    today = date.today()
    end_y, end_m = today.year, today.month - 1  # 직전월까지 (당월은 진행중)
    if end_m == 0:
        end_y -= 1; end_m = 12
    ymds = month_range(end_y, end_m, months)
    print(f"[{lawd_cd}] {ymds[0]} ~ {ymds[-1]} ({months}개월) 수집 시작")

    out_dir = Path("data/rtms_trades")
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = label or lawd_cd
    out_path = out_dir / f"{fname}.parquet"

    all_rows: list[pd.DataFrame] = []
    t0 = time.time()
    for i, ymd in enumerate(ymds, 1):
        try:
            df = fetch_trades(lawd_cd, ymd, sleep_sec=0.12)
        except Exception as e:
            print(f"  ✗ {ymd}: {e}")
            continue
        if len(df):
            df["LAWD_CD"] = lawd_cd
            df["DEAL_YMD"] = ymd
            all_rows.append(df)
        if i % 12 == 0 or i == len(ymds):
            elapsed = time.time() - t0
            done = sum(len(d) for d in all_rows)
            print(f"  {i}/{len(ymds)} ({ymd}) — 누적 {done:,}건 / {elapsed:.1f}초")

    if not all_rows:
        print("  ⚠ 수집된 거래 없음")
        return out_path
    combined = pd.concat(all_rows, ignore_index=True)
    combined.to_parquet(out_path, index=False)
    print(f"✅ 저장 {out_path} — 총 {len(combined):,}건")
    return out_path


if __name__ == "__main__":
    lawd = sys.argv[1] if len(sys.argv) > 1 else "11680"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    label = sys.argv[3] if len(sys.argv) > 3 else None
    fetch_district(lawd, n, label)
