"""apt2.me 학군 데이터 통합 스크래퍼.

4가지 페이지를 시군구별로 수집:
  1) schoolTrend.jsp  — 학교별 5년 A등급 비율 추세 (중·고)
  2) middleGrade.jsp  — 중학교 학교별 성취도 (평균/표준편차/A~E 분포)
  3) highGrade.jsp    — 고등학교 학교별 성취도
  4) middle.jsp       — 중학교 학교별 특목고 진학실적

출력:
  data/apt2_school_trend.csv
  data/apt2_middle_grade.csv
  data/apt2_high_grade.csv
  data/apt2_middle_special.csv

area code는 data/apt2_area_codes.json (extract_area_codes.py 산출물) 사용.
강원(42)·전북(45)은 apt2.me 데이터 없음. 223개 시군구.

비교 금지: 절대값(가격류)은 RTMS와 다르나 학군 데이터는 자체로 유효.
"""
from __future__ import annotations

import csv
import json
import re
import ssl
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
BASE = "https://apt2.me/apt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

SIDO_NAME = {
    "11":"서울","26":"부산","27":"대구","28":"인천","29":"광주","30":"대전","31":"울산",
    "36":"세종","41":"경기","42":"강원","43":"충북","44":"충남","45":"전북","46":"전남",
    "47":"경북","48":"경남","50":"제주",
}


