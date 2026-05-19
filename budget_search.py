"""
예산 → 한강 이남 매칭 매물 → 입지 점수 정렬 → 추천.

당일 최초 실행 시 catalog 자동 갱신 (mtime 오늘 자정 이전이면 재빌드).
출력 끝에 Naver 단지 페이지 URL 리스트 추가.

사용 예:
  python budget_search.py 80000              # 8억 ±5천, 상위 30개
  python budget_search.py 80000 50           # 상위 50개
  python budget_search.py 80000 --range 7000
  python budget_search.py 80000 --region 서울 --min-score 25
  python budget_search.py 80000 --no-refresh # 갱신 건너뛰기
  python budget_search.py 80000 --force-refresh
  python budget_search.py 80000 --no-urls    # URL 섹션 숨기기
"""
import argparse
import csv
import datetime
import os
import subprocess
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CATALOG_RAW = "data/candidates_hangang_south_catalog.csv"
CATALOG_SCORED = "data/catalog_scored.csv"
NAVER_COMPLEX_URL = "https://new.land.naver.com/complexes/{}"


def to_int(s):
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def to_float(s, default=0.0):
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def truncate(s, n):
    s = str(s or "")
    return s[:n]


def is_stale_today(path):
    """파일 mtime이 오늘 자정 이전이면 stale(어제 이전 데이터)."""
    if not os.path.exists(path):
        return True
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    today_start = datetime.datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return mtime < today_start


def refresh_catalog():
    """catalog raw 재빌드 + 점수화. 25-30분 소요."""
    print("=" * 60)
    print("[갱신] catalog 재빌드 시작 (약 25-30분 소요)")
    print("       취소: Ctrl+C → 다음 실행에 --no-refresh 추가하면 갱신 건너뜀")
    print("=" * 60)

    # 1) catalog raw 빌드
    env = os.environ.copy()
    env["SCREEN_GYEONGGI"] = "1"
    env["SCREEN_NO_PRICE_FILTER"] = "1"
    env.pop("SCREEN_SMOKE", None)
    print("\n[1/2] screen_candidates.py (단지 스크리닝)...")
    subprocess.run([sys.executable, "screen_candidates.py"], env=env, check=True)

    # 2) 점수 부여
    env2 = os.environ.copy()
    env2["SCORE_INPUT"] = CATALOG_RAW
    env2["SCORE_OUTPUT"] = CATALOG_SCORED
    print("\n[2/2] score_candidates.py (입지 점수화)...")
    subprocess.run([sys.executable, "score_candidates.py"], env=env2, check=True)

    print("\n[갱신 완료] 검색 진행...\n")


