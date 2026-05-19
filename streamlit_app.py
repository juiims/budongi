"""한강 이남 단지 입지 점수 웹 UI (Streamlit) — 인터랙티브 점수화.

기능:
  - 사이드바: 예산·지역·점수컷·상위N
  - 개인직장 역 선택 (수도권 741개 역 중)
  - 가중치 슬라이더 (서울/경기 각 요소)
  - 컷오프 슬라이더 (강남·지하철·개인직장 등)
  - 즉시 점수 재계산 (catalog raw 위에)
  - 단지별 점수 분해 (요소별 원점수·가중치·기여도·계산 근거)
  - Naver 단지 페이지 링크

실행: streamlit run streamlit_app.py
"""
import datetime
import math
import os
import subprocess
import sys

import pandas as pd
import streamlit as st

CATALOG_RAW = "data/candidates_hangang_south_catalog.csv"
SUBWAY = "data/subway_stations.csv"
NAVER_URL = "https://new.land.naver.com/complexes/{}"

st.set_page_config(page_title="한강 이남 입지 검색", page_icon="🏠", layout="wide")

CURRENT_YEAR = 2026
GANGNAM = (37.4979, 127.0276)
JOB_HUBS = {
    "판교": (37.3947, 127.1112),
    "분당(서현)": (37.3812, 127.1187),
    "과천": (37.4292, 126.9879),
    "광교중앙": (37.2861, 127.0566),
    "마곡": (37.5602, 126.8255),
}
SEOUL_DISTRICTS = {
    "강서구", "양천구", "영등포구", "구로구", "금천구", "동작구",
    "관악구", "서초구", "강남구", "송파구", "강동구",
}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def linear_score(v, cutoff):
    if v is None or pd.isna(v):
        return 0
    if v <= 0:
        return 100
    if v >= cutoff:
        return 0
    return round(100 * (1 - v / cutoff), 1)


def range_score(v, lo, hi, reverse=False):
    if v is None or pd.isna(v):
        return 0
    if reverse:
        if v <= lo: return 100
        if v >= hi: return 0
        return round(100 * (1 - (v - lo) / (hi - lo)), 1)
    if v <= lo: return 0
    if v >= hi: return 100
    return round(100 * (v - lo) / (hi - lo), 1)


def parse_year(s):
    try:
        return int(str(s)[:4])
    except (ValueError, TypeError):
        return None


