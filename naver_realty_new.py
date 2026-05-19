"""
네이버 부동산 데이터 수집 - 하이브리드 방식
=========================================
참고 블로그: https://leesunkyu94.github.io/data%20%EB%A7%8C%EB%93%A4%EA%B8%B0/naver-real-estate/

블로그와 동일하게 `new.land.naver.com/api/*` 엔드포인트를 사용하되,
- Selenium으로 브라우저 세션을 열고
- Chrome Performance Log로 페이지가 발급하는 Bearer JWT를 가로채고
- 그 토큰으로 `/api/search`, `/api/complexes/{id}`, `/api/complexes/{id}/prices` 호출

실행:
    pip install selenium webdriver-manager
    python naver_realty_new.py

Chrome 브라우저 필요.
"""

import json
import sys
import time
import csv
import os
from datetime import datetime
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

os.environ.setdefault("WDM_SSL_VERIFY", "0")

# Windows 콘솔(cp949)에서도 한글/이모지 깨지지 않도록 stdout/stderr 강제 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ============================================================
# 검색할 단지 리스트
# ============================================================
APT_LIST = [
    "하안주공9단지",
    "강서힐스테이트",
    "관악드림타운",
    "목동신시가지5단지",
    "철산래미안자이",
]

DELAY_BETWEEN_APTS = 4
DELAY_BETWEEN_API = 1.0
MAX_ARTICLE_PAGES = 20  # 평형별 매물 페이지 상한 (안전장치)

# 토큰 부트스트랩에 사용할 임의 단지 ID (페이지를 한번 열어 토큰을 발급받음)
BOOTSTRAP_COMPLEX_ID = "103305"  # 강서힐스테이트


def setup_driver(headless: bool = False) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,900")
    options.add_argument("--lang=ko-KR")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    driver.execute_cdp_cmd("Network.enable", {})
    driver.set_script_timeout(30)
    return driver


def extract_bearer_token(driver: webdriver.Chrome) -> str | None:
    """Performance log에서 /api/* 요청의 Authorization 헤더 추출."""
    logs = driver.get_log("performance")
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
        except Exception:
            continue
        if msg.get("method") != "Network.requestWillBeSent":
            continue
        req = msg.get("params", {}).get("request", {})
        url = req.get("url", "")
        if "new.land.naver.com/api/" not in url:
            continue
        for k, v in (req.get("headers") or {}).items():
            if k.lower() == "authorization" and v.lower().startswith("bearer "):
                return v
    return None


def fetch_json(driver: webdriver.Chrome, path: str, auth: str | None = None) -> dict:
    """브라우저 컨텍스트에서 /api/* fetch — Authorization 헤더 첨부."""
    script = """
        const cb = arguments[arguments.length - 1];
        const path = arguments[0];
        const auth = arguments[1];
        const headers = {'Accept': 'application/json'};
        if (auth) headers['Authorization'] = auth;
        fetch(path, {credentials: 'include', headers})
          .then(r => r.text().then(t => ({status: r.status, body: t})))
          .then(x => cb(x))
          .catch(e => cb({status: 0, body: String(e)}));
    """
    res = driver.execute_async_script(script, path, auth)
    if res.get("status") != 200:
        return {"_error": f"HTTP {res.get('status')}", "_body": res.get("body", "")[:300]}
    try:
        return json.loads(res["body"])
    except json.JSONDecodeError:
        return {"_error": "non-json", "_body": res["body"][:300]}


def bootstrap_token(driver: webdriver.Chrome) -> str:
    """단지 페이지 한 번 열어 토큰 가로채기."""
    print(f"[부트스트랩] 토큰 발급용 페이지 로드 (complex {BOOTSTRAP_COMPLEX_ID})")
    driver.get(f"https://new.land.naver.com/complexes/{BOOTSTRAP_COMPLEX_ID}")
    # API 호출이 발생하도록 충분히 대기
    for attempt in range(6):
        time.sleep(2)
        token = extract_bearer_token(driver)
        if token:
            print(f"[부트스트랩] 토큰 획득: {token[:40]}...")
            return token
    raise RuntimeError("토큰 추출 실패 — 페이지가 API 호출을 안 함")


