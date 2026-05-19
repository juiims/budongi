"""apt2.me 학군 4종 → catalog 통합.

입력:
  data/apt2_middle_grade.csv   (중학교 성취도)
  data/apt2_high_grade.csv     (고등학교 성취도)
  data/apt2_school_trend.csv   (5년 추세, 중·고)
  data/apt2_middle_special.csv (특목고 진학)
  data/catalog_with_school_scored.csv (기존 [필디] 통합본)

처리:
  1) 학교 주소 파싱 → 광역·시구(catalog 형식)·동
     - 서울: '서울특별시 강남구 대치동' → ('서울','강남구','대치동')
     - 경기 자치구: '경기도 화성시 동탄대로 …' + apt2 시군구='동탄구'
       → ('경기','화성시 동탄구','동탄대로')  ← 동이 도로명일 때 NaN 처리
     - 경기 일반: '경기도 광명시 하안동' → ('경기','광명시','하안동')
     - 광역시: '부산광역시 해운대구 좌동' → ('부산','해운대구','좌동')
  2) (광역,시구,동), (광역,시구), (광역,시) 3단 집계
  3) catalog와 left-join 3단 fallback
  4) 산출: data/catalog_apt2_school.csv

[[feedback-cross-source-comparison]] 준수: [필디] 컬럼은 그대로 두고
apt2 컬럼은 `apt2_` prefix로 분리. 시간변화·내부 비교에만 사용.
"""
from __future__ import annotations
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "data"

SIDO_SHORT = {
    "서울특별시":"서울","부산광역시":"부산","대구광역시":"대구","인천광역시":"인천",
    "광주광역시":"광주","대전광역시":"대전","울산광역시":"울산","세종특별자치시":"세종",
    "경기도":"경기","강원도":"강원","강원특별자치도":"강원",
    "충청북도":"충북","충청남도":"충남",
    "전라북도":"전북","전북특별자치도":"전북","전라남도":"전남",
    "경상북도":"경북","경상남도":"경남",
    "제주특별자치도":"제주","제주도":"제주",
    "서울":"서울","경기":"경기",
}

# 광역시 자치구 (자체로 시구) — 시 prefix 불필요
METRO_SIDO = {"서울","부산","대구","인천","광주","대전","울산","세종"}

# 동 추출 패턴 — '○○동', '○○읍', '○○면', '○○리'로 끝나는 단어
DONG_PAT = re.compile(r"([가-힣0-9]+(?:동|읍|면|리))(?:\s|$|[\d])")

# 행정동 → 법정동 정규화: "목5동" → "목동", "신정2동" → "신정동"
# catalog 단지의 동은 법정동, 학교 주소는 행정동인 경우가 많음.
ADMIN_TO_LEGAL_DONG = re.compile(r"^([가-힣]+?)\d+동$")

def normalize_dong(dong: str | None) -> str | None:
    if not dong:
        return None
    m = ADMIN_TO_LEGAL_DONG.match(dong)
    if m:
        return m.group(1) + "동"
    return dong

# 경기 자치구 area code 앞 4자리 → 부모 시 매핑
# (apt2 area_codes.json 기반, schoolTrend.jsp 시도 페이지 링크 추출)
GG_PARENT_CITY = {
    "4111": "수원시",   # 장안/권선/팔달/영통
    "4113": "성남시",   # 수정/중원/분당
    "4117": "안양시",   # 만안/동안
    "4119": "부천시",   # 원미/소사/오정
    "4127": "안산시",   # 상록/단원
    "4128": "고양시",   # 덕양/일산동/일산서
    "4146": "용인시",   # 처인/기흥/수지
    "4159": "화성시",   # 만세/효행/병점/동탄
}


