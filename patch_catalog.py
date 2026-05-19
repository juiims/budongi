"""catalog 빌드 누락 5개 자치구 재실행 후 기존 CSV에 append.

평택 시구 처리 중 chromedriver traceback 발생 → 이후 하남/화성 4개 자치구 빈 결과.
이 스크립트는 누락 자치구만 재실행해서 기존 catalog CSV에 추가.
"""
import csv
import os
import sys
import time

from naver_realty_new import setup_driver, bootstrap_token
from screen_candidates import (
    screen_district, save_csv, GANGNAM_STN, HAPJEONG_STN, NAMYANG_RND,
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ["SCREEN_NO_PRICE_FILTER"] = "1"

MISSING = [
    ("하남시", "4145000000"),
    ("화성시 동탄구", "4159700000"),
    ("화성시 만세구", "4159100000"),
    ("화성시 병점구", "4159500000"),
    ("화성시 효행구", "4159300000"),
]
EXISTING_CSV = "data/candidates_hangang_south_catalog.csv"


def main():
    # 기존 데이터 로딩
    existing = []
    if os.path.exists(EXISTING_CSV):
        with open(EXISTING_CSV, "r", encoding="utf-8-sig") as f:
            existing = list(csv.DictReader(f))
    print(f"기존 catalog: {len(existing)}행")
    existing_ids = {r.get("단지번호") for r in existing if r.get("단지번호")}

    driver = setup_driver(headless=False)
    new_rows = []
    try:
        auth_holder = [bootstrap_token(driver)]
        for i, (name, cortarNo) in enumerate(MISSING):
            elapsed_label = f"{i+1}/{len(MISSING)}"
            try:
                rows = screen_district(driver, name, cortarNo, auth_holder, elapsed_label)
                # 기존에 없는 단지만 추가
                added = 0
                for r in rows:
                    if r.get("단지번호") not in existing_ids:
                        new_rows.append(r)
                        existing_ids.add(r.get("단지번호"))
                        added += 1
                print(f"  → 신규 {added}개 (총 응답 {len(rows)}개)")
            except Exception as e:
                import traceback
                traceback.print_exc()
            time.sleep(1)
    finally:
        driver.quit()

    # 기존 + 신규 합쳐서 저장
    combined = existing + new_rows
    print(f"\n최종: {len(existing)} + {len(new_rows)} = {len(combined)}행")
    save_csv(combined, EXISTING_CSV)


if __name__ == "__main__":
    main()
