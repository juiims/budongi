"""사용자 제공 서울교통공사 CSV 구조 확인."""
import csv
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PATH = "data/서울교통공사_노선별 지하철역 정보.csv"

# cp949 시도 (한국 정부 CSV 표준)
for enc in ["cp949", "euc-kr", "utf-8-sig", "utf-8"]:
    try:
        with open(PATH, "r", encoding=enc) as f:
            sample = f.read(2000)
            print(f"=== encoding: {enc} ===")
            print(sample[:500])
            print()
            break
    except UnicodeDecodeError:
        continue

with open(PATH, "r", encoding="cp949") as f:
    reader = csv.reader(f)
    rows = list(reader)
print(f"\n총 {len(rows)}행 (헤더 포함)")
print(f"컬럼: {rows[0]}")
print(f"\n첫 3행:")
for r in rows[1:4]:
    print(f"  {r}")
print(f"\n마지막 3행:")
for r in rows[-3:]:
    print(f"  {r}")