@st.cache_data
def load_catalog(_key):
    df = pd.read_csv(CATALOG_RAW, encoding="utf-8-sig", dtype={"단지번호": str})
    for c in ["세대수", "최저매매가_만원", "최고매매가_만원", "위도", "경도",
              "강남까지_km", "회사2_남양_km"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["세대수"] = df["세대수"].fillna(0).astype(int)
    df = df.drop_duplicates(subset=["단지번호"]).reset_index(drop=True)
    df["지역구분"] = df["시구"].apply(lambda s: "서울" if s in SEOUL_DISTRICTS else "경기")

    # 자체일자리 거리 (좌표 기반, 고정)
    def hub_km(row):
        if pd.isna(row["위도"]) or pd.isna(row["경도"]):
            return None
        return min(haversine_km(row["위도"], row["경도"], h_lat, h_lon)
                   for h_lat, h_lon in JOB_HUBS.values())
    df["자체일자리_km"] = df.apply(hub_km, axis=1)
    return df


@st.cache_data
def load_subway(_key):
    df = pd.read_csv(SUBWAY, encoding="utf-8-sig")
    return df


@st.cache_data
def compute_nearest_subway(_key):
    catalog = load_catalog(_key)
    subway = load_subway(_key)
    sw_lats = subway["lat"].values
    sw_lngs = subway["lng"].values
    out = []
    for _, row in catalog.iterrows():
        lat, lon = row["위도"], row["경도"]
        if pd.isna(lat) or pd.isna(lon):
            out.append(None); continue
        dists = [haversine_km(lat, lon, sl, sg) for sl, sg in zip(sw_lats, sw_lngs)]
        out.append(round(min(dists), 3))
    return out


def compute_personal_km(catalog, p_lat, p_lng):
    """단지별 사용자 선택 역까지 거리."""
    out = []
    for _, row in catalog.iterrows():
        lat, lon = row["위도"], row["경도"]
        if pd.isna(lat) or pd.isna(lon):
            out.append(None); continue
        out.append(round(haversine_km(lat, lon, p_lat, p_lng), 2))
    return out


def score_dataframe(df, weights_seoul, weights_gg, cuts):
    """가중치·컷오프 받아 점수 부여."""
    def f_job(row):
        cut = cuts["seoul_gangnam"] if row["지역구분"] == "서울" else cuts["gyeonggi_gangnam"]
        return linear_score(row["강남까지_km"], cut)

    def f_jache(row):
        return linear_score(row["자체일자리_km"], cuts["job_hub"]) if row["지역구분"] == "경기" else 0

    def f_env(row):
        year = parse_year(row["준공년월"])
        age = CURRENT_YEAR - year if year else None
        hh_s = range_score(row["세대수"], cuts["env_hh_min"], cuts["env_hh_max"])
        age_s = range_score(age, cuts["env_age_min"], cuts["env_age_max"], reverse=True) if age is not None else 0
        return round(hh_s * 0.5 + age_s * 0.5, 1)

    df["s_job"] = df.apply(f_job, axis=1)
    df["s_jache"] = df.apply(f_jache, axis=1)
    df["s_transit"] = df["가까운지하철_km"].apply(lambda v: linear_score(v, cuts["subway"]))
    df["s_env"] = df.apply(f_env, axis=1)
    df["s_personal"] = df["개인직장_km"].apply(lambda v: linear_score(v, cuts["personal"]))

    def total(row):
        if row["지역구분"] == "서울":
            w = weights_seoul
            factors = {"직장": row["s_job"], "교통": row["s_transit"],
                       "환경": row["s_env"], "개인직장": row["s_personal"]}
        else:
            w = weights_gg
            factors = {"서울접근성": row["s_job"], "자체일자리": row["s_jache"],
                       "교통": row["s_transit"], "환경": row["s_env"],
                       "개인직장": row["s_personal"]}
        total_w = sum(w.values())
        if total_w == 0:
            return 0
        return round(sum(factors[k] * w[k] for k in w) / total_w, 1)

    df["입지점수"] = df.apply(total, axis=1)
    return df


# ============================================================
# 데이터 로딩
# ============================================================
st.title("🏠 한강 이남 단지 입지 점수 검색")

if not os.path.exists(CATALOG_RAW) or not os.path.exists(SUBWAY):
    st.error(f"필수 파일 없음: {CATALOG_RAW} 또는 {SUBWAY}")
    st.stop()

mtime = datetime.datetime.fromtimestamp(os.path.getmtime(CATALOG_RAW))
mtime_key = mtime.isoformat()
catalog = load_catalog(mtime_key).copy()
subway = load_subway(mtime_key)
catalog["가까운지하철_km"] = compute_nearest_subway(mtime_key)

# ============================================================
# 사이드바
# ============================================================
with st.sidebar:
    st.header("🔎 검색 옵션")
    budget = st.number_input("예산 (만원)", 10000, 300000, 80000, step=1000)
    rng = st.slider("범위 ± (만원)", 1000, 30000, 5000, step=1000)
    region = st.radio("지역", ["전체", "서울", "경기"], horizontal=True)
    min_score = st.slider("최소 입지점수", 0, 80, 0)
    top_n = st.slider("상위 N개", 5, 200, 30)

    st.divider()
    st.header("🚉 개인직장 (출근지)")
    all_lines = sorted(subway["line_no"].astype(str).unique())
    line_filter = st.multiselect("노선 필터 (선택, 비우면 전체)", all_lines, default=[])
    sub_sw = subway[subway["line_no"].astype(str).isin(line_filter)] if line_filter else subway
    station_options = sorted(sub_sw["station_name"].unique())
    default_idx = station_options.index("합정") if "합정" in station_options else 0
    station_name = st.selectbox("역 선택", station_options, index=default_idx,
                                help="단지에서 이 역까지 직선거리로 개인직장 점수 산출")
    matched = sub_sw[sub_sw["station_name"] == station_name]
    p_lat = float(matched.iloc[0]["lat"])
    p_lng = float(matched.iloc[0]["lng"])
    p_lines = ", ".join(matched["line_no"].astype(str).unique())
    st.caption(f"📍 **{station_name}**역 ({p_lines}) — lat={p_lat:.4f}, lng={p_lng:.4f}")

    st.divider()
    st.header("⚖️ 가중치")
    with st.expander("서울 단지 (합 100 권장)", expanded=False):
        w_s_job = st.slider("직장(강남)", 0, 100, 40, key="ws_job")
        w_s_transit = st.slider("교통(지하철)", 0, 100, 25, key="ws_transit")
        w_s_env = st.slider("환경(세대·신축)", 0, 100, 15, key="ws_env")
        w_s_personal = st.slider("개인직장", 0, 100, 20, key="ws_personal")
        st.caption(f"합계: {w_s_job + w_s_transit + w_s_env + w_s_personal}")
    with st.expander("경기 단지 (합 100 권장)", expanded=False):
        w_g_seoul = st.slider("서울접근성(강남)", 0, 100, 25, key="wg_seoul")
        w_g_jache = st.slider("자체일자리", 0, 100, 20, key="wg_jache")
        w_g_transit = st.slider("교통(지하철)", 0, 100, 15, key="wg_transit")
        w_g_env = st.slider("환경(세대·신축)", 0, 100, 15, key="wg_env")
        w_g_personal = st.slider("개인직장", 0, 100, 25, key="wg_personal")
        st.caption(f"합계: {w_g_seoul + w_g_jache + w_g_transit + w_g_env + w_g_personal}")

    st.header("📏 컷오프 (0점 되는 거리·기준)")
    with st.expander("거리 컷오프 (km)", expanded=False):
        st.caption("0km=100점, cutoff=0점, 그 사이 선형")
        c_seoul_gn = st.slider("강남 (서울)", 5.0, 30.0, 15.0, step=0.5)
        c_gg_gn = st.slider("강남 (경기)", 10.0, 50.0, 30.0, step=1.0)
        c_hub = st.slider("자체일자리 거점", 3.0, 20.0, 10.0, step=0.5)
        c_subway = st.slider("지하철역", 0.5, 5.0, 1.5, step=0.1)
        c_personal = st.slider("개인직장(선택역)", 3.0, 30.0, 12.0, step=0.5)
    with st.expander("환경 점수 기준", expanded=False):
        st.caption("세대수·연식 각각 선형으로 0-100 산출 후 평균")
        c_env_hh_min = st.number_input("세대 0점", 100, 1000, 300, step=100)
        c_env_hh_max = st.number_input("세대 만점", 500, 5000, 1500, step=100)
        c_env_age_min = st.number_input("연식 만점 (년)", 0, 30, 5, step=1)
        c_env_age_max = st.number_input("연식 0점 (년)", 10, 60, 30, step=1)

    st.divider()
    st.caption(f"📅 데이터: {mtime:%Y-%m-%d %H:%M}")
    is_today = mtime.date() == datetime.date.today()
    st.caption("✅ 당일 데이터" if is_today else "⚠️ 어제 이전 데이터")
    if st.button("🔄 catalog 재빌드 (25-30분)", width="stretch"):
        with st.spinner("재빌드 중... 콘솔 출력 확인"):
            try:
                env = os.environ.copy()
                env["SCREEN_GYEONGGI"] = "1"
                env["SCREEN_NO_PRICE_FILTER"] = "1"
                subprocess.run([sys.executable, "screen_candidates.py"], env=env, check=True)
                st.success("재빌드 완료")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"재빌드 실패: {e}")

