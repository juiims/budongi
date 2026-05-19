"""Gist JSON5 → CSV 변환 + 한강 이남 커버리지 검증."""
import ast
import csv
import re
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SRC = "data/korean_subway_raw.json5"
DST = "data/subway_stations.csv"

with open(SRC, "r", encoding="utf-8") as f:
    text = f.read()

# // 주석 제거 (라인 단위)
text = re.sub(r"//.*", "", text)
data = ast.literal_eval(text)
print(f"전체 역: {len(data)}개")

# 도시별 통계
from collections import Counter
city_counter = Counter(s.get("city") for s in data)
print("\n도시별:")
for city, count in sorted(city_counter.items(), key=lambda x: -x[1]):
    print(f"  {city}: {count}개")

# 한강 이남 서울 11구 + 경기 남부 시군 화이트리스트
SEOUL_SOUTH = {"강서구", "양천구", "영등포구", "구로구", "금천구", "동작구",
               "관악구", "서초구", "강남구", "송파구", "강동구"}
GG_SOUTH = {"광명시", "안양시", "과천시", "군포시", "의왕시", "안산시", "시흥시",
            "부천시", "성남시", "하남시", "김포시", "화성시", "수원시", "용인시",
            "평택시", "오산시", "안성시"}


def is_hangang_south(s):
    """역의 areas가 한강 이남에 포함되는지."""
    city = s.get("city", "")
    areas = s.get("areas") or []
    if city == "서울":
        for a in areas:
            if a in SEOUL_SOUTH:
                return True
        return False
    if city == "경기":
        for a in areas:
            for gg in GG_SOUTH:
                if a == gg or a.startswith(gg):
                    return True
        return False
    return False


hs_stations = [s for s in data if is_hangang_south(s)]
print(f"\n한강 이남 역: {len(hs_stations)}개")

# 시구별 분포
area_counter = Counter()
for s in hs_stations:
    for a in s.get("areas") or []:
        area_counter[a] += 1
print("\n한강 이남 시구별 역 수:")
for area, count in sorted(area_counter.items(), key=lambda x: -x[1]):
    print(f"  {area}: {count}개")

# CSV 저장 (한강 이남만)
with open(DST, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["name", "city", "areas", "lines", "lat", "lng"])
    for s in hs_stations:
        w.writerow([
            s.get("name", ""),
            s.get("city", ""),
            ",".join(s.get("areas") or []),
            ",".join(s.get("lines") or []),
            s.get("lat", ""),
            s.get("lng", ""),
        ])
print(f"\n저장: {DST} ({len(hs_stations)}개 역)")
