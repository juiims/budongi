"""Naver 단지 페이지가 호출하는 모든 API 추적 + HTML 소스에서 '도보/역' 검색."""
import json
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TARGET_ID = "103305"  # 강서힐스테이트


def make_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--lang=ko-KR")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)


def main():
    driver = make_driver()
    try:
        url = f"https://new.land.naver.com/complexes/{TARGET_ID}"
        print(f"페이지 로드: {url}")
        driver.get(url)
        time.sleep(5)  # XHR 호출 끝날 때까지

        # 1) HTML 소스에서 '도보'·'역'·'지하철' 패턴 검색
        html = driver.page_source
        print(f"\n=== HTML 소스 길이: {len(html):,} ===")
        for kw in ["도보", "지하철", "정류장", "버스"]:
            cnt = html.count(kw)
            print(f"  '{kw}' {cnt}회 등장")

        # 도보 분 패턴 발견 시 주변 컨텍스트
        for m in re.finditer(r".{40}도보\s*\d+\s*분.{40}", html)[:8] if hasattr(re.finditer(r"", ""), '__getitem__') else list(re.finditer(r".{40}도보\s*\d+\s*분.{40}", html))[:8]:
            print(f"    컨텍스트: {m.group()}")

        # 2) Performance Log에서 호출된 모든 API path 수집
        logs = driver.get_log("performance")
        api_calls = set()
        for log in logs:
            try:
                msg = json.loads(log["message"])["message"]
                if msg.get("method") == "Network.requestWillBeSent":
                    req_url = msg["params"]["request"]["url"]
                    if "new.land.naver.com/api/" in req_url or "naver.com" in req_url:
                        # path만 추출
                        path = req_url.split("naver.com", 1)[1].split("?")[0]
                        api_calls.add(path)
            except Exception:
                continue

        print(f"\n=== 호출된 API path {len(api_calls)}개 ===")
        for p in sorted(api_calls):
            print(f"  {p}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
