"""
입지 점수화 — 연속점수(0-100) 가중합 방식.

방식 변경 사유: 통과개수 등급(B)은 컷오프 빡빡함 논쟁이 본질이 아님.
사용자 워크플로우(예산 → 매물 → 입지 정렬)는 절대 등급보다 상대 순위가 중요.
따라서 거리·세대수·연식 기반 연속점수(0-100)로 줄세우기 가능하게 변경.

각 요소 점수: 거리 기반 선형 (0km=100점, 컷오프거리=0점)
요소 합산: 서울/경기 가중치 다름. 측정 가능한 요소만 사용해 100점 만점으로 재정규화.

5요소 (사용자 결정: 너나위 4요소 + 개인직장):
  - 직장 / 서울접근성
  - 교통 (측정불가, 1차 제외)
  - 학군 (측정불가, 1차 제외)
  - 환경 (세대수·신축)
  - 개인직장 (합정/남양)

서울 1차 측정 가능: 직장·환경·개인직장 (3개)
경기 1차 측정 가능: 서울접근성·자체일자리·환경·개인직장 (4개)
"""
import csv
import math
import os
import sys
from collections import Counter

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CURRENT_YEAR = 2026

# ============================================================
# 거리 컷오프 (점수 0이 되는 거리, km)
# ============================================================
CUT_SEOUL_GANGNAM = 15.0       # 서울 직장: 강남 0km=100, 15km=0
CUT_GYEONGGI_GANGNAM = 30.0    # 경기 서울접근성: 0km=100, 30km=0
CUT_JOB_HUB = 10.0             # 자체일자리: 0km=100, 10km=0
CUT_HAPJEONG = 12.0            # 개인직장 합정: 0km=100, 12km=0
# 남양: 셔틀 이용 → 교통(지하철 접근성) 점수로 대체.
# 거리 컬럼만 참고용 유지.
CUT_SUBWAY = 1.5               # 교통: 가장 가까운 지하철역 0km=100, 1.5km=0

# ============================================================
# 환경 점수 파라미터
# ============================================================
HH_MIN = 300       # 세대수: 300이하=0점, 1500이상=만점 (선형)
HH_MAX = 1500
AGE_MIN = 5        # 연식: 5년이하=만점, 30년이상=0점 (선형)
AGE_MAX = 30

# ============================================================
# 가중치 — 측정 요소만 합쳐서 100점 만점이 되도록 재정규화
# ============================================================
# 서울: 직장·교통·환경·개인직장 (학군은 데이터 부재로 미측정)
SEOUL_WEIGHTS = {"직장": 40, "교통": 25, "환경": 15, "개인직장": 20}  # 합 100
# 경기: 서울접근성·자체일자리·교통·환경·개인직장
GYEONGGI_WEIGHTS = {"서울접근성": 25, "자체일자리": 20, "교통": 15, "환경": 15, "개인직장": 25}  # 합 100

# ============================================================
# 경기 자체일자리 거점
# ============================================================
JOB_HUBS = {
    "판교": (37.3947, 127.1112),
    "분당": (37.3812, 127.1187),   # 서현역
    "과천": (37.4292, 126.9879),   # 정부과천청사
    "광교": (37.2861, 127.0566),   # 광교중앙역
    "마곡": (37.5602, 126.8255),   # 마곡역
}

SEOUL_DISTRICTS = {
    "강서구", "양천구", "영등포구", "구로구", "금천구", "동작구",
    "관악구", "서초구", "강남구", "송파구", "강동구",
}

# 지하철 역 좌표 로딩 (1회) — score_row()에서 가장 가까운 역 거리 계산용
_SUBWAY_COORDS = None


def load_subway_coords(path="data/subway_stations.csv"):
    """수도권 전철 좌표 로딩. (lat, lng) 튜플 리스트 반환."""
    import os
    if not os.path.exists(path):
        return []
    coords = []
    with open(path, "r", encoding="utf-8-sig") as f:
        import csv as _csv
        for row in _csv.DictReader(f):
            try:
                lat = float(row["lat"])
                lng = float(row["lng"])
                coords.append((lat, lng))
            except (KeyError, ValueError, TypeError):
                continue
    return coords


