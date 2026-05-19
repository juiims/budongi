"""국토부 RTMS 실거래가 Open API 클라이언트.

데이터셋: https://www.data.go.kr/data/15126469/openapi.do
엔드포인트: apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev

서비스 키는 .streamlit/secrets.toml 또는 RTMS_SERVICE_KEY 환경변수에서 읽음.

사용:
    from rtms_client import fetch_trades, SEOUL_HANGANG_SOUTH_LAWD
    df = fetch_trades("11680", "202604")  # 강남구 2026년 4월
"""
from __future__ import annotations

import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
ENDPOINT_RENT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

# 한강 이남 서울 11구 LAWD_CD (시군구 5자리) — 행정표준코드 기준
SEOUL_HANGANG_SOUTH_LAWD = {
    "강서구": "11500", "양천구": "11470", "영등포구": "11560", "구로구": "11530",
    "금천구": "11545", "동작구": "11590", "관악구": "11620", "서초구": "11650",
    "강남구": "11680", "송파구": "11710", "강동구": "11740",
}

# 경기 한강 이남 17개 시 LAWD_CD (시군구 단위 — 일반시 5자리 / 자치구 보유 시는 자치구별 별도)
GYEONGGI_HANGANG_SOUTH_LAWD = {
    "광명시": "41210",
    "안양시 만안구": "41171", "안양시 동안구": "41173",
    "과천시": "41290",
    "의왕시": "41430",
    "군포시": "41410",
    "안산시 단원구": "41273", "안산시 상록구": "41271",
    "수원시 장안구": "41111", "수원시 권선구": "41113",
    "수원시 팔달구": "41115", "수원시 영통구": "41117",
    "성남시 수정구": "41131", "성남시 중원구": "41133", "성남시 분당구": "41135",
    "용인시 처인구": "41461", "용인시 기흥구": "41463", "용인시 수지구": "41465",
    "오산시": "41370",
    "평택시": "41220",
    "화성시": "41591",   # 41590은 빈 결과, 41591이 실데이터
    "안성시": "41550",
    "이천시": "41500",
    "여주시": "41670",
    "광주시": "41610",
    # 부천시는 자치구 폐지(2016) 후에도 RTMS는 옛 자치구 코드 분리 유지
    "부천시 원미구": "41192",
    "부천시 소사구": "41194",
    "부천시 오정구": "41196",
    "시흥시": "41390",
    "김포시": "41570",
    "하남시": "41450",
}

ALL_LAWD = {**SEOUL_HANGANG_SOUTH_LAWD, **GYEONGGI_HANGANG_SOUTH_LAWD}


def _load_service_key() -> str:
    """secrets.toml 또는 환경변수에서 서비스 키 로드."""
    key = os.environ.get("RTMS_SERVICE_KEY")
    if key:
        return key
    secrets_path = Path(".streamlit/secrets.toml")
    if secrets_path.exists():
        for line in secrets_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("RTMS_SERVICE_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(
        "RTMS_SERVICE_KEY 없음. .streamlit/secrets.toml 또는 환경변수 설정 필요."
    )


SERVICE_KEY = _load_service_key()


def _fetch_page(lawd_cd: str, deal_ymd: str, page_no: int, num_rows: int = 1000,
                endpoint: str = ENDPOINT) -> ET.Element:
    params = {
        "serviceKey": SERVICE_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "pageNo": str(page_no),
        "numOfRows": str(num_rows),
    }
    url = endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "budong-rtms/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return ET.fromstring(r.read())


