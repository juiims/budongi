"""
4월(스크린샷) vs 5월(우리 데이터) 비교 장표 생성.
HTML + CSV 두 가지 출력.

usage: python make_report.py [csv_path]
  csv_path 기본값: data/regional_summary_dong.csv
"""
import csv
import sys
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from compare_detailed import SCREENSHOT, COLS  # 스크린샷 4월 값 (25구)


def safe_int(v):
    if not v:
        return None
    s = str(v).rstrip("%").strip()
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def cell_color(delta_pct):
    """변화율에 따른 셀 색상."""
    if delta_pct is None:
        return "#f5f5f5"
    if abs(delta_pct) < 3:
        return "#e8f5e9"  # 거의 일치 — 연한 초록
    if abs(delta_pct) < 10:
        return "#fff9c4"  # 차이 약간 — 연한 노랑
    if delta_pct > 0:
        return "#ffcdd2"  # 상승/우리가 더 큼 — 연한 빨강
    return "#bbdefb"      # 하락/우리가 더 작음 — 연한 파랑


def render_html(april, may, output_path):
    yymm = datetime.now().strftime("%Y.%m")
    html = []
    html.append("<!DOCTYPE html>")
    html.append("<html lang='ko'><head><meta charset='utf-8'>")
    html.append(f"<title>서울 25개 구 4월/5월 비교 ({yymm})</title>")
    html.append("""<style>
body { font-family: 'Malgun Gothic', sans-serif; padding: 20px; background: #fafafa; }
h1 { color: #333; }
h2 { color: #555; margin-top: 30px; }
.legend { margin: 15px 0; font-size: 13px; }
.legend span { display: inline-block; padding: 4px 12px; margin-right: 8px; border-radius: 4px; }
table { border-collapse: collapse; margin: 15px 0; font-size: 12px; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
th, td { padding: 6px 10px; border: 1px solid #ddd; text-align: right; }
th { background: #ff7043; color: white; font-weight: 600; text-align: center; }
th.region { background: #ffa726; }
td.region { background: #fff3e0; font-weight: 600; text-align: center; }
.month { background: #ffe0b2; color: #555; text-align: center; font-size: 11px; }
.delta { font-size: 11px; color: #555; }
</style></head><body>""")

    html.append(f"<h1>서울 25개 구 — 매도 호가 + 매물수 (4월 vs 5월)</h1>")
    html.append(f"<p>기준일: 4월(2026.04 스크린샷) / 5월({yymm} Naver 부동산 동 단위 집계)</p>")
    html.append("""<div class="legend">
변화율 색상:
<span style="background:#e8f5e9;">±3% 이내</span>
<span style="background:#fff9c4;">±3~10%</span>
<span style="background:#ffcdd2;">+10% 이상 (상승)</span>
<span style="background:#bbdefb;">-10% 이상 (하락)</span>
</div>""")

    # 표 헤더
    html.append("<table>")
    html.append("<tr><th class='region' rowspan='2'>시구</th>")
    for c in COLS:
        html.append(f"<th colspan='2'>{c}</th>")
    html.append("</tr>")
    html.append("<tr>")
    for _ in COLS:
        html.append("<th class='month'>4월</th><th class='month'>5월 (Δ%)</th>")
    html.append("</tr>")

    # 데이터 행
    for name, screen in SCREENSHOT.items():
        if name not in may:
            continue
        html.append(f"<tr><td class='region'>{name}</td>")
        ours = may[name]
        for i, c in enumerate(COLS):
            s = screen[i]
            o = ours.get(c)
            html.append(f"<td>{s:,}</td>" if c != "전세가율" else f"<td>{s}%</td>")
            if o is None:
                html.append(f"<td style='background:{cell_color(None)}'>-</td>")
                continue
            if c == "전세가율":
                d = o - s
                color = cell_color(d)
                html.append(f"<td style='background:{color}'>{o}% <span class='delta'>({d:+}%p)</span></td>")
            else:
                d = (o - s) / s * 100 if s else 0
                color = cell_color(d)
                html.append(f"<td style='background:{color}'>{o:,} <span class='delta'>({d:+.1f}%)</span></td>")
        html.append("</tr>")
    html.append("</table>")

    # 평균 편차 요약
    html.append("<h2>평균 절대편차</h2><table><tr><th>지표</th><th>평균 |Δ|</th></tr>")
    for c in COLS:
        ds = []
        for name, screen in SCREENSHOT.items():
            if name not in may:
                continue
            o = may[name].get(c)
            if o is None:
                continue
            i = COLS.index(c)
            s = screen[i]
            if c == "전세가율":
                ds.append(abs(o - s))
            else:
                ds.append(abs((o - s) / s * 100) if s else 0)
        if ds:
            avg = sum(ds) / len(ds)
            unit = "%p" if c == "전세가율" else "%"
            html.append(f"<tr><td>{c}</td><td>±{avg:.1f}{unit}</td></tr>")
    html.append("</table>")

    html.append("</body></html>")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html))
    print(f"HTML 저장: {output_path}")


def render_csv(april, may, output_path):
    """비교 CSV: 시구 | 컬럼 | 4월값 | 5월값 | Δ"""
    rows = []
    for name, screen in SCREENSHOT.items():
        if name not in may:
            continue
        ours = may[name]
        for i, c in enumerate(COLS):
            s = screen[i]
            o = ours.get(c)
            if c == "전세가율":
                delta = f"{o-s:+}%p" if o is not None else ""
                o_str = f"{o}%" if o is not None else ""
                s_str = f"{s}%"
            else:
                delta = f"{(o-s)/s*100:+.1f}%" if o is not None and s else ""
                o_str = f"{o:,}" if o is not None else ""
                s_str = f"{s:,}"
            rows.append({
                "시구": name, "지표": c,
                "2026.04 (스크린샷)": s_str,
                "2026.05 (우리)": o_str,
                "변화율": delta,
            })

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["시구", "지표", "2026.04 (스크린샷)", "2026.05 (우리)", "변화율"])
        w.writeheader()
        w.writerows(rows)
    print(f"CSV 저장: {output_path}")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "data/regional_summary_dong.csv"
    print(f"5월 데이터: {target}")

    may = {}
    with open(target, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            name = r["지역"]
            may[name] = {c: safe_int(r.get(c)) for c in COLS}

    april = SCREENSHOT  # 4월 = 스크린샷
    render_html(april, may, "data/report_4월_5월_비교.html")
    render_csv(april, may, "data/report_4월_5월_비교.csv")


if __name__ == "__main__":
    main()