def search_complex(driver: webdriver.Chrome, apt_name: str, auth: str) -> dict | None:
    res = fetch_json(driver, f"/api/search?keyword={quote(apt_name)}&page=1", auth)
    if "_error" in res:
        return None
    return (res.get("complexes") or [None])[0]


def fetch_articles_by_pyeong(
    driver: webdriver.Chrome,
    complex_no: str,
    pyeong_no,
    auth: str,
) -> list[dict]:
    """평형별 매매 매물 리스트 (페이지네이션)."""
    articles: list[dict] = []
    for page in range(1, MAX_ARTICLE_PAGES + 1):
        path = (
            f"/api/articles/complex/{complex_no}"
            f"?realEstateType=APT"
            f"&tradeType=A1"
            f"&order=rank"
            f"&priceType=RETAIL"
            f"&complexNo={complex_no}"
            f"&areaNos={pyeong_no}"
            f"&page={page}"
        )
        res = fetch_json(driver, path, auth)
        if "_error" in res:
            break
        page_articles = res.get("articleList") or []
        if not page_articles:
            break
        articles.extend(page_articles)
        if not res.get("isMoreData"):
            break
        time.sleep(DELAY_BETWEEN_API)
    return articles


def extract_apt(driver: webdriver.Chrome, apt_name: str, auth: str) -> dict:
    out = {"검색어": apt_name}

    summary = search_complex(driver, apt_name, auth)
    if not summary:
        out["에러"] = "검색 결과 없음"
        return out

    complex_no = summary.get("complexNo")
    out["단지번호"] = complex_no
    out["단지명_검색결과"] = summary.get("complexName")
    out["주소_검색결과"] = summary.get("cortarAddress")

    time.sleep(DELAY_BETWEEN_API)
    detail = fetch_json(driver, f"/api/complexes/{complex_no}?sameAddressGroup=false", auth)
    if "_error" in detail:
        out["에러"] = f"단지 상세 실패: {detail['_error']}"
        return out

    cd = detail.get("complexDetail") or detail
    out["단지명"] = cd.get("complexName")
    out["주소"] = cd.get("address") or cd.get("roadAddress")
    out["총세대수"] = cd.get("totalHouseholdCount") or cd.get("totalHsehCnt")
    out["총동수"] = cd.get("totalDongCount")
    out["입주연월"] = cd.get("useApproveYmd")
    out["최저층"] = cd.get("lowFloor")
    out["최고층"] = cd.get("highFloor")
    out["주차대수"] = cd.get("totalParkingCount")
    out["용적률"] = cd.get("batlRatio") or cd.get("floorAreaRatio")
    out["건폐율"] = cd.get("btlRatio") or cd.get("buildingCoverageRatio")
    out["위도"] = cd.get("latitude")
    out["경도"] = cd.get("longitude")

    pyeongs = (
        detail.get("complexPyeongDetailList")
        or cd.get("complexPyeongDetailList")
        or []
    )
    out["평형들"] = []
    for p in pyeongs:
        stat = p.get("articleStatistics") or {}
        mc = p.get("averageMaintenanceCost") or {}
        pyeong_no = p.get("pyeongNo") or p.get("pyeongTypeNo")
        item = {
            "평형번호": pyeong_no,
            "평형명": p.get("pyeongName2") or p.get("pyeongName"),
            "공급면적_㎡": p.get("supplyArea"),
            "전용면적_㎡": p.get("exclusiveArea"),
            "전용평": p.get("exclusivePyeong"),
            "전용률_%": p.get("exclusiveRate"),
            "세대수": p.get("householdCountByPyeong"),
            "방수": p.get("roomCnt"),
            "욕실수": p.get("bathroomCnt"),
            "현관구조": p.get("entranceType"),
            # 매매
            "매매건수": stat.get("dealCount"),
            "매매가_최저": stat.get("dealPriceMin"),
            "매매가_최고": stat.get("dealPriceMax"),
            "매매가_범위": stat.get("dealPriceString"),
            "매매_평단가": stat.get("dealPricePerSpaceString"),
            # 전세
            "전세건수": stat.get("leaseCount"),
            "전세가_최저": stat.get("leasePriceMin"),
            "전세가_최고": stat.get("leasePriceMax"),
            "전세가_범위": stat.get("leasePriceString"),
            "전세_평단가": stat.get("leasePricePerSpaceString"),
            "전세가율_%": stat.get("leasePriceRateString"),
            # 월세
            "월세건수": stat.get("rentCount"),
            "월세가_범위": stat.get("rentPriceString"),
            # 관리비
            "관리비_연평균": mc.get("averageTotalPrice"),
            "관리비_여름": mc.get("summerTotalPrice"),
            "관리비_겨울": mc.get("winterTotalPrice"),
        }

        deal_count_raw = stat.get("dealCount")
        try:
            deal_count = int(deal_count_raw) if deal_count_raw not in (None, "") else 0
        except (ValueError, TypeError):
            deal_count = 0
        if pyeong_no and deal_count > 0:
            time.sleep(DELAY_BETWEEN_API)
            item["매물들"] = fetch_articles_by_pyeong(
                driver, complex_no, pyeong_no, auth
            )
        else:
            item["매물들"] = []

        out["평형들"].append(item)

    return out


