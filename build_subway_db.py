"""수도권 전철 좌표 DB 빌드.

출처: stripe2933/SeoulMetropolitanSubway/data/output/station_id_table.parquet
   - 741개 역 (서울+경기+인천 전 노선)
   - 컬럼: station_id, line_no, station_name, is_interchange, x(경도), y(위도)

출력: data/subway_stations.csv
  - station_name, line_no, lat, lng, is_interchange

검증: 한강 이남 + 회사 통근권 핵심 역 매칭 확인.
"""
import csv
import sys

import pyarrow.parquet as pq

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SRC = "data/station_id_table.parquet"
DST = "data/subway_stations.csv"

df = pq.read_table(SRC).to_pandas()
print(f"총 역: {len(df)}개")
print(f"노선: {sorted(df['line_no'].unique())}")

# 회사 통근권·자체일자리 거점 등 핵심 역 검증
key_stations = ["강남", "합정", "사당", "신림", "여의도", "광화문", "판교",
                "광교중앙", "광교", "정자", "서현", "야탑", "분당", "미금",
                "평촌", "인덕원", "안양", "수원", "동탄", "병점", "광명",
                "하남시청", "안산", "한대앞", "시흥", "김포공항", "마곡",
                "과천", "신도림", "잠실", "강동", "고덕", "삼성중앙"]
print("\n핵심 역 매칭 검증:")
for kw in key_stations:
    matches = df[df["station_name"].str.contains(kw, na=False)]
    if matches.empty:
        print(f"  ❌ {kw}")
    else:
        for _, row in matches.head(2).iterrows():
            print(f"  ✅ {row['station_name']} ({row['line_no']}호선)"
                  f" lat={row['y']:.4f} lng={row['x']:.4f}")

# CSV 저장
with open(DST, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["station_name", "line_no", "lat", "lng", "is_interchange"])
    for _, row in df.iterrows():
        w.writerow([
            row["station_name"],
            row["line_no"],
            f"{row['y']:.6f}",
            f"{row['x']:.6f}",
            "1" if row["is_interchange"] else "0",
        ])
print(f"\n저장: {DST} ({len(df)}개 역)")