def fetch_trades(lawd_cd: str, deal_ymd: str, sleep_sec: float = 0.15) -> pd.DataFrame:
    """단일 시군구·년월의 모든 아파트 매매 거래를 DataFrame으로 반환.

    deal_ymd: "YYYYMM" (예: "202604")
    """
    rows: list[dict] = []
    page = 1
    while True:
        root = _fetch_page(lawd_cd, deal_ymd, page)
        code = root.findtext(".//resultCode")
        if code != "000":
            msg = root.findtext(".//resultMsg") or "unknown"
            raise RuntimeError(f"RTMS API 오류 {code}: {msg}")
        items = root.findall(".//item")
        if not items:
            break
        for it in items:
            rows.append({child.tag: (child.text or "").strip() for child in it})
        total = int(root.findtext(".//totalCount") or "0")
        rows_per_page = int(root.findtext(".//numOfRows") or "1000")
        if page * rows_per_page >= total:
            break
        page += 1
        time.sleep(sleep_sec)
    df = pd.DataFrame(rows)
    if len(df):
        # 핵심 컬럼 형변환
        df["dealAmount_만원"] = (
            df["dealAmount"].str.replace(",", "").astype(int)
        )
        df["거래일"] = pd.to_datetime(
            df["dealYear"] + "-" + df["dealMonth"].str.zfill(2) + "-" + df["dealDay"].str.zfill(2),
            errors="coerce",
        )
        df["excluUseAr"] = pd.to_numeric(df["excluUseAr"], errors="coerce")
        df["floor"] = pd.to_numeric(df["floor"], errors="coerce")
        df["buildYear"] = pd.to_numeric(df["buildYear"], errors="coerce")
    return df


def fetch_rents(lawd_cd: str, deal_ymd: str, sleep_sec: float = 0.15) -> pd.DataFrame:
    """단일 시군구·년월의 모든 아파트 전월세 거래 → DataFrame."""
    rows: list[dict] = []
    page = 1
    while True:
        root = _fetch_page(lawd_cd, deal_ymd, page, endpoint=ENDPOINT_RENT)
        code = root.findtext(".//resultCode")
        if code != "000":
            msg = root.findtext(".//resultMsg") or "unknown"
            raise RuntimeError(f"RTMS Rent API 오류 {code}: {msg}")
        items = root.findall(".//item")
        if not items:
            break
        for it in items:
            rows.append({child.tag: (child.text or "").strip() for child in it})
        total = int(root.findtext(".//totalCount") or "0")
        rows_per_page = int(root.findtext(".//numOfRows") or "1000")
        if page * rows_per_page >= total:
            break
        page += 1
        time.sleep(sleep_sec)
    df = pd.DataFrame(rows)
    if len(df):
        df["deposit_만원"] = df["deposit"].str.replace(",", "").replace("", "0").astype(int)
        df["monthlyRent_만원"] = df["monthlyRent"].str.replace(",", "").replace("", "0").astype(int)
        df["거래일"] = pd.to_datetime(
            df["dealYear"] + "-" + df["dealMonth"].str.zfill(2) + "-" + df["dealDay"].str.zfill(2),
            errors="coerce",
        )
        df["excluUseAr"] = pd.to_numeric(df["excluUseAr"], errors="coerce")
        df["buildYear"] = pd.to_numeric(df["buildYear"], errors="coerce")
        df["순수전세"] = df["monthlyRent_만원"] == 0
    return df


if __name__ == "__main__":
    import sys

    lawd = sys.argv[1] if len(sys.argv) > 1 else "11680"
    ymd = sys.argv[2] if len(sys.argv) > 2 else "202604"
    mode = sys.argv[3] if len(sys.argv) > 3 else "trade"
    if mode == "rent":
        df = fetch_rents(lawd, ymd)
        print(f"LAWD={lawd} YMD={ymd} 전월세 — {len(df)}건 (순수전세 {df['순수전세'].sum() if len(df) else 0}건)")
        if len(df):
            print(df[["aptNm", "umdNm", "excluUseAr", "deposit_만원", "monthlyRent_만원", "거래일"]].head(10).to_string())
    else:
        df = fetch_trades(lawd, ymd)
        print(f"LAWD={lawd} YMD={ymd} 매매 — {len(df)}건")
        if len(df):
            print(df[["aptNm", "umdNm", "excluUseAr", "floor", "dealAmount_만원", "거래일"]].head(10).to_string())