def parse_address(sido_short: str, sigu_apt2: str, address: str, area_code: str = "") -> tuple[str, str, str | None]:
    """주소 + apt2 시군구 + area code → (광역, catalog형식 시구, 동).

    catalog 시구 규칙:
      광역시: 시구_apt2 그대로 (강남구, 해운대구)
      경기 자치구: area code 앞 4자리로 부모 시 결정 → '<부모시> <자치구>'
        (apt2 학교 주소에 자치구가 명시 안 된 경우가 많아 area code 매핑이 안전)
      일반시: 시구_apt2 그대로 (광명시, 시흥시)
    동은 행정동→법정동 정규화 ("목5동" → "목동").
    """
    addr = (address or "").strip()
    m = DONG_PAT.search(addr)
    dong = normalize_dong(m.group(1)) if m else None

    if sido_short in METRO_SIDO:
        return (sido_short, sigu_apt2, dong)

    # 경기·도 — 자치구 보유 시 area code로 부모 시 결정
    if sigu_apt2.endswith("구") and len(str(area_code)) >= 4:
        prefix4 = str(area_code)[:4]
        parent = GG_PARENT_CITY.get(prefix4)
        if parent:
            return (sido_short, f"{parent} {sigu_apt2}", dong)
        # area code 매핑 누락 시 주소에서 시 추출 fallback
        m2 = re.search(r"([가-힣]+시)\s+", addr)
        if m2:
            return (sido_short, f"{m2.group(1)} {sigu_apt2}", dong)
        return (sido_short, sigu_apt2, dong)

    return (sido_short, sigu_apt2, dong)


def normalize_apt2(df: pd.DataFrame) -> pd.DataFrame:
    """광역 컬럼 정규화 + 시구·동 catalog 형식 부착."""
    df = df.copy()
    df["광역"] = df["광역"].astype(str)
    parts = df.apply(
        lambda r: parse_address(str(r.get("광역","")), str(r.get("시군구","")),
                                str(r.get("주소","")), str(r.get("area",""))),
        axis=1
    )
    df["_광역"] = [p[0] for p in parts]
    df["_시구"] = [p[1] for p in parts]
    df["_동"] = [p[2] for p in parts]
    df["_시"] = df["_시구"].str.split(" ").str[0]
    return df


