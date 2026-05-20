"""apt2.me schoolTrend.jsp 광역시도 페이지에서 하위 시군구 area code 추출."""
from __future__ import annotations
import re
from pathlib import Path
import json

ROOT = Path(__file__).parent
SIDO_CODES = ["11","26","27","28","29","30","31","36","41","42","43","44","45","46","47","48","50"]
SIDO_NAME = {
    "11":"서울","26":"부산","27":"대구","28":"인천","29":"광주","30":"대전","31":"울산",
    "36":"세종","41":"경기","42":"강원","43":"충북","44":"충남","45":"전북","46":"전남",
    "47":"경북","48":"경남","50":"제주",
}

# href 패턴: ./schoolTrend.jsp?area=11680&Cmb_gubun=03">강남구</a>
PAT = re.compile(r'schoolTrend\.jsp\?area=(\d{4,5})(?:&Cmb_gubun=\d+)?"[^>]*>([^<]+)</a>')

result: dict[str, dict[str, str]] = {}
for sido in SIDO_CODES:
    html = (ROOT / f"_apt2_st_{sido}.html").read_text(encoding="utf-8", errors="replace")
    found = PAT.findall(html)
    sub: dict[str, str] = {}
    for code, name in found:
        if not code.startswith(sido):  # 다른 시도 링크는 제외
            continue
        name = name.strip()
        if not name or name in ("전체", sido):
            continue
        if code == sido:  # 시도 자체 링크 제외
            continue
        if name in sub:
            continue
        sub[name] = code
    result[sido] = sub
    print(f"[{sido}/{SIDO_NAME[sido]}] {len(sub)}개")

out = ROOT / "data" / "apt2_area_codes.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
total = sum(len(v) for v in result.values())
print(f"\n총 {total}개 시군구. 저장: {out}")
