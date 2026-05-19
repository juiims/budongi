"""경기도 시군구 응답 구조 검사 — 누락 7개 시 매칭 확인."""
import sys
import time
from naver_realty_new import setup_driver, bootstrap_token, fetch_json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MISSING = ["성남시", "부천시", "용인시", "수원시", "안양시", "안산시", "화성시"]

driver = setup_driver(headless=False)
try:
    auth = bootstrap_token(driver)

    print("=" * 60)
    print("1단계: 경기도 (4100000000) 하위 응답")
    print("=" * 60)
    res = fetch_json(driver, "/api/regions/list?cortarNo=4100000000", auth)
    regions = res.get("regionList") or []
    print(f"총 {len(regions)}개")
    for r in regions:
        name = r.get("cortarName", "")
        flag = ""
        if name in MISSING:
            flag = "  ★ (시 단위로 발견)"
        for m in MISSING:
            if m != name and m in name:
                flag = f"  ◆ (부분일치: {m})"
                break
        print(f"  {r.get('cortarNo')} | {name} | type={r.get('cortarType')}{flag}")

    print()
    print("=" * 60)
    print("2단계: 누락 시 부분일치 점검")
    print("=" * 60)
    name_to_no = {r.get("cortarName"): r.get("cortarNo") for r in regions}
    for m in MISSING:
        if m in name_to_no:
            print(f"  [{m}] 직접 매칭됨 → {name_to_no[m]}")
            continue
        partial = [(n, no) for n, no in name_to_no.items() if m in n or n.startswith(m)]
        if partial:
            print(f"  [{m}] 부분일치 {len(partial)}개:")
            for n, no in partial:
                print(f"      - {no} | {n}")
        else:
            print(f"  [{m}] 일치 없음")

    # 만약 부분일치한 첫 항목으로 하위 호출 시 동 응답 보기 (예: 성남시 분당구)
    print()
    print("=" * 60)
    print("3단계: 부분일치 첫 항목 하위 응답 샘플")
    print("=" * 60)
    for m in MISSING:
        partial = [(n, no) for n, no in name_to_no.items() if m in n]
        if not partial:
            continue
        sample_name, sample_no = partial[0]
        time.sleep(0.5)
        sub = fetch_json(driver, f"/api/regions/list?cortarNo={sample_no}", auth)
        sub_regions = sub.get("regionList") or []
        print(f"  [{sample_name} / {sample_no}] 하위 {len(sub_regions)}개")
        for s in sub_regions[:3]:
            print(f"      {s.get('cortarNo')} | {s.get('cortarName')} | type={s.get('cortarType')}")
        if len(sub_regions) > 3:
            print(f"      ... +{len(sub_regions)-3}개")

finally:
    driver.quit()