def fetch_html(url: str, retries: int = 3, sleep: float = 1.0) -> str | None:
    last_err = None
    for i in range(retries):
        try:
            req = Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ko-KR,ko;q=0.9",
            })
            with urlopen(req, context=_SSL_CTX, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            time.sleep(sleep * (i + 1))
    sys.stderr.write(f"fetch 실패 {url}: {last_err}\n")
    return None


_PAGE_PAT = re.compile(r"pages=(\d+)")


def detect_max_page(html: str) -> int:
    """페이지네이션 마커에서 최대 페이지 번호 추출. 없으면 1."""
    pages = [int(m) for m in _PAGE_PAT.findall(html)]
    return max(pages) if pages else 1


# ── 공통 파서 헬퍼 ──
_MCODE_PAT = re.compile(r"mcode=([A-Za-z0-9+/=]+)")
_POS_PAT = re.compile(r"pos_x=([\d.\-]+)&pos_y=([\d.\-]+)")


def extract_school_meta(td_school) -> dict:
    """학교명 td 에서 학교명/사립공립/주소/mcode/좌표 추출."""
    text = td_school.get_text("\n", strip=True)
    lines = [l for l in text.split("\n") if l.strip()]
    school_name = ""
    school_type = ""  # 사립/공립
    address = ""
    if lines:
        first = lines[0]
        m = re.match(r"^(.+?)\s*(사립|공립|국립|자율|자사|특목)?$", first)
        if m:
            school_name = m.group(1).strip()
            school_type = m.group(2) or ""
        else:
            school_name = first
    # 주소 — '서울특별시', '경기도' 등으로 시작하는 라인
    for l in lines[1:]:
        if re.match(r"^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)", l):
            address = l
            break
    mcode_m = _MCODE_PAT.search(str(td_school))
    pos_m = _POS_PAT.search(str(td_school))
    return {
        "학교명": school_name,
        "설립구분": school_type,
        "주소": address,
        "mcode": mcode_m.group(1) if mcode_m else "",
        "위도": float(pos_m.group(2)) if pos_m else None,
        "경도": float(pos_m.group(1)) if pos_m else None,
    }


def to_float(s: str) -> float | None:
    s = re.sub(r"[^\d.\-]", "", s or "")
    if not s or s in ("-", ".", "-.", ".-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ── 1) middleGrade.jsp / highGrade.jsp 파서 (구조 동일) ──
def parse_grade_page(html: str, sido: str, sigu: str, area: str, level: str) -> list[dict]:
    """학교별 성취도. level='M'(중) 또는 'H'(고)."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    # 데이터 td: class='td_style1'. 학교명 td 는 anchor가 mcode 포함.
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", class_="td_style1")
        if len(tds) < 3:
            continue
        if "mcode=" not in str(tds[0]):
            continue
        meta = extract_school_meta(tds[0])
        # 좌표는 tds[2] 의 지도 링크에 있음
        pos_m = _POS_PAT.search(str(tr))
        if pos_m:
            meta["위도"] = float(pos_m.group(2))
            meta["경도"] = float(pos_m.group(1))
        # tds[1] : 평균/표준편차  "92.1\n0"
        mean_lines = [l.strip() for l in tds[1].get_text("\n").split("\n") if l.strip()]
        평균 = to_float(mean_lines[0]) if mean_lines else None
        표준편차 = to_float(mean_lines[1]) if len(mean_lines) > 1 else None
        # tds[2] : A/B/C/D/E "79.1/9.2/4.0\n4.0/3.7" → 5 floats
        dist_text = tds[2].get_text(" ").replace("\n", " ")
        dist_nums = re.findall(r"[\d.]+", dist_text)
        # 처음 5개가 A/B/C/D/E (지도 좌표가 뒤에 붙을 수 있어 head)
        a = to_float(dist_nums[0]) if len(dist_nums) > 0 else None
        b = to_float(dist_nums[1]) if len(dist_nums) > 1 else None
        c = to_float(dist_nums[2]) if len(dist_nums) > 2 else None
        d = to_float(dist_nums[3]) if len(dist_nums) > 3 else None
        e = to_float(dist_nums[4]) if len(dist_nums) > 4 else None
        rows.append({
            "광역": SIDO_NAME.get(sido, sido),
            "시도코드": sido,
            "시군구": sigu,
            "area": area,
            "학교급": level,
            **meta,
            "평균": 평균,
            "표준편차": 표준편차,
            "A_pct": a,
            "B_pct": b,
            "C_pct": c,
            "D_pct": d,
            "E_pct": e,
        })
    return rows


# ── 2) middle.jsp 파서 (특목고 진학) ──
def parse_special_page(html: str, sido: str, sigu: str, area: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", class_="td_style1")
        if len(tds) < 3:
            continue
        if "mcode=" not in str(tds[0]):
            continue
        meta = extract_school_meta(tds[0])
        pos_m = _POS_PAT.search(str(tr))
        if pos_m:
            meta["위도"] = float(pos_m.group(2))
            meta["경도"] = float(pos_m.group(1))
        # tds[1] : 과고/외고/국제고/자사고/영재고 "0 명\n6 명\n7 명\n0 명"
        nums_1 = re.findall(r"(\d+)\s*명", tds[1].get_text(" "))
        과고 = int(nums_1[0]) if len(nums_1) > 0 else None
        외고국제고 = int(nums_1[1]) if len(nums_1) > 1 else None
        자사고 = int(nums_1[2]) if len(nums_1) > 2 else None
        영재고 = int(nums_1[3]) if len(nums_1) > 3 else None
        # tds[2] : "118 / 50 / 68\n8 명\n6.78 %"
        t2 = tds[2].get_text(" ")
        총인원_m = re.match(r"\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)", t2)
        총인원 = int(총인원_m.group(1)) if 총인원_m else None
        남 = int(총인원_m.group(2)) if 총인원_m else None
        여 = int(총인원_m.group(3)) if 총인원_m else None
        특목고계_m = re.search(r"(\d+)\s*명", t2[총인원_m.end():] if 총인원_m else t2)
        특목고계 = int(특목고계_m.group(1)) if 특목고계_m else None
        비율_m = re.search(r"([\d.]+)\s*%", t2)
        특목고비율 = to_float(비율_m.group(1)) if 비율_m else None
        rows.append({
            "광역": SIDO_NAME.get(sido, sido),
            "시도코드": sido,
            "시군구": sigu,
            "area": area,
            **meta,
            "과고": 과고,
            "외고국제고": 외고국제고,
            "자사고": 자사고,
            "영재고": 영재고,
            "총인원": 총인원,
            "남": 남,
            "여": 여,
            "특목고계": 특목고계,
            "특목고비율_pct": 특목고비율,
        })
    return rows


# ── 3) schoolTrend.jsp 파서 (학교별 5년 추세) ──
def parse_trend_page(html: str, sido: str, sigu: str, area: str, level: str) -> list[dict]:
    """학교별 5년 추세. 학교마다 div 블럭, 내부에 원점수/환산/과목 row."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    # 각 학교 블럭은 'cateBox' 아래 div들. mcode 링크가 있는 div를 찾음.
    for div in soup.find_all("div"):
        link = div.find("a", href=re.compile(r"mcode="))
        if not link:
            continue
        # 자식 table이 있어야 학교 블럭. 헤더 영역 div 등은 제외.
        tbl = div.find("table")
        if not tbl:
            continue
        # 같은 div 안에 '구분' th 가 있는 table 만 채택 (단지명 link만 있는 헤더 div 배제)
        if "원점수" not in div.get_text():
            continue
        # 학교 메타
        school_name = link.get_text(strip=True)
        mcode_m = _MCODE_PAT.search(link["href"])
        mcode = mcode_m.group(1) if mcode_m else ""
        # 주소·설립구분: div text에서 추출
        text = div.get_text("\n", strip=True)
        type_m = re.search(r"(사립|공립|국립|자율|자사|특목)", text)
        설립구분 = type_m.group(1) if type_m else ""
        addr_m = re.search(r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)\S*\s+\S+\s+\S+", text)
        주소 = addr_m.group(0).split("\n")[0] if addr_m else ""
        # row 추출
        data = {"원점수": {}, "환산": {}}
        for tr in tbl.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            label = tds[0].get_text(strip=True)
            # '원점수' 또는 '환산수학×1.5' (br 제거 후 text)
            key = None
            if label.startswith("원점수"):
                key = "원점수"
            elif label.startswith("환산"):
                key = "환산"
            if key and len(tds) >= 7:
                vals = [to_float(td.get_text(strip=True)) for td in tds[1:6]]
                data[key]["2021"] = vals[0]
                data[key]["2022"] = vals[1]
                data[key]["2023"] = vals[2]
                data[key]["2024"] = vals[3]
                data[key]["2025"] = vals[4]
                data[key]["5년평균"] = to_float(tds[6].get_text(strip=True))
                trend_text = tds[7].get_text(strip=True) if len(tds) > 7 else ""
                data[key]["3년추세"] = trend_text.replace("▲", "").replace("▼", "").strip()
                prev_text = tds[8].get_text(strip=True) if len(tds) > 8 else ""
                data[key]["전년대비"] = to_float(prev_text.replace("▲", "").replace("▼", ""))
            # 2025과목 row
            if label == "2025과목":
                full_text = " ".join(td.get_text(" ", strip=True) for td in tds[1:])
                m_k = re.search(r"국어A\s*([\d.]+)%", full_text)
                m_m = re.search(r"수학A\s*([\d.]+)%", full_text)
                m_e = re.search(r"영어A\s*([\d.]+)%", full_text)
                m_low = re.search(r"수학최하위\s*([\d.]+)%", full_text)
                m_top = re.search(r"5년최고\s*(\d+)", full_text)
                data["2025_국어A"] = to_float(m_k.group(1)) if m_k else None
                data["2025_수학A"] = to_float(m_m.group(1)) if m_m else None
                data["2025_영어A"] = to_float(m_e.group(1)) if m_e else None
                data["2025_수학최하위"] = to_float(m_low.group(1)) if m_low else None
                data["5년최고연도"] = int(m_top.group(1)) if m_top else None
        rows.append({
            "광역": SIDO_NAME.get(sido, sido),
            "시도코드": sido,
            "시군구": sigu,
            "area": area,
            "학교급": level,
            "학교명": school_name,
            "설립구분": 설립구분,
            "주소": 주소,
            "mcode": mcode,
            "원점수_2021": data["원점수"].get("2021"),
            "원점수_2022": data["원점수"].get("2022"),
            "원점수_2023": data["원점수"].get("2023"),
            "원점수_2024": data["원점수"].get("2024"),
            "원점수_2025": data["원점수"].get("2025"),
            "원점수_5년평균": data["원점수"].get("5년평균"),
            "원점수_3년추세": data["원점수"].get("3년추세"),
            "원점수_전년대비": data["원점수"].get("전년대비"),
            "환산_2021": data["환산"].get("2021"),
            "환산_2022": data["환산"].get("2022"),
            "환산_2023": data["환산"].get("2023"),
            "환산_2024": data["환산"].get("2024"),
            "환산_2025": data["환산"].get("2025"),
            "환산_5년평균": data["환산"].get("5년평균"),
            "환산_3년추세": data["환산"].get("3년추세"),
            "환산_전년대비": data["환산"].get("전년대비"),
            "_2025_국어A": data.get("2025_국어A"),
            "_2025_수학A": data.get("2025_수학A"),
            "_2025_영어A": data.get("2025_영어A"),
            "_2025_수학최하위": data.get("2025_수학최하위"),
            "_5년최고연도": data.get("5년최고연도"),
        })
    return rows


# ── 페이지네이션 수집 ──
def fetch_pages(endpoint: str, area: str, extra: str = "") -> list[str]:
    """페이지 1부터 시작, max_page 만큼 fetch. 빈/실패 페이지에서 중단."""
    url1 = f"{BASE}/{endpoint}?area={area}{extra}&pages=1"
    h1 = fetch_html(url1)
    if not h1:
        return []
    htmls = [h1]
    max_p = detect_max_page(h1)
    for p in range(2, max_p + 1):
        url = f"{BASE}/{endpoint}?area={area}{extra}&pages={p}"
        h = fetch_html(url)
        if not h:
            break
        htmls.append(h)
        time.sleep(0.4)
    return htmls


# ── 메인 ──
def main():
    areas_json = ROOT / "data" / "apt2_area_codes.json"
    areas_map = json.loads(areas_json.read_text(encoding="utf-8"))
    # flatten
    all_areas: list[tuple[str, str, str]] = []  # (sido, sigu, area_code)
    for sido, sub in areas_map.items():
        for name, code in sub.items():
            all_areas.append((sido, name, code))
    print(f"총 {len(all_areas)}개 시군구 수집 시작")

    rows_mg: list[dict] = []  # 중학교 성취도
    rows_hg: list[dict] = []  # 고등학교 성취도
    rows_sp: list[dict] = []  # 특목고 진학
    rows_tr: list[dict] = []  # 5년 추세 (중·고 합본)

    for i, (sido, sigu, area) in enumerate(all_areas, 1):
        print(f"[{i}/{len(all_areas)}] {SIDO_NAME[sido]} {sigu} ({area})", flush=True)

        try:
            for h in fetch_pages("middleGrade.jsp", area):
                rows_mg.extend(parse_grade_page(h, sido, sigu, area, "중"))
        except Exception as e:
            sys.stderr.write(f"  middleGrade 실패 {area}: {e}\n")
        try:
            for h in fetch_pages("highGrade.jsp", area):
                rows_hg.extend(parse_grade_page(h, sido, sigu, area, "고"))
        except Exception as e:
            sys.stderr.write(f"  highGrade 실패 {area}: {e}\n")
        try:
            for h in fetch_pages("middle.jsp", area):
                rows_sp.extend(parse_special_page(h, sido, sigu, area))
        except Exception as e:
            sys.stderr.write(f"  middle 실패 {area}: {e}\n")
        try:
            for h in fetch_pages("schoolTrend.jsp", area, "&Cmb_gubun=03"):
                rows_tr.extend(parse_trend_page(h, sido, sigu, area, "중"))
            for h in fetch_pages("schoolTrend.jsp", area, "&Cmb_gubun=04"):
                rows_tr.extend(parse_trend_page(h, sido, sigu, area, "고"))
        except Exception as e:
            sys.stderr.write(f"  schoolTrend 실패 {area}: {e}\n")

        time.sleep(0.3)

    # 저장
    def save(rows: list[dict], name: str):
        if not rows:
            print(f"  {name}: empty")
            return
        out = ROOT / "data" / name
        keys = list(rows[0].keys())
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        print(f"  saved {name}: {len(rows):,} rows -> {out}")

    save(rows_mg, "apt2_middle_grade.csv")
    save(rows_hg, "apt2_high_grade.csv")
    save(rows_sp, "apt2_middle_special.csv")
    save(rows_tr, "apt2_school_trend.csv")


if __name__ == "__main__":
    main()