# ============================================================
# 점수 계산
# ============================================================
weights_seoul = {"직장": w_s_job, "교통": w_s_transit,
                 "환경": w_s_env, "개인직장": w_s_personal}
weights_gg = {"서울접근성": w_g_seoul, "자체일자리": w_g_jache,
              "교통": w_g_transit, "환경": w_g_env, "개인직장": w_g_personal}
cuts = {
    "seoul_gangnam": c_seoul_gn, "gyeonggi_gangnam": c_gg_gn,
    "job_hub": c_hub, "subway": c_subway, "personal": c_personal,
    "env_hh_min": c_env_hh_min, "env_hh_max": c_env_hh_max,
    "env_age_min": c_env_age_min, "env_age_max": c_env_age_max,
}

# 개인직장 거리 (사용자 선택 역 기반 매번 재계산)
catalog["개인직장_km"] = compute_personal_km(catalog, p_lat, p_lng)
scored = score_dataframe(catalog, weights_seoul, weights_gg, cuts)

# ============================================================
# 필터링
# ============================================================
bmin = budget - rng
bmax = budget + rng
mask = (scored["최고매매가_만원"] >= bmin) & (scored["최저매매가_만원"] <= bmax)
mask &= scored["입지점수"] >= min_score
if region != "전체":
    mask &= scored["지역구분"] == region

