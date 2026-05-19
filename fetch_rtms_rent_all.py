"""한강 이남 42자치구 전월세 10년치 일괄 수집."""
import time
from datetime import date
from pathlib import Path

import pandas as pd

from rtms_client import ALL_LAWD, fetch_rents

SKIP_IF_EXISTS = True
MONTHS = 120  # 10년

out_dir = Path("data/rtms_rents")
out_dir.mkdir(parents=True, exist_ok=True)


def month_range(end_year, end_month, count):
    out = []
    y, m = end_year, end_month
    for _ in range(count):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12; y -= 1
    return list(reversed(out))


today = date.today()
end_y, end_m = today.year, today.month - 1
if end_m == 0:
    end_y -= 1; end_m = 12
ymds = month_range(end_y, end_m, MONTHS)
print(f"수집 범위: {ymds[0]} ~ {ymds[-1]} ({MONTHS}개월)")

t0 = time.time()
done = 0
total = len(ALL_LAWD)
for label, lawd in ALL_LAWD.items():
    out_path = out_dir / f"{label}.parquet"
    if SKIP_IF_EXISTS and out_path.exists():
        print(f"[{done+1}/{total}] {label} ({lawd}) — 이미 수집됨, 스킵")
        done += 1
        continue
    print(f"\n[{done+1}/{total}] {label} ({lawd}) 수집 시작")
    all_rows = []
    t_start = time.time()
    for i, ymd in enumerate(ymds, 1):
        try:
            df = fetch_rents(lawd, ymd, sleep_sec=0.12)
        except Exception as e:
            print(f"  ✗ {ymd}: {e}")
            continue
        if len(df):
            df["LAWD_CD"] = lawd
            df["DEAL_YMD"] = ymd
            all_rows.append(df)
        if i % 24 == 0 or i == len(ymds):
            done_cnt = sum(len(d) for d in all_rows)
            print(f"  {i}/{len(ymds)} — 누적 {done_cnt:,}건 / {time.time()-t_start:.0f}초")
    if all_rows:
        combined = pd.concat(all_rows, ignore_index=True)
        combined.to_parquet(out_path, index=False)
        print(f"  ✅ {len(combined):,}건 저장")
    else:
        print(f"  ⚠ 거래 없음")
    done += 1
    elapsed = time.time() - t0
    print(f"  누적 경과 {elapsed:.0f}초 · 평균 {elapsed/done:.0f}초/자치구")

print(f"\n✅ 전체 완료 — {time.time()-t0:.0f}초")