# ── 집계 ──
def agg_grade(df: pd.DataFrame, level: str, prefix: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """성취도 (평균/A_pct/E_pct) 동·시구·시 집계."""
    cols = {
        "평균": "mean", "A_pct": "mean", "E_pct": "mean",
    }
    def _agg(g):
        return g.agg(
            **{f"{prefix}_학교수": ("학교명","count"),
               f"{prefix}_평균_avg": ("평균","mean"),
               f"{prefix}_평균_max": ("평균","max"),
               f"{prefix}_A_pct_avg": ("A_pct","mean"),
               f"{prefix}_A_pct_max": ("A_pct","max"),
               f"{prefix}_E_pct_avg": ("E_pct","mean")}
        ).reset_index()
    sub = df[df["학교급"] == level] if "학교급" in df.columns else df
    dong = _agg(sub.groupby(["_광역","_시구","_동"], dropna=False))
    sigu = _agg(sub.groupby(["_광역","_시구"], dropna=False))
    sigu.columns = [c.replace(prefix, f"시구_{prefix}") if c.startswith(prefix) else c for c in sigu.columns]
    si = _agg(sub.groupby(["_광역","_시"], dropna=False))
    si.columns = [c.replace(prefix, f"시_{prefix}") if c.startswith(prefix) else c for c in si.columns]
    return dong, sigu, si


def agg_trend(df: pd.DataFrame, level: str, prefix: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """5년추세 학교별 → 동·시구·시 집계."""
    sub = df[df["학교급"] == level].copy()
    # 추세 라벨 → 인디케이터
    sub["_연속상승"] = sub["원점수_3년추세"].astype(str).str.contains("연속", na=False).astype(int)
    sub["_반등"] = sub["원점수_3년추세"].astype(str).str.contains("반등", na=False).astype(int)
    sub["_원점수_2025"] = pd.to_numeric(sub["원점수_2025"], errors="coerce")
    sub["_5년평균"] = pd.to_numeric(sub["원점수_5년평균"], errors="coerce")
    sub["_전년대비"] = pd.to_numeric(sub["원점수_전년대비"], errors="coerce")

    def _agg(g):
        return g.agg(
            **{f"{prefix}_2025_avg": ("_원점수_2025","mean"),
               f"{prefix}_2025_max": ("_원점수_2025","max"),
               f"{prefix}_5년평균_avg": ("_5년평균","mean"),
               f"{prefix}_연속상승비율": ("_연속상승","mean"),
               f"{prefix}_반등비율": ("_반등","mean"),
               f"{prefix}_전년대비_avg": ("_전년대비","mean")}
        ).reset_index()
    dong = _agg(sub.groupby(["_광역","_시구","_동"], dropna=False))
    sigu = _agg(sub.groupby(["_광역","_시구"], dropna=False))
    sigu.columns = [c.replace(prefix, f"시구_{prefix}") if c.startswith(prefix) else c for c in sigu.columns]
    si = _agg(sub.groupby(["_광역","_시"], dropna=False))
    si.columns = [c.replace(prefix, f"시_{prefix}") if c.startswith(prefix) else c for c in si.columns]
    return dong, sigu, si


def agg_special(df: pd.DataFrame, prefix: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """특목고 진학 학교별 → 동·시구·시 집계."""
    sub = df.copy()
    sub["_특목비율"] = pd.to_numeric(sub["특목고비율_pct"], errors="coerce")
    sub["_특목계"] = pd.to_numeric(sub["특목고계"], errors="coerce")
    def _agg(g):
        return g.agg(
            **{f"{prefix}_비율_avg": ("_특목비율","mean"),
               f"{prefix}_비율_max": ("_특목비율","max"),
               f"{prefix}_계_avg": ("_특목계","mean")}
        ).reset_index()
    dong = _agg(sub.groupby(["_광역","_시구","_동"], dropna=False))
    sigu = _agg(sub.groupby(["_광역","_시구"], dropna=False))
    sigu.columns = [c.replace(prefix, f"시구_{prefix}") if c.startswith(prefix) else c for c in sigu.columns]
    si = _agg(sub.groupby(["_광역","_시"], dropna=False))
    si.columns = [c.replace(prefix, f"시_{prefix}") if c.startswith(prefix) else c for c in si.columns]
    return dong, sigu, si


# ── catalog 매칭 ──
def match(catalog: pd.DataFrame, dong: pd.DataFrame, sigu: pd.DataFrame, si: pd.DataFrame,
          prefix: str, sentinel_col: str) -> pd.DataFrame:
    """catalog(시구·동) + 3단 fallback. sentinel_col: 매칭 단계 판별용 컬럼명."""
    cat = catalog.copy()
    광역_map = {"서울":"서울","경기":"경기","부산":"부산","대구":"대구","인천":"인천",
              "광주":"광주","대전":"대전","울산":"울산","세종":"세종"}
    cat["_광역"] = cat["지역구분"].map(광역_map).fillna(cat["지역구분"])
    cat["_시"] = cat["시구"].str.split(" ").str[0]

    cat = cat.merge(dong, how="left", left_on=["_광역","시구","동"], right_on=["_광역","_시구","_동"])
    cat = cat.drop(columns=["_시구","_동"], errors="ignore")

    cat = cat.merge(sigu, how="left", left_on=["_광역","시구"], right_on=["_광역","_시구"])
    cat = cat.drop(columns=["_시구"], errors="ignore")

    cat = cat.merge(si, how="left", left_on=["_광역","_시"], right_on=["_광역","_시"])
    cat = cat.drop(columns=["_광역","_시"], errors="ignore")

    # 매칭 단계 표시
    sentinel_dong = sentinel_col
    sentinel_sigu = f"시구_{sentinel_col}"
    sentinel_si = f"시_{sentinel_col}"
    def lvl(r):
        if pd.notna(r.get(sentinel_dong)): return "동"
        if pd.notna(r.get(sentinel_sigu)): return "시구"
        if pd.notna(r.get(sentinel_si)): return "시"
        return "없음"
    cat[f"학군_매칭_{prefix}"] = cat.apply(lvl, axis=1)
    return cat


def main():
    print("apt2 4종 로드…")
    df_mg = pd.read_csv(DATA / "apt2_middle_grade.csv")
    df_hg = pd.read_csv(DATA / "apt2_high_grade.csv")
    df_tr = pd.read_csv(DATA / "apt2_school_trend.csv")
    df_sp = pd.read_csv(DATA / "apt2_middle_special.csv")
    print(f"  중성취 {len(df_mg):,} / 고성취 {len(df_hg):,} / 추세 {len(df_tr):,} / 특목 {len(df_sp):,}")

    print("주소 정규화…")
    df_mg = normalize_apt2(df_mg)
    df_hg = normalize_apt2(df_hg)
    df_tr = normalize_apt2(df_tr)
    df_sp = normalize_apt2(df_sp)

    print("동·시구·시 집계…")
    mg_d, mg_g, mg_s = agg_grade(df_mg, "중", "apt2_중성취")
    hg_d, hg_g, hg_s = agg_grade(df_hg, "고", "apt2_고성취")
    trm_d, trm_g, trm_s = agg_trend(df_tr, "중", "apt2_중추세")
    trh_d, trh_g, trh_s = agg_trend(df_tr, "고", "apt2_고추세")
    sp_d, sp_g, sp_s = agg_special(df_sp, "apt2_특목")

    print("catalog 로드…")
    cat = pd.read_csv(DATA / "catalog_with_school_scored.csv")
    n0 = len(cat)
    print(f"  단지 {n0:,}개")

    print("3단 fallback 매칭…")
    cat = match(cat, mg_d, mg_g, mg_s, "중성취", "apt2_중성취_학교수")
    cat = match(cat, hg_d, hg_g, hg_s, "고성취", "apt2_고성취_학교수")
    cat = match(cat, trm_d, trm_g, trm_s, "중추세", "apt2_중추세_2025_avg")
    cat = match(cat, trh_d, trh_g, trh_s, "고추세", "apt2_고추세_2025_avg")
    cat = match(cat, sp_d, sp_g, sp_s, "특목", "apt2_특목_비율_avg")

    # 최종 학군 컬럼 (동→시구→시 우선순위)
    def coalesce(*cols):
        out = cat[cols[0]].copy()
        for c in cols[1:]:
            out = out.fillna(cat[c])
        return out

    # Shrinkage 보정 — 동 매칭 학교 수 n이 작으면 시구 평균으로 끌어당김
    # blended = (n * 동평균 + k * 시구평균) / (n + k),  k=5 (shrinkage strength)
    # 동 매칭 안 된 경우 (n=NaN) → 시구 평균 그대로 (또는 시 fallback)
    K = 5
    def shrink(dong_col, sigu_col, si_col, n_dong_col, n_sigu_col):
        d = pd.to_numeric(cat[dong_col], errors="coerce")
        sg = pd.to_numeric(cat[sigu_col], errors="coerce")
        si = pd.to_numeric(cat[si_col], errors="coerce")
        n_d = pd.to_numeric(cat[n_dong_col], errors="coerce").fillna(0)
        # 동 매칭 있을 때만 shrinkage. 없으면 시구 → 시 fallback
        blended = (n_d * d.fillna(0) + K * sg.fillna(si)) / (n_d + K)
        # 둘 다 NaN인 경우 시 fallback
        blended = blended.where(blended.notna() & ((d.notna()) | (sg.notna())), si)
        return blended

    cat["apt2_중_평균"] = shrink("apt2_중성취_평균_avg","시구_apt2_중성취_평균_avg","시_apt2_중성취_평균_avg",
                                "apt2_중성취_학교수","시구_apt2_중성취_학교수")
    cat["apt2_중_A%"]  = shrink("apt2_중성취_A_pct_avg","시구_apt2_중성취_A_pct_avg","시_apt2_중성취_A_pct_avg",
                                "apt2_중성취_학교수","시구_apt2_중성취_학교수")
    cat["apt2_고_평균"] = shrink("apt2_고성취_평균_avg","시구_apt2_고성취_평균_avg","시_apt2_고성취_평균_avg",
                                "apt2_고성취_학교수","시구_apt2_고성취_학교수")
    cat["apt2_고_A%"]  = shrink("apt2_고성취_A_pct_avg","시구_apt2_고성취_A_pct_avg","시_apt2_고성취_A_pct_avg",
                                "apt2_고성취_학교수","시구_apt2_고성취_학교수")
    # 추세는 학교수 컬럼이 없으므로 일반 coalesce (학교당 평균이 이미 안정적)
    cat["apt2_중_2025"]      = coalesce("apt2_중추세_2025_avg","시구_apt2_중추세_2025_avg","시_apt2_중추세_2025_avg")
    cat["apt2_중_5년평균"]    = coalesce("apt2_중추세_5년평균_avg","시구_apt2_중추세_5년평균_avg","시_apt2_중추세_5년평균_avg")
    cat["apt2_중_연속상승비율"] = coalesce("apt2_중추세_연속상승비율","시구_apt2_중추세_연속상승비율","시_apt2_중추세_연속상승비율")
    cat["apt2_고_2025"]      = coalesce("apt2_고추세_2025_avg","시구_apt2_고추세_2025_avg","시_apt2_고추세_2025_avg")
    cat["apt2_고_5년평균"]    = coalesce("apt2_고추세_5년평균_avg","시구_apt2_고추세_5년평균_avg","시_apt2_고추세_5년평균_avg")
    cat["apt2_고_연속상승비율"] = coalesce("apt2_고추세_연속상승비율","시구_apt2_고추세_연속상승비율","시_apt2_고추세_연속상승비율")
    cat["apt2_중_반등비율"]    = coalesce("apt2_중추세_반등비율","시구_apt2_중추세_반등비율","시_apt2_중추세_반등비율")
    cat["apt2_고_반등비율"]    = coalesce("apt2_고추세_반등비율","시구_apt2_고추세_반등비율","시_apt2_고추세_반등비율")
    # 특목도 학교수 있으면 shrinkage
    cat["apt2_특목비율"]      = shrink("apt2_특목_비율_avg","시구_apt2_특목_비율_avg","시_apt2_특목_비율_avg",
                                       "apt2_중성취_학교수","시구_apt2_중성취_학교수")  # 학교수는 중성취 재사용
    # 동 매칭 학교 수 컬럼도 보존 (디버깅·신뢰도 표시용)
    cat["학군_동학교수"] = pd.to_numeric(cat["apt2_중성취_학교수"], errors="coerce").fillna(0).astype(int)
    cat["학군_시구학교수"] = pd.to_numeric(cat["시구_apt2_중성취_학교수"], errors="coerce").fillna(0).astype(int)

    # 정리: 상세 집계 컬럼은 제거하고 매칭/최종만 남김
    keep_prefix = ("apt2_중_","apt2_고_","apt2_특목비율","학군_매칭_","학군_동학교수","학군_시구학교수")
    drop_cols = [c for c in cat.columns
                 if (c.startswith("apt2_") or c.startswith("시구_apt2") or c.startswith("시_apt2"))
                 and not c.startswith(keep_prefix)]
    cat_final = cat.drop(columns=drop_cols)

    out = DATA / "catalog_apt2_school.csv"
    cat_final.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n저장: {out} ({len(cat_final):,}행 × {len(cat_final.columns)}컬럼)")

    print("\n── 매칭 단계 분포 ──")
    for col in ["학군_매칭_중성취","학군_매칭_고성취","학군_매칭_중추세","학군_매칭_고추세","학군_매칭_특목"]:
        if col in cat_final:
            print(f"  {col}: {dict(cat_final[col].value_counts())}")

    print("\n── 신규 컬럼 분포 (한강이남 catalog) ──")
    for col in ["apt2_중_평균","apt2_고_평균","apt2_중_2025","apt2_고_2025","apt2_중_연속상승비율","apt2_특목비율"]:
        if col in cat_final:
            s = pd.to_numeric(cat_final[col], errors="coerce")
            print(f"  {col}: n={s.notna().sum()}, mean={s.mean():.2f}, p50={s.median():.2f}, max={s.max():.2f}")


if __name__ == "__main__":
    main()
