"""중학교 학업성취율·특목고 진학 데이터를 단지 catalog와 매칭.

입력:
  data/[필디]2025년2학기_전국중학교학업성취율_특목고현황.csv
  data/catalog_scored.csv

매칭 전략 (1차 — 동 단위):
  학교를 (시구, 동) 단위로 집계 → catalog의 (시구, 동)으로 left join.

산출:
  data/school_dong.csv      (시구, 동) 단위 집계 결과
  data/catalog_with_school.csv  catalog + 학군 컬럼
  + 콘솔 리포트: 매칭률, 누락 케이스
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

SCHOOL_CSV = Path("data/[필디]2025년2학기_전국중학교학업성취율_특목고현황.csv")
CATALOG_CSV = Path("data/catalog_scored.csv")
OUT_DONG = Path("data/school_dong.csv")
OUT_CATALOG = Path("data/catalog_with_school.csv")

SEOUL_SOUTH = {
    "강서구", "양천구", "영등포구", "구로구", "금천구",
    "동작구", "관악구", "서초구", "강남구", "송파구", "강동구",
}
# 경기 한강이남 — catalog의 시구 표기와 일치하도록 (시 단위까지만)
# catalog에 등장하는 한강 인근 시 (시흥/김포/하남/부천) 포함
GG_SOUTH = {
    "광명시", "안양시", "과천시", "의왕시", "군포시", "안산시",
    "수원시", "성남시", "용인시", "오산시", "평택시", "화성시",
    "안성시", "이천시", "여주시", "광주시",
    "시흥시", "김포시", "하남시", "부천시",
}


def _normalize_school_addr(row) -> tuple[str, str]:
    """학교 주소를 catalog 시구·동 형식과 맞춤.

    서울: 주소2=시구, 주소3=동
    경기 자치구 보유 시 (주소3이 '구'로 끝남): 주소2+주소3=시구, 주소4=동
    경기 일반시: 주소2=시구, 주소3=동
    """
    p1, p2, p3, p4 = row["주소1"], row["주소2"], row["주소3"], row["주소4"]
    if p1 == "서울":
        return p2, p3 if pd.notna(p3) else None
    # 경기
    if pd.notna(p3) and str(p3).endswith("구"):
        return f"{p2} {p3}", p4 if pd.notna(p4) else None
    return p2, p3 if pd.notna(p3) else None


def load_schools() -> pd.DataFrame:
    df = pd.read_csv(SCHOOL_CSV)
    # 한강이남만
    mask = (
        ((df["주소1"] == "서울") & (df["주소2"].isin(SEOUL_SOUTH)))
        | ((df["주소1"] == "경기") & (df["주소2"].isin(GG_SOUTH)))
    )
    df = df[mask].copy()
    # 시구·동 정규화 (catalog 형식에 맞춤)
    addr = df.apply(_normalize_school_addr, axis=1)
    df["시구"] = [a[0] for a in addr]
    df["동"] = [a[1] for a in addr]
    df = df.rename(columns={
        "주소1": "광역",
        "분류": "공사립",
        "국어": "성취_국어", "영어": "성취_영어", "수학": "성취_수학",
        "평균": "성취_평균", "특목고계": "특목고진학",
    })
    # 시 단위 fallback 키 추가 (예: '성남시 분당구' → '성남시')
    df["__시"] = df["시구"].str.split(" ").str[0]
    return df


def aggregate_by_dong(schools: pd.DataFrame) -> pd.DataFrame:
    """(광역, 시구, 동) 단위로 학교 통계 집계."""
    grp = schools.groupby(["광역", "시구", "동"], dropna=False)
    agg = grp.agg(
        학교수=("학교명", "count"),
        성취_평균_avg=("성취_평균", "mean"),
        성취_평균_max=("성취_평균", "max"),
        특목고진학_합=("특목고진학", "sum"),
        특목고진학_avg=("특목고진학", "mean"),
        사립여부_비율=("공사립", lambda s: (s == "사립").mean()),
    ).reset_index()
    # 시구 단위 평균도 함께 (동이 NaN인 학교 백업)
    return agg


def aggregate_by_sigu(schools: pd.DataFrame) -> pd.DataFrame:
    """동이 없는 케이스용 fallback — (광역, 시구) 단위 집계."""
    grp = schools.groupby(["광역", "시구"], dropna=False)
    return grp.agg(
        시구_학교수=("학교명", "count"),
        시구_성취_평균_avg=("성취_평균", "mean"),
        시구_성취_평균_max=("성취_평균", "max"),
        시구_특목고진학_avg=("특목고진학", "mean"),
        시구_특목고진학_max=("특목고진학", "max"),
    ).reset_index()


def aggregate_by_si(schools: pd.DataFrame) -> pd.DataFrame:
    """시구 매칭 실패 케이스용 fallback — (광역, 시) 단위 집계."""
    grp = schools.groupby(["광역", "__시"], dropna=False)
    return grp.agg(
        시_학교수=("학교명", "count"),
        시_성취_평균_avg=("성취_평균", "mean"),
        시_성취_평균_max=("성취_평균", "max"),
        시_특목고진학_avg=("특목고진학", "mean"),
        시_특목고진학_max=("특목고진학", "max"),
    ).reset_index().rename(columns={"__시": "시"})


def match_catalog(catalog: pd.DataFrame,
                  dong_agg: pd.DataFrame,
                  sigu_agg: pd.DataFrame,
                  si_agg: pd.DataFrame) -> pd.DataFrame:
    cat = catalog.copy()

    # catalog의 지역구분과 학교 광역 매핑
    광역_map = {"서울": "서울", "경기": "경기"}
    cat["__광역"] = cat["지역구분"].map(광역_map)
    # 시구의 시 단위 (예: '성남시 분당구' → '성남시')
    cat["__시"] = cat["시구"].str.split(" ").str[0]

    # 1차: (광역, 시구, 동) 매칭
    merged = cat.merge(
        dong_agg, how="left",
        left_on=["__광역", "시구", "동"],
        right_on=["광역", "시구", "동"],
    )
    merged = merged.drop(columns=["광역"])

    # 2차 fallback: 동 매칭 실패 시 시구 평균
    merged = merged.merge(
        sigu_agg, how="left",
        left_on=["__광역", "시구"],
        right_on=["광역", "시구"],
    )
    merged = merged.drop(columns=["광역"])

    # 3차 fallback: 시구도 실패 시 시 단위 평균 (예: 화성시 동탄구 → 화성시)
    merged = merged.merge(
        si_agg, how="left",
        left_on=["__광역", "__시"],
        right_on=["광역", "시"],
    )
    merged = merged.drop(columns=["광역", "시", "__광역", "__시"], errors="ignore")

    # 매칭 단계 플래그
    def _level(row):
        if pd.notna(row.get("학교수")):
            return "동"
        if pd.notna(row.get("시구_학교수")):
            return "시구"
        if pd.notna(row.get("시_학교수")):
            return "시"
        return "없음"
    merged["학군_매칭"] = merged.apply(_level, axis=1)

    # 최종 학군 점수용 컬럼 (동 → 시구 → 시 순)
    merged["학군_성취율"] = (
        merged["성취_평균_avg"]
        .fillna(merged["시구_성취_평균_avg"])
        .fillna(merged["시_성취_평균_avg"])
    )
    merged["학군_특목고"] = (
        merged["특목고진학_avg"]
        .fillna(merged["시구_특목고진학_avg"])
        .fillna(merged["시_특목고진학_avg"])
    )

    return merged


def report(catalog_matched: pd.DataFrame, schools: pd.DataFrame):
    print("=" * 60)
    print("학군 매칭 리포트")
    print("=" * 60)
    print(f"학교 수: {len(schools):,}개교 "
          f"(서울 {(schools['광역']=='서울').sum()} / 경기 {(schools['광역']=='경기').sum()})")
    print(f"단지 수: {len(catalog_matched):,}개")
    print()
    print("매칭 결과:")
    print(catalog_matched["학군_매칭"].value_counts())
    print()
    # 동 매칭 실패한 단지의 (시구, 동) 빈도
    no_dong = catalog_matched[catalog_matched["학군_매칭"] != "동"]
    if len(no_dong) > 0:
        print(f"동 매칭 실패 단지: {len(no_dong)}개")
        print("실패 케이스 TOP 20 (시구, 동, 단지수):")
        top = no_dong.groupby(["지역구분", "시구", "동"]).size().sort_values(ascending=False).head(20)
        for (gj, sg, dg), n in top.items():
            print(f"  {gj} {sg} {dg}: {n}개")
    print()
    print("학군_성취율 분포:")
    print(catalog_matched["학군_성취율"].describe())


def main():
    print(f"학교 데이터 로드: {SCHOOL_CSV.name}")
    schools = load_schools()
    print(f"  한강이남: {len(schools):,}개교")

    dong_agg = aggregate_by_dong(schools)
    sigu_agg = aggregate_by_sigu(schools)
    si_agg = aggregate_by_si(schools)
    dong_agg.to_csv(OUT_DONG, index=False, encoding="utf-8-sig")
    print(f"\n동 단위 집계 저장: {OUT_DONG} ({len(dong_agg)}행)")

    print(f"\ncatalog 로드: {CATALOG_CSV.name}")
    catalog = pd.read_csv(CATALOG_CSV)

    matched = match_catalog(catalog, dong_agg, sigu_agg, si_agg)
    matched.to_csv(OUT_CATALOG, index=False, encoding="utf-8-sig")
    print(f"매칭 결과 저장: {OUT_CATALOG} ({len(matched)}행)")

    print()
    report(matched, schools)


if __name__ == "__main__":
    main()