def maybe_refresh(args):
    """필요 시 catalog 자동 갱신."""
    if args.no_refresh:
        return
    src = args.input
    if args.force_refresh:
        print(f"[갱신] --force-refresh 옵션\n")
    elif is_stale_today(src):
        if os.path.exists(src):
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(src))
            print(f"[알림] catalog mtime={mtime:%Y-%m-%d %H:%M} — 당일 데이터 아님")
        else:
            print(f"[알림] catalog 파일 없음: {src}")
    else:
        return  # 오늘 데이터

    try:
        refresh_catalog()
    except KeyboardInterrupt:
        print("\n[갱신 취소] 기존 데이터로 검색 진행\n")
    except subprocess.CalledProcessError as e:
        print(f"\n[갱신 실패] return code {e.returncode} — 기존 데이터로 검색 진행\n")
    except Exception as e:
        print(f"\n[갱신 실패] {e} — 기존 데이터로 검색 진행\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("budget", type=int, help="예산 (만원). 예: 80000 = 8억")
    p.add_argument("top_n", type=int, nargs="?", default=30,
                   help="상위 N개 (기본 30)")
    p.add_argument("--range", dest="rng", type=int, default=5000,
                   help="예산 ±range 만원 (기본 5000)")
    p.add_argument("--min-score", type=float, default=0,
                   help="최소 입지점수 (기본 0)")
    p.add_argument("--region", choices=["서울", "경기"], help="지역 필터")
    p.add_argument("--input", default=CATALOG_SCORED,
                   help=f"입력 CSV (기본 {CATALOG_SCORED})")
    p.add_argument("--no-refresh", action="store_true",
                   help="당일 갱신 건너뛰기")
    p.add_argument("--force-refresh", action="store_true",
                   help="강제 catalog 재빌드")
    p.add_argument("--no-urls", action="store_true",
                   help="Naver URL 섹션 숨기기")
    args = p.parse_args()

    # 1. 당일 최초 실행 시 자동 갱신
    maybe_refresh(args)

    # 2. 입력 파일 결정
    src = args.input
    if not os.path.exists(src):
        fallback = "data/candidates_scored.csv"
        if os.path.exists(fallback):
            print(f"[경고] {src} 없음 → {fallback} 사용 (9억 이하 데이터만 검색됨)\n")
            src = fallback
        else:
            print(f"[에러] 입력 파일 없음: {src}")
            sys.exit(1)

    bmin = args.budget - args.rng
    bmax = args.budget + args.rng

    with open(src, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    matched = []
    for r in rows:
        min_p = to_int(r.get("최저매매가_만원"))
        max_p = to_int(r.get("최고매매가_만원"))
        if min_p is None:
            continue
        if max_p is None:
            max_p = min_p
        if max_p < bmin or min_p > bmax:
            continue
        if to_float(r.get("입지점수")) < args.min_score:
            continue
        if args.region and r.get("지역구분") != args.region:
            continue
        matched.append(r)

    matched.sort(key=lambda r: -to_float(r.get("입지점수")))

    mtime = (datetime.datetime.fromtimestamp(os.path.getmtime(src))
             if os.path.exists(src) else None)
    mtime_str = f" (데이터 갱신: {mtime:%Y-%m-%d %H:%M})" if mtime else ""
    print(f"입력: {src} ({len(rows)}개 단지){mtime_str}")
    print(f"예산: {args.budget:,}만원 ±{args.rng:,}만원 ({bmin:,}~{bmax:,})")
    if args.min_score > 0:
        print(f"최소 입지점수: {args.min_score}")
    if args.region:
        print(f"지역 필터: {args.region}")
    print(f"매칭: {len(matched)}개 → 상위 {min(args.top_n, len(matched))}개\n")

    # 추천 표
    header = (f"{'#':>3} {'점수':>5} {'지역':>2} {'시구':<10} {'동':<10} "
              f"{'단지명':<28} {'가격대(만)':<15} {'세대':>5} {'준공':>6} "
              f"{'강남':>5} {'합정':>5} {'남양':>5}")
    print(header)
    print("-" * len(header))
    top = matched[:args.top_n]
    for i, r in enumerate(top, 1):
        price = f"{r.get('최저매매가_만원','')}~{r.get('최고매매가_만원','')}"
        print(f"{i:>3} {to_float(r.get('입지점수')):>5.1f} "
              f"{r.get('지역구분',''):>2} "
              f"{truncate(r.get('시구'), 10):<10} "
              f"{truncate(r.get('동'), 10):<10} "
              f"{truncate(r.get('단지명'), 28):<28} "
              f"{truncate(price, 15):<15} "
              f"{r.get('세대수',''):>5} "
              f"{truncate(r.get('준공년월'), 6):>6} "
              f"{truncate(r.get('강남까지_km'), 5):>5} "
              f"{truncate(r.get('회사1_합정_km'), 5):>5} "
              f"{truncate(r.get('회사2_남양_km'), 5):>5}")

    # Naver 단지 페이지 URL
    if not args.no_urls and top:
        print(f"\n[Naver 단지 페이지 — 클릭/복사하여 실시간 매물 확인]")
        for i, r in enumerate(top, 1):
            cid = r.get("단지번호", "").strip()
            if cid:
                url = NAVER_COMPLEX_URL.format(cid)
                name = truncate(r.get("단지명"), 28)
                print(f"  {i:>3}. {name:<28} {url}")


if __name__ == "__main__":
    main()
