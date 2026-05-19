"""한강 이남 28개 자치구 RTMS 10년치 일괄 수집."""
import time
from pathlib import Path

from rtms_client import ALL_LAWD
from fetch_rtms_district import fetch_district

SKIP_IF_EXISTS = True
MONTHS = 120  # 10년

out_dir = Path("data/rtms_trades")
out_dir.mkdir(parents=True, exist_ok=True)

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
    try:
        fetch_district(lawd, MONTHS, label)
    except Exception as e:
        print(f"  ✗ 실패: {e}")
    done += 1
    elapsed = time.time() - t0
    print(f"  누적 경과 {elapsed:.0f}초 · 평균 {elapsed/done:.0f}초/자치구")

print(f"\n✅ 전체 완료 — {time.time()-t0:.0f}초")