def nearest_subway_km(lat, lon):
    """단지 좌표에서 가장 가까운 지하철역까지 직선거리(km)."""
    global _SUBWAY_COORDS
    if _SUBWAY_COORDS is None:
        _SUBWAY_COORDS = load_subway_coords()
    if not _SUBWAY_COORDS or not lat or not lon:
        return None
    return min(haversine_km(lat, lon, s_lat, s_lng)
               for s_lat, s_lng in _SUBWAY_COORDS)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def linear_score(value, cutoff):
    """0 ~ cutoff 선형 감소. value=0이면 100, value≥cutoff면 0."""
    if value is None:
        return 0
    if value <= 0:
        return 100
    if value >= cutoff:
        return 0
    return round(100 * (1 - value / cutoff), 1)


def range_score(value, lo, hi, reverse=False):
    """lo~hi 선형. reverse=True면 lo=만점·hi=0."""
    if value is None:
        return 0
    if reverse:
        if value <= lo:
            return 100
        if value >= hi:
            return 0
        return round(100 * (1 - (value - lo) / (hi - lo)), 1)
    else:
        if value <= lo:
            return 0
        if value >= hi:
            return 100
        return round(100 * (value - lo) / (hi - lo), 1)


def parse_year(s):
    if not s:
        return None
    s = str(s).strip()
    if not s or not s[0].isdigit():
        return None
    try:
        return int(s[:4])
    except ValueError:
        return None


def min_job_hub_km(lat, lon):
    if not lat or not lon:
        return None
    return min(haversine_km(lat, lon, h_lat, h_lon)
               for h_lat, h_lon in JOB_HUBS.values())


def score_row(row):
    gn_km = float(row.get("강남까지_km") or 0) or None
    if gn_km == 0:
        gn_km = None
    hj_km = float(row.get("회사1_합정_km") or 0) or None
    ny_km = float(row.get("회사2_남양_km") or 0) or None
    if not row.get("강남까지_km"):
        gn_km = None
    if not row.get("회사1_합정_km"):
        hj_km = None
    if not row.get("회사2_남양_km"):
        ny_km = None

    household = int(row.get("세대수") or 0)
    year = parse_year(row.get("준공년월"))
    age = (CURRENT_YEAR - year) if year else None
    try:
        lat = float(row.get("위도") or 0)
        lon = float(row.get("경도") or 0)
        if lat == 0 or lon == 0:
            lat = lon = None
    except (ValueError, TypeError):
        lat = lon = None

    seoul = row.get("시구", "") in SEOUL_DISTRICTS
    region = "서울" if seoul else "경기"

    # 요소별 점수
    if seoul:
        s_job = linear_score(gn_km, CUT_SEOUL_GANGNAM)
        s_seoul_acc = None
        s_jache = None
        hub_km = None
    else:
        s_job = None
        s_seoul_acc = linear_score(gn_km, CUT_GYEONGGI_GANGNAM)
        hub_km = min_job_hub_km(lat, lon) if lat and lon else None
        s_jache = linear_score(hub_km, CUT_JOB_HUB)

    # 환경: 세대수 50% + 신축 50%
    hh_score = range_score(household, HH_MIN, HH_MAX)
    age_score = range_score(age, AGE_MIN, AGE_MAX, reverse=True) if age is not None else 0
    s_env = round(hh_score * 0.5 + age_score * 0.5, 1)

    # 개인직장: 합정역 직선거리만 (남양은 셔틀 → 교통 점수에 흡수)
    s_personal = linear_score(hj_km, CUT_HAPJEONG) if hj_km else 0

    # 교통: 가장 가까운 지하철역 직선거리 (수도권 741개역 기준)
    subway_km = nearest_subway_km(lat, lon) if lat and lon else None
    s_transit = linear_score(subway_km, CUT_SUBWAY) if subway_km is not None else 0

    # 가중합
    if seoul:
        weights = SEOUL_WEIGHTS
        factors = {"직장": s_job, "교통": s_transit, "환경": s_env, "개인직장": s_personal}
    else:
        weights = GYEONGGI_WEIGHTS
        factors = {"서울접근성": s_seoul_acc, "자체일자리": s_jache,
                   "교통": s_transit, "환경": s_env, "개인직장": s_personal}

    total = sum(factors[k] * weights[k] for k in weights) / sum(weights.values())
    total = round(total, 1)

    out = dict(row)
    out["지역구분"] = region
    out["자체일자리_km"] = round(hub_km, 2) if hub_km else ""
    out["가까운지하철_km"] = round(subway_km, 2) if subway_km is not None else ""
    out["점수_직장"] = s_job if s_job is not None else ""
    out["점수_서울접근성"] = s_seoul_acc if s_seoul_acc is not None else ""
    out["점수_자체일자리"] = s_jache if s_jache is not None else ""
    out["점수_교통"] = s_transit
    out["점수_환경"] = s_env
    out["점수_개인직장"] = s_personal
    out["입지점수"] = total
    return out


