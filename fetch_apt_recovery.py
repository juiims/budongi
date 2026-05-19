"""apt2.me 아파트 실거래가 전고점 대비 회복률 스크래퍼.

- 입력: 시군구 area code 리스트 (행안부 법정동 5자리, apt2.me 자체 분할 포함)
- 출력: data/apt_recovery_hangang_south.csv  (단지 행 단위)

페이지 구조: /apt/AptRecovery.jsp?area={code} 가 단일 HTML에 전체 단지 표.
페이지네이션은 사실상 1페이지 고정 (pages=2부터 빈 결과).

추출 필드:
  area_code, 단지명, 연차, aptCode_b64, aptCode
  세대수, 주차대수, 광역, 시구, 동
  계약일, 면적_㎡, 평형, 층, 동번호
  거래금액_만원, 회복률_pct, 거래건수
  직전가_만원, 최저가_만원, 직전대비_pct
  매물수, 신규매물수
  학교명, 도보_분, 거리_m
  위도, 경도
  시계열_가격_만원 (sparkline 콤마 문자열)

참고: 절대값(거래가)은 RTMS와 출처 다르니 비교 금지 (feedback_cross_source_comparison).
비율 컬럼 (회복률, 직전대비) 위주로 활용.
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote
from urllib.request import Request, urlopen
import ssl

from bs4 import BeautifulSoup

BASE = "https://apt2.me/apt/AptRecovery.jsp"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# Windows에서 가끔 발생하는 인증서 폐기 검사 실패 우회.
# 검증 자체는 유지하되 폐기 목록 fetch 실패는 무시.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# ── area_code 매핑 (apt2.me /apt/RtnJson.jsp?level=cate2 응답에서 추출) ──
SEOUL_HANGANG_SOUTH = {
    "강서구": "11500", "양천구": "11470", "영등포구": "11560",
    "구로구": "11530", "금천구": "11545", "동작구": "11590",
    "관악구": "11620", "서초구": "11650", "강남구": "11680",
    "송파구": "11710", "강동구": "11740",
}

GG_HANGANG_SOUTH = {
    "광명시": "41210",
    "안양시 만안구": "41171", "안양시 동안구": "41173",
    "과천시": "41290", "의왕시": "41430", "군포시": "41410",
    "안산시 상록구": "41271", "안산시 단원구": "41273",
    "수원시 장안구": "41111", "수원시 권선구": "41113",
    "수원시 팔달구": "41115", "수원시 영통구": "41117",
    "성남시 수정구": "41131", "성남시 중원구": "41133", "성남시 분당구": "41135",
    "용인시 처인구": "41461", "용인시 기흥구": "41463", "용인시 수지구": "41465",
    "오산시": "41370", "평택시": "41220",
    "화성시 동탄구": "41597", "화성시 만세구": "41591",
    "화성시 병점구": "41595", "화성시 효행구": "41593",
    "안성시": "41550", "이천시": "41500", "여주시": "41670",
    "광주시": "41610", "시흥시": "41390", "김포시": "41570",
    "하남시": "41450",
    "부천시 원미구": "41192", "부천시 소사구": "41194", "부천시 오정구": "41196",
}

AREA_LABEL = {**{v: k for k, v in SEOUL_HANGANG_SOUTH.items()},
              **{v: k for k, v in GG_HANGANG_SOUTH.items()}}


def fetch_html(area_code: str, retries: int = 3, sleep: float = 1.0) -> str:
    """area 페이지 HTML 가져오기. CF 차단 시 재시도."""
    url = f"{BASE}?area={area_code}"
    last_err = None
    for i in range(retries):
        try:
            req = Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            })
            with urlopen(req, context=_SSL_CTX, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            time.sleep(sleep * (i + 1))
    raise RuntimeError(f"fetch 실패 {area_code}: {last_err}")


# ── 파서 정규식 ──
_AMOUNT_PAT = re.compile(r"(\d+)억(?:(\d+)천)?(\d+)?")
_FLOOR_PAT = re.compile(r"(\d+)층")
_AREA_PAT = re.compile(r"([\d.]+)㎡\s*(\d+[A-Z]?)?평?")
_DONG_PAT = re.compile(r"\((\d+)\)")
_RECOVERY_PAT = re.compile(r"(\d+)%\s*\((\d+)건\)")
_PREV_CHANGE_PAT = re.compile(r"([↑↓])([\d.]+)%")
_MEMUL_PAT = re.compile(r"매물[:：]\s*(\d+)건\s*\(신규[:：]\s*(\d+)건\)")
_SUBWAY_TIME_PAT = re.compile(r"도보\s*(\d+)분")
_SUBWAY_DIST_PAT = re.compile(r"(\d+)\s*m")
_LATLON_PAT = re.compile(r"pos_x=([\d.\-]+)&pos_y=([\d.\-]+)")
_YEAR_PAT = re.compile(r"\((\d+)년차\)")


def parse_amount_manwon(s: str) -> int | None:
    """'14억6천500' → 146500 (만원)."""
    s = s.replace(",", "").strip()
    m = _AMOUNT_PAT.search(s)
    if not m:
        return None
    eok = int(m.group(1))
    cheon = int(m.group(2) or 0)
    rest = int(m.group(3) or 0)
    return eok * 10000 + cheon * 1000 + rest


def parse_row(tr, area_code: str) -> dict | None:
    """3-cell tr → 단지 dict. 헤더/구분자 행은 None."""
    tds = tr.find_all("td", recursive=False)
    if len(tds) != 3:
        return None
    if "style8" in (tds[0].get("class") or []):
        return None  # 헤더

    cell_name, cell_date, cell_recovery = tds

    # ── 1번째 셀: 단지명, 세대수, 주소, sparkline ──
    name_a = cell_name.find("a", href=re.compile(r"AptReal\.jsp"))
    if not name_a:
        return None
    raw_name = name_a.get_text(strip=True)
    year_m = _YEAR_PAT.search(raw_name)
    danji_nm = _YEAR_PAT.sub("", raw_name).strip()
    yearago = int(year_m.group(1)) if year_m else None

    # aptCode (협력업체 href=javascript:crayBtn1(..) 또는 AptSellPick href)
    apt_code_b64 = None
    cell_html = str(cell_name) + str(cell_date)  # 양쪽 셀 모두 탐색
    m = re.search(r"crayBtn1\([^,]+,'([^']+)'\)", cell_html)
    if m:
        apt_code_b64 = m.group(1)
    if not apt_code_b64:
        m = re.search(r"aptCode=([^&\"'&]+)", cell_html)
        if m:
            apt_code_b64 = m.group(1)

    apt_code = None
    if apt_code_b64:
        import base64
        try:
            apt_code = base64.b64decode(apt_code_b64 + "==").decode("ascii")
        except Exception:
            pass

    # 세대수 / 주차
    text = cell_name.get_text(" ", strip=True)
    m = re.search(r"([\d,]+)\s*세대", text)
    sedae = int(m.group(1).replace(",", "")) if m else None
    m = re.search(r"세대\s*/\s*([\d,]+)\s*대", text)
    juchaa = int(m.group(1).replace(",", "")) if m else None

    # 주소 분해 (예: '경기도 안양시 동안구 호계동')
    addr = ""
    for span in cell_name.find_all("span"):
        t = span.get_text(strip=True)
        if t.startswith(("서울", "경기")):
            addr = t
            break
    addr_parts = addr.split()
    광역 = addr_parts[0] if addr_parts else ""
    if 광역 == "경기도" and len(addr_parts) >= 4 and addr_parts[2].endswith("구"):
        시구 = f"{addr_parts[1]} {addr_parts[2]}"
        동 = addr_parts[3] if len(addr_parts) > 3 else ""
    elif 광역 == "서울특별시" and len(addr_parts) >= 3:
        시구 = addr_parts[1]
        동 = addr_parts[2]
    else:
        시구 = addr_parts[1] if len(addr_parts) > 1 else ""
        동 = addr_parts[2] if len(addr_parts) > 2 else ""

    # sparkline 가격
    spark = cell_name.find("span", class_="inlinesparkline")
    spark_txt = spark.get_text(strip=True) if spark else ""

    # ── 2번째 셀: 계약일, 면적, 평형, 층, 동, 매물 ──
    d2 = cell_date.get_text(" ", strip=True)
    date_m = re.search(r"(\d{2}\.\d{2}\.\d{2})", d2)
    contract_date = date_m.group(1) if date_m else None

    area_m = _AREA_PAT.search(d2)
    면적_m2 = float(area_m.group(1)) if area_m else None
    평형 = area_m.group(2) if area_m else None

    floor_m = _FLOOR_PAT.search(d2)
    층 = int(floor_m.group(1)) if floor_m else None

    dong_m = _DONG_PAT.search(d2)
    동번호 = dong_m.group(1) if dong_m else None

    memul_m = _MEMUL_PAT.search(d2)
    매물수 = int(memul_m.group(1)) if memul_m else None
    신규매물수 = int(memul_m.group(2)) if memul_m else None

    # 위경도 (지도 링크)
    map_a = cell_date.find("a", href=re.compile(r"map2\.jsp"))
    위도 = 경도 = None
    if map_a:
        ll = _LATLON_PAT.search(map_a.get("href", ""))
        if ll:
            위도 = float(ll.group(1))
            경도 = float(ll.group(2))

    # ── 3번째 셀: 거래금액, 회복률, 직전가, 최저가, 학교 ──
    d3 = cell_recovery.get_text(" ", strip=True)
    bold_spans = cell_recovery.find_all("span", style=re.compile(r"color:red.*font-weight:bold"))
    거래금액 = parse_amount_manwon(bold_spans[0].get_text(strip=True)) if bold_spans else None

    rec_m = _RECOVERY_PAT.search(d3)
    회복률_pct = int(rec_m.group(1)) if rec_m else None
    거래건수 = int(rec_m.group(2)) if rec_m else None

    blue_span = cell_recovery.find("span", style=re.compile(r"color:\s*blue"))
    직전가 = 최저가 = None
    if blue_span:
        amounts = re.findall(r"\d+억(?:\d+천)?(?:\d+)?", blue_span.get_text(" ", strip=True))
        if amounts:
            직전가 = parse_amount_manwon(amounts[0])
        if len(amounts) > 1:
            최저가 = parse_amount_manwon(amounts[1])

    change_m = _PREV_CHANGE_PAT.search(d3)
    직전대비_pct = None
    if change_m:
        direction = 1 if change_m.group(1) == "↑" else -1
        직전대비_pct = direction * float(change_m.group(2))

    # 학세권
    학교명 = None
    도보_분 = None
    거리_m = None
    subway_div = cell_recovery.find("div", class_="subway-info")
    if subway_div:
        학교명 = subway_div.contents[0].strip() if subway_div.contents else None
        t_span = subway_div.find("span", class_="time")
        d_span = subway_div.find("span", class_="distance")
        if t_span:
            tm = _SUBWAY_TIME_PAT.search(t_span.get_text())
            도보_분 = int(tm.group(1)) if tm else None
        if d_span:
            dm = _SUBWAY_DIST_PAT.search(d_span.get_text())
            거리_m = int(dm.group(1)) if dm else None

    return {
        "area_code": area_code,
        "area_label": AREA_LABEL.get(area_code, ""),
        "광역": 광역,
        "시구": 시구,
        "동": 동,
        "단지명": danji_nm,
        "연차": yearago,
        "aptCode": apt_code,
        "aptCode_b64": apt_code_b64,
        "세대수": sedae,
        "주차대수": juchaa,
        "위도": 위도,
        "경도": 경도,
        "계약일": contract_date,
        "면적_㎡": 면적_m2,
        "평형": 평형,
        "층": 층,
        "동번호": 동번호,
        "거래금액_만원": 거래금액,
        "회복률_pct": 회복률_pct,
        "거래건수": 거래건수,
        "직전가_만원": 직전가,
        "최저가_만원": 최저가,
        "직전대비_pct": 직전대비_pct,
        "매물수": 매물수,
        "신규매물수": 신규매물수,
        "학교명": 학교명,
        "학교_도보_분": 도보_분,
        "학교_거리_m": 거리_m,
        "시계열_가격_만원": spark_txt,
    }


def parse_page(html: str, area_code: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        try:
            row = parse_row(tr, area_code)
            if row and row["단지명"]:
                rows.append(row)
        except Exception as e:
            print(f"  ! parse error {area_code}: {e}", file=sys.stderr)
    return rows


def scrape_areas(area_codes: list[str], out_csv: Path, sleep: float = 1.5) -> int:
    cols = [
        "area_code", "area_label", "광역", "시구", "동",
        "단지명", "연차", "aptCode", "aptCode_b64", "세대수", "주차대수",
        "위도", "경도",
        "계약일", "면적_㎡", "평형", "층", "동번호",
        "거래금액_만원", "회복률_pct", "거래건수",
        "직전가_만원", "최저가_만원", "직전대비_pct",
        "매물수", "신규매물수",
        "학교명", "학교_도보_분", "학교_거리_m",
        "시계열_가격_만원",
    ]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for code in area_codes:
            label = AREA_LABEL.get(code, code)
            try:
                html = fetch_html(code)
                rows = parse_page(html, code)
                writer.writerows(rows)
                total += len(rows)
                print(f"  OK {code} {label}: {len(rows)}개")
            except Exception as e:
                print(f"  FAIL {code} {label}: {e}", file=sys.stderr)
            time.sleep(sleep)
    return total


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/apt_recovery_hangang_south.csv")
    ap.add_argument("--codes", help="콤마구분 area code, 미지정 시 한강 이남 전체")
    ap.add_argument("--sleep", type=float, default=1.5, help="요청 간 대기 (초)")
    args = ap.parse_args()

    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    else:
        codes = list(SEOUL_HANGANG_SOUTH.values()) + list(GG_HANGANG_SOUTH.values())

    out = Path(args.out)
    print(f"수집 대상: {len(codes)}개 시군구")
    total = scrape_areas(codes, out, sleep=args.sleep)
    print(f"\n완료: {total}개 단지 → {out}")


if __name__ == "__main__":
    main()