def save_results(results: list[dict]) -> None:
    with open("naver_new_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nJSON: naver_new_results.json")

    rows = []
    for r in results:
        if "에러" in r:
            rows.append({"검색어": r["검색어"], "에러": r["에러"]})
            continue
        base = {k: v for k, v in r.items() if k != "평형들"}
        if not r.get("평형들"):
            rows.append(base)
            continue
        for p in r["평형들"]:
            pyeong_base = {**base, **{k: v for k, v in p.items() if k != "매물들"}}
            articles = p.get("매물들") or []
            if not articles:
                rows.append(pyeong_base)
                continue
            for a in articles:
                rows.append({
                    **pyeong_base,
                    "매물번호": a.get("articleNo"),
                    "매물명": a.get("articleName"),
                    "거래종류": a.get("tradeTypeName"),
                    "매물가격": a.get("dealOrWarrantPrc"),
                    "매물_공급면적_㎡": a.get("area1"),
                    "매물_전용면적_㎡": a.get("area2"),
                    "층정보": a.get("floorInfo"),
                    "향": a.get("direction"),
                    "동": a.get("buildingName"),
                    "확인일자": a.get("articleConfirmYmd"),
                    "매물특징": a.get("articleFeatureDesc"),
                    "중개사": a.get("realtorName"),
                })

    if not rows:
        return
    keys, seen = [], set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                keys.append(k); seen.add(k)
    csv_path = "naver_new_results.csv"
    try:
        f = open(csv_path, "w", newline="", encoding="utf-8-sig")
    except PermissionError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = f"naver_new_results_{ts}.csv"
        print(f"[경고] naver_new_results.csv 가 잠겨 있음 → {csv_path} 로 저장")
        f = open(csv_path, "w", newline="", encoding="utf-8-sig")
    with f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"CSV : {csv_path} ({len(rows)} 행)")


def main() -> None:
    print("=" * 60)
    print("네이버 부동산 수집 (블로그 방식 + Selenium 토큰 부트스트랩)")
    print("=" * 60)

    driver = setup_driver(headless=False)
    results = []
    try:
        auth = bootstrap_token(driver)

        for idx, name in enumerate(APT_LIST, 1):
            print(f"\n[{idx}/{len(APT_LIST)}] {name}")
            try:
                data = extract_apt(driver, name, auth)
            except Exception as e:
                data = {"검색어": name, "에러": f"예외: {e}"}
            results.append(data)

            if "에러" in data:
                print(f"  ❌ {data['에러']}")
            else:
                article_total = sum(
                    len(p.get("매물들") or []) for p in data.get("평형들", [])
                )
                print(f"  ✅ {data.get('단지명')} ({data.get('단지번호')}) | "
                      f"{data.get('총세대수')}세대 | "
                      f"평형 {len(data.get('평형들', []))}개 | "
                      f"매물 {article_total}건")
            time.sleep(DELAY_BETWEEN_APTS)
    finally:
        driver.quit()
        save_results(results)


if __name__ == "__main__":
    main()