filtered = scored[mask].sort_values("입지점수", ascending=False).head(top_n)

# ============================================================
# 메트릭
# ============================================================
col1, col2, col3, col4 = st.columns(4)
col1.metric("예산 범위", f"{bmin:,} ~ {bmax:,}")
col2.metric("매칭 단지", f"{len(scored[mask])}개", f"표시: 상위 {len(filtered)}")
col3.metric("개인직장", f"{station_name}역")
col4.metric("평균 점수",
            f"{filtered['입지점수'].mean():.1f}" if len(filtered) else "—")

# ============================================================
# 산정 공식 안내
# ============================================================
with st.expander("📐 점수 산정 공식 (현재 적용 중)", expanded=False):
    st.markdown("""
**거리 기반 점수**:  `점수 = 100 × max(0, 1 − 거리 / 컷오프)`  → 0km=100점, 컷오프 이상=0점

**환경 점수**:  `점수 = 0.5 × 세대수점수 + 0.5 × 신축점수`  (각 선형 0-100)

**최종 입지점수**:  `Σ(요소점수 × 가중치) ÷ Σ가중치`  → 0-100
""")
    col_a, col_b = st.columns(2)
    with col_a:
        st.write("**서울 가중치**")
        st.json(weights_seoul)
        st.write(f"합: {sum(weights_seoul.values())}")
        st.write("**경기 가중치**")
        st.json(weights_gg)
        st.write(f"합: {sum(weights_gg.values())}")
    with col_b:
        st.write("**거리 컷오프 (km)**")
        st.json({
            "강남 서울": c_seoul_gn, "강남 경기": c_gg_gn,
            "자체일자리": c_hub, "지하철": c_subway,
            "개인직장(선택역)": c_personal,
        })
        st.write("**환경 기준**")
        st.json({
            "세대수": f"{c_env_hh_min}-{c_env_hh_max}",
            "연식(년)": f"{c_env_age_min}-{c_env_age_max}",
        })

# ============================================================
# 결과 표
# ============================================================
if filtered.empty:
    st.warning("매칭 단지 없음 — 예산·점수 조건 완화 권장")
