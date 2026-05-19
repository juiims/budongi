"""
naver_new_results.json → 평형별 매도 호가/전세가 비교표 (만원 단위)
스크린샷 "현재 시점 주목할 지역" 컬럼 구조와 동일하게 생성.
"""
import json
import csv
import re
import sys
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_korean_price(s):
    """'4억 8,000' / '10억' / '12억 5,500' → 만원(int)"""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace(" ", "")
    if not s or s in ("-",):
        return None
    m = re.match(r"(?:(\d+)억)?(?:([\d,]+))?", s)
    if not m:
        return None
    eok = int(m.group(1) or 0)
    man_str = (m.group(2) or "").replace(",", "")
    man = int(man_str) if man_str.isdigit() else 0
    total = eok * 10000 + man
    return total or None


def parse_pyeongdang(s):
    """'(2,495~3,379만원/3.3㎡)' → 평균 평단가 (만원/평)"""
    if not s or not isinstance(s, str):
        return None
    nums = [
        int(x.replace(",", ""))
        for x in re.findall(r"[\d,]+", s)
        if x.replace(",", "").isdigit()
    ]
    if not nums:
        return None
    return (nums[0] + nums[1]) // 2 if len(nums) >= 2 else nums[0]


def assign_pyeongs(pyeongs, targets, tol=4.5):
    """각 target 평수에 가장 가까운 평형을 하나씩 그리디 할당 (중복 없음, ±tol 이내)."""
    pairs = []
    for t in targets:
        for p in pyeongs:
            try:
                ep = float(p.get("전용평"))
            except (TypeError, ValueError):
                continue
            d = abs(ep - t)
            if d <= tol:
                pairs.append((d, t, p))
    pairs.sort(key=lambda x: x[0])
    used_p, assigned = set(), {}
    for d, t, p in pairs:
        if t in assigned or id(p) in used_p:
            continue
        assigned[t] = p
        used_p.add(id(p))
    return assigned


def fmt(n):
    if n is None or n == "":
        return ""
    if isinstance(n, (int, float)):
        return f"{int(n):,}"
    return str(n)


def main():
    with open("naver_new_results.json", encoding="utf-8") as f:
        data = json.load(f)

    yymm = datetime.now().strftime("%Y.%m")
    targets = [18, 21, 24, 33]

    fieldnames = ["단지명", "주소", "평당매매", "평당전세"]
    for t in targets:
        fieldnames += [f"{t}기준 매매", f"{t}기준 전세", f"{t}기준 매물수"]
    fieldnames += ["전세가율", "년월"]

    rows = []
    for apt in data:
        if "에러" in apt:
            continue
        pyeongs = apt.get("평형들") or []

        dpps = [parse_pyeongdang(p.get("매매_평단가")) for p in pyeongs]
        dpps = [x for x in dpps if x]
        lpps = [parse_pyeongdang(p.get("전세_평단가")) for p in pyeongs]
        lpps = [x for x in lpps if x]
        avg_dpp = sum(dpps) // len(dpps) if dpps else None
        avg_lpp = sum(lpps) // len(lpps) if lpps else None

        row = {
            "단지명": apt.get("단지명"),
            "주소": apt.get("주소"),
            "평당매매": fmt(avg_dpp),
            "평당전세": fmt(avg_lpp),
        }

        assigned = assign_pyeongs(pyeongs, targets)
        for t in targets:
            p = assigned.get(t)
            if not p:
                row[f"{t}기준 매매"] = ""
                row[f"{t}기준 전세"] = ""
                row[f"{t}기준 매물수"] = ""
                continue
            dmin = parse_korean_price(p.get("매매가_최저"))
            dmax = parse_korean_price(p.get("매매가_최고"))
            lmin = parse_korean_price(p.get("전세가_최저"))
            lmax = parse_korean_price(p.get("전세가_최고"))
            d_avg = (dmin + dmax) // 2 if dmin and dmax else (dmin or dmax)
            l_avg = (lmin + lmax) // 2 if lmin and lmax else (lmin or lmax)

            row[f"{t}기준 매매"] = fmt(d_avg)
            row[f"{t}기준 전세"] = fmt(l_avg)
            cnt = p.get("매매건수")
            try:
                row[f"{t}기준 매물수"] = int(cnt) if cnt not in (None, "") else ""
            except (ValueError, TypeError):
                row[f"{t}기준 매물수"] = ""

        row["전세가율"] = f"{round(avg_lpp / avg_dpp * 100)}%" if avg_dpp and avg_lpp else ""
        row["년월"] = yymm
        rows.append(row)

    out_csv = "summary_table.csv"
    try:
        fp = open(out_csv, "w", newline="", encoding="utf-8-sig")
    except PermissionError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_csv = f"summary_table_{ts}.csv"
        print(f"[경고] summary_table.csv 잠김 → {out_csv} 로 저장")
        fp = open(out_csv, "w", newline="", encoding="utf-8-sig")
    with fp:
        w = csv.DictWriter(fp, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"CSV: {out_csv} ({len(rows)}행)")
    print()

    widths = {
        k: max(len(k), max((len(str(r.get(k, ""))) for r in rows), default=0))
        for k in fieldnames
    }
    sep = " | "
    header = sep.join(k.ljust(widths[k]) for k in fieldnames)
    print(header)
    print("-" * len(header))
    for r in rows:
        print(sep.join(str(r.get(k, "")).ljust(widths[k]) for k in fieldnames))


if __name__ == "__main__":
    main()
