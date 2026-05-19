"""regional_summary.csv 와 스크린샷(4월) 값 비교."""
import csv
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 스크린샷 2026.04 — 평당매매 / 평당전세 / 전세가율(%)만 추출 (시구 24개 정도)
SCREENSHOT = {
    "강남구": (10299, 3269, 32),
    "서초구": (10473, 3719, 36),
    "용산구": (8228, 2730, 33),
    "송파구": (7609, 2605, 34),
    "성동구": (6792, 2582, 38),
    "양천구": (5977, 2149, 36),
    "광진구": (6414, 2657, 41),
    "마포구": (6093, 2519, 41),
    "강동구": (5483, 2451, 45),
    "영등포구": (5216, 2137, 41),
    "종로구": (4506, 2351, 52),
    "동작구": (5320, 2290, 43),
    "중구": (5017, 2343, 47),
    "강서구": (3813, 1920, 50),
    "서대문구": (3992, 2072, 52),
    "동대문구": (3800, 1955, 51),
    "성북구": (3294, 1874, 57),
    "은평구": (3172, 1858, 59),
    "관악구": (3267, 1788, 55),
    "노원구": (2845, 1497, 53),
    "구로구": (2893, 1612, 56),
    "중랑구": (2557, 1603, 63),
    "금천구": (2329, 1454, 62),
    "강북구": (2458, 1564, 64),
    "도봉구": (2230, 1321, 59),
}

target = sys.argv[1] if len(sys.argv) > 1 else "regional_summary.csv"
print(f"비교 대상: {target}\n")
with open(target, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

print(f"{'지역':<7} {'평당매매':>17} {'평당전세':>15} {'전세가율':>15}")
print(f"{'':7} {'우리/스샷 (Δ%)':>17} {'우리/스샷 (Δ%)':>15} {'우리/스샷':>15}")
print("-" * 70)

diff_deal_total, diff_lease_total, diff_rate_total, n = 0, 0, 0, 0
for r in rows:
    name = r["지역"]
    if name not in SCREENSHOT:
        continue
    s_deal, s_lease, s_rate = SCREENSHOT[name]
    o_deal = int(r["평당매매"]) if r["평당매매"] else 0
    o_lease = int(r["평당전세"]) if r["평당전세"] else 0
    o_rate = int(r["전세가율"].rstrip("%")) if r["전세가율"] else 0

    d_deal = (o_deal - s_deal) / s_deal * 100 if s_deal else 0
    d_lease = (o_lease - s_lease) / s_lease * 100 if s_lease else 0
    d_rate = o_rate - s_rate

    print(f"{name:<7} {o_deal:>5,}/{s_deal:>5,} ({d_deal:+5.1f}%) "
          f"{o_lease:>5,}/{s_lease:>5,} ({d_lease:+5.1f}%) "
          f"{o_rate:>3}%/{s_rate:>2}% ({d_rate:+3}%p)")

    diff_deal_total += abs(d_deal)
    diff_lease_total += abs(d_lease)
    diff_rate_total += abs(d_rate)
    n += 1

print("-" * 70)
print(f"평균 절대편차:  매매 ±{diff_deal_total/n:.1f}%   전세 ±{diff_lease_total/n:.1f}%   "
      f"전세가율 ±{diff_rate_total/n:.1f}%p")