else:
    show = filtered.copy()
    show["Naver"] = show["단지번호"].apply(lambda c: NAVER_URL.format(c))

    DISPLAY = ["입지점수", "지역구분", "시구", "동", "단지명",
               "최저매매가_만원", "최고매매가_만원", "세대수", "준공년월",
               "강남까지_km", "개인직장_km", "가까운지하철_km",
               "자체일자리_km", "회사2_남양_km", "Naver"]
    DISPLAY = [c for c in DISPLAY if c in show.columns]

    st.dataframe(
        show[DISPLAY].reset_index(drop=True),
        width="stretch",
        column_config={
            "Naver": st.column_config.LinkColumn("Naver", display_text="🔗 보기"),
            "입지점수": st.column_config.NumberColumn("점수", format="%.1f"),
            "최저매매가_만원": st.column_config.NumberColumn("최저(만원)", format="%d"),
            "최고매매가_만원": st.column_config.NumberColumn("최고(만원)", format="%d"),
            "강남까지_km": st.column_config.NumberColumn("강남km", format="%.2f"),
            "개인직장_km": st.column_config.NumberColumn(f"{station_name}km", format="%.2f"),
            "회사2_남양_km": st.column_config.NumberColumn("남양km", format="%.2f"),
            "가까운지하철_km": st.column_config.NumberColumn("지하철km", format="%.2f"),
            "자체일자리_km": st.column_config.NumberColumn("자체일자리km", format="%.2f"),
            "세대수": st.column_config.NumberColumn("세대", format="%d"),
        },
        hide_index=True,
        height=500,
    )

    csv = show[DISPLAY].to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 CSV 다운로드", csv,
        file_name=f"budget_{budget}_top{top_n}_{station_name}_{datetime.date.today()}.csv",
        mime="text/csv",
    )

    # ============================================================
    # 단지별 점수 분해
    # ============================================================
    st.divider()
    st.subheader("🔍 단지별 점수 분해")
    options = filtered.apply(
        lambda r: f"{r['입지점수']:.1f} | {r['단지명']} ({r['시구']} {r['동']})",
        axis=1,
    ).tolist()
    selected_label = st.selectbox("단지 선택 (상위 결과)", options)
    if selected_label:
        idx = options.index(selected_label)
        row = filtered.iloc[idx]
        region_ = row["지역구분"]
        weights = weights_seoul if region_ == "서울" else weights_gg

        st.markdown(f"### {row['단지명']}  ({region_} {row['시구']} {row['동']})")
        st.caption(
            f"세대 {row['세대수']:,} · 준공 {row['준공년월']} · "
            f"가격 {row['최저매매가_만원']:,.0f}~{row['최고매매가_만원']:,.0f}만원 · "
            f"입지점수 **{row['입지점수']:.1f}**"
        )

        if region_ == "서울":
            factors = [
                ("직장", row["s_job"], weights["직장"],
                 f"강남 {row['강남까지_km']:.2f}km / cut {c_seoul_gn}km"),
                ("교통", row["s_transit"], weights["교통"],
                 f"지하철 {row['가까운지하철_km']:.2f}km / cut {c_subway}km"),
                ("환경", row["s_env"], weights["환경"],
                 f"세대 {row['세대수']:,} / 준공 {row['준공년월']}"),
                ("개인직장", row["s_personal"], weights["개인직장"],
                 f"{station_name} {row['개인직장_km']:.2f}km / cut {c_personal}km"),
            ]
        else:
            factors = [
                ("서울접근성", row["s_job"], weights["서울접근성"],
                 f"강남 {row['강남까지_km']:.2f}km / cut {c_gg_gn}km"),
                ("자체일자리", row["s_jache"], weights["자체일자리"],
                 f"거점 {row['자체일자리_km']:.2f}km / cut {c_hub}km"),
                ("교통", row["s_transit"], weights["교통"],
                 f"지하철 {row['가까운지하철_km']:.2f}km / cut {c_subway}km"),
                ("환경", row["s_env"], weights["환경"],
                 f"세대 {row['세대수']:,} / 준공 {row['준공년월']}"),
                ("개인직장", row["s_personal"], weights["개인직장"],
                 f"{station_name} {row['개인직장_km']:.2f}km / cut {c_personal}km"),
            ]

        total_w = sum(w for _, _, w, _ in factors)
        breakdown = pd.DataFrame([
            {
                "요소": name,
                "원점수": s,
                "가중치": w,
                "기여도": round(s * w / total_w, 1) if total_w else 0,
                "계산 근거": detail,
            }
            for name, s, w, detail in factors
        ])
        st.dataframe(breakdown, hide_index=True, width="stretch")
        st.markdown(
            f"**최종 입지점수 {row['입지점수']:.1f}** "
            f"= Σ(원점수 × 가중치) ÷ {total_w} (가중치 합)"
        )

# ============================================================
st.divider()
st.caption("💡 사이드바 옵션 변경 시 점수 즉시 재계산 · "
           "표 헤더 클릭 정렬 · 🔗 Naver 페이지 실시간 매물 · "
           "추천 가격은 catalog 스냅샷이며 실시간 호가는 Naver에서 확인")