def main():
    src = os.environ.get("SCORE_INPUT", "data/candidates_hangang_south.csv")
    dst = os.environ.get("SCORE_OUTPUT", "data/candidates_scored.csv")

    if not os.path.exists(src):
        print(f"입력 파일 없음: {src}")
        return

    with open(src, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"입력: {src} ({len(rows)}행)")

    scored = [score_row(r) for r in rows]

    # 단지번호(markerId) 기준 dedup — 자치구 경계 걸친 단지 중복 제거
    seen_ids = {}
    for r in scored:
        mid = r.get("단지번호")
        if not mid:
            continue
        if mid not in seen_ids:
            seen_ids[mid] = r
    deduped_before = len(scored)
    scored = list(seen_ids.values())
    print(f"dedup: {deduped_before} → {len(scored)} ({deduped_before - len(scored)}개 중복 제거)")

    scored.sort(key=lambda r: -r["입지점수"])

    keys, seen = [], set()
    for r in scored:
        for k in r.keys():
            if k not in seen:
                keys.append(k); seen.add(k)
    with open(dst, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(scored)
    print(f"출력: {dst}")

    # 분포 (10점 단위)
    print("\n점수 분포 (10점 단위):")
    bins = Counter()
    for r in scored:
        b = int(r["입지점수"] // 10) * 10
        bins[b] += 1
    for b in sorted(bins.keys(), reverse=True):
        bar = "#" * (bins[b] // 5)
        print(f"  {b:3d}-{b+9:3d}: {bins[b]:4d} {bar}")

    print("\n지역별 평균/최대:")
    seoul_scores = [r["입지점수"] for r in scored if r["지역구분"] == "서울"]
    gg_scores = [r["입지점수"] for r in scored if r["지역구분"] == "경기"]
    if seoul_scores:
        print(f"  서울({len(seoul_scores)}개): 평균={sum(seoul_scores)/len(seoul_scores):.1f} 최대={max(seoul_scores)}")
    if gg_scores:
        print(f"  경기({len(gg_scores)}개): 평균={sum(gg_scores)/len(gg_scores):.1f} 최대={max(gg_scores)}")

    print("\n점수 상위 15개:")
    for r in scored[:15]:
        print(f"  {r['입지점수']:5.1f} | {r['지역구분']} {r['시구']:6s} {r['동']:10s} {r['단지명']:30s} "
              f"강남{r['강남까지_km']}km 합정{r['회사1_합정_km']}km 남양{r['회사2_남양_km']}km "
              f"세대{r['세대수']} {r['준공년월']}")


if __name__ == "__main__":
    main()
