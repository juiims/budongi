"""apt2.me 수집 결과 검증 + 기존 [필디] 데이터와 비교.

입력:
  data/apt2_middle_grade.csv
  data/apt2_high_grade.csv
  data/apt2_middle_special.csv
  data/apt2_school_trend.csv
  data/[필디]2025년2학기_전국중학교학업성취율_특목고현황.csv  (기존 학교별 평균)

출력 (콘솔):
  1) 각 CSV 행수·고유 학교수·시군구 커버리지
  2) 기존 [필디] 중학교 vs apt2_middle_grade 학교명 매칭률
  3) 동일 학교의 평균/특목고계 값 차이 샘플 10개
  4) 한강이남 45개 시군구 기준 커버리지
"""
from __future__ import annotations
import csv
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).parent
DATA = ROOT / "data"

# 한강이남 광역+시구 키 (fetch_apt_recovery에서 가져옴)
HANGANG_SOUTH = set()
SEOUL_HS = ["강서구","양천구","영등포구","구로구","금천구","동작구","관악구","서초구","강남구","송파구","강동구"]
for nm in SEOUL_HS:
    HANGANG_SOUTH.add(("서울", nm))
GG_HS = ["광명시","안양시 만안구","안양시 동안구","과천시","의왕시","군포시",
         "안산시 상록구","안산시 단원구","수원시 장안구","수원시 권선구","수원시 팔달구",
         "수원시 영통구","성남시 수정구","성남시 중원구","성남시 분당구","용인시 처인구",
         "용인시 기흥구","용인시 수지구","오산시","평택시","화성시 동탄구","화성시 만세구",
         "화성시 병점구","화성시 효행구","안성시","이천시","여주시","광주시","시흥시","김포시","하남시",
         "부천시 원미구","부천시 소사구","부천시 오정구"]
for nm in GG_HS:
    HANGANG_SOUTH.add(("경기", nm))


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def section(title: str):
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def summarize(rows: list[dict], name: str, school_key: str = "학교명"):
    if not rows:
        print(f"[{name}] 비어있음")
        return
    sido_counter = Counter((r.get("광역","") for r in rows))
    sigu_set = set((r.get("광역",""), r.get("시군구","")) for r in rows)
    school_set = set((r.get("광역",""), r.get("시군구",""), r.get(school_key,"")) for r in rows)
    mcode_set = set(r.get("mcode","") for r in rows if r.get("mcode"))
    print(f"[{name}]")
    print(f"  행수: {len(rows):,}")
    print(f"  고유 시군구: {len(sigu_set)}")
    print(f"  고유 학교: {len(school_set):,} (mcode 기준 {len(mcode_set):,})")
    print(f"  광역별 행수: ", end="")
    print(", ".join(f"{k}={v}" for k, v in sido_counter.most_common()))
    # 한강이남 커버리지
    hs_sigu = {(광역, 시구) for (광역, 시구) in sigu_set if (광역, 시구) in HANGANG_SOUTH}
    hs_schools = sum(1 for r in rows if (r.get("광역",""), r.get("시군구","")) in HANGANG_SOUTH)
    print(f"  한강이남 매칭: 시군구 {len(hs_sigu)}/45개, 학교행 {hs_schools:,}")


def main():
    section("apt2.me 수집 결과 요약")
    mg = load_csv(DATA / "apt2_middle_grade.csv")
    hg = load_csv(DATA / "apt2_high_grade.csv")
    sp = load_csv(DATA / "apt2_middle_special.csv")
    tr = load_csv(DATA / "apt2_school_trend.csv")

    summarize(mg, "중학교 성취도 (middleGrade)")
    summarize(hg, "고등학교 성취도 (highGrade)")
    summarize(sp, "특목고 진학 (middle.jsp)")
    summarize(tr, "5년 추세 (schoolTrend)")
    if tr:
        # 중/고 split
        tr_m = [r for r in tr if r.get("학교급") == "중"]
        tr_h = [r for r in tr if r.get("학교급") == "고"]
        print(f"  중학교: {len(tr_m):,} / 고등학교: {len(tr_h):,}")

    section("기존 [필디] 중학교 데이터 vs apt2_middle_grade")
    pd_path = DATA / "[필디]2025년2학기_전국중학교학업성취율_특목고현황.csv"
    pd = load_csv(pd_path)
    print(f"[필디] 행수: {len(pd):,}")
    pd_schools = set(r["학교명"] for r in pd)
    mg_schools = set(r["학교명"] for r in mg)
    overlap = pd_schools & mg_schools
    only_pd = pd_schools - mg_schools
    only_mg = mg_schools - pd_schools
    print(f"  학교명 교집합: {len(overlap):,}")
    print(f"  [필디]에만 있음: {len(only_pd):,}")
    print(f"  apt2에만 있음:   {len(only_mg):,}")

    section("동일 학교 평균값 비교 샘플 10개")
    pd_by_name = {r["학교명"]: r for r in pd}
    mg_by_name = {r["학교명"]: r for r in mg if r.get("학교명")}
    samples = sorted(overlap)[:10]
    print(f"{'학교명':<25} {'[필디]평균':>10} {'apt2평균':>10} {'[필디]특목':>10} {'apt2_A%':>8}")
    print("-" * 70)
    for name in samples:
        a = pd_by_name[name]
        b = mg_by_name[name]
        print(f"{name[:24]:<25} {a.get('평균',''):>10} {b.get('평균',''):>10} {a.get('특목고계',''):>10} {b.get('A_pct',''):>8}")

    section("학교급별 광역 커버리지 (행수)")
    print(f"{'광역':<6} {'중성취':>8} {'고성취':>8} {'특목진학':>8} {'추세중':>8} {'추세고':>8}")
    sidos = sorted({r.get("광역","") for ds in [mg,hg,sp,tr] for r in ds if r.get("광역")})
    def n(rows, sido, extra_filter=None):
        return sum(1 for r in rows if r.get("광역")==sido and (extra_filter(r) if extra_filter else True))
    for s in sidos:
        print(f"{s:<6} {n(mg,s):>8} {n(hg,s):>8} {n(sp,s):>8} "
              f"{n(tr,s,lambda r:r.get('학교급')=='중'):>8} "
              f"{n(tr,s,lambda r:r.get('학교급')=='고'):>8}")


if __name__ == "__main__":
    main()
