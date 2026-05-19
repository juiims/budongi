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
SUBWAY_ENRICH = "data/catalog_subway.csv"
RTMS_ENRICH = "data/catalog_with_rtms.csv"
SUPPLY_ENRICH = "data/catalog_with_supply.csv"
DISTRICT_SUPPLY = "data/catalog_with_district_supply.csv"
SCHOOL_ENRICH = "data/catalog_apt2_school_scored.csv"
JEONSE_ENRICH = "data/catalog_with_jeonse.csv"
NAVER_URL = "https://new.land.naver.com/complexes/{}"

st.set_page_config(page_title="한강 이남 입지 검색", page_icon="🏠", layout="wide")

# ============================================================
# Custom Theme — Trendy Blue
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Pretendard:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp, [data-testid="stSidebar"] {
    font-family: 'Pretendard', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

.stApp {
    background: linear-gradient(180deg, #EFF6FF 0%, #F8FAFC 280px) !important;
}

/* Hero header */
.hero {
    background: linear-gradient(135deg, #1D4ED8 0%, #2563EB 45%, #3B82F6 100%);
    border-radius: 20px;
    padding: 28px 32px;
    color: white;
    box-shadow: 0 20px 40px -20px rgba(37, 99, 235, 0.55);
    margin-bottom: 24px;
}
.hero h1 {
    font-size: 30px !important;
    font-weight: 800 !important;
    margin: 0 !important;
    letter-spacing: -0.02em;
    color: white !important;
}
.hero p {
    font-size: 14px;
    margin: 6px 0 0 0;
    opacity: 0.9;
}
.hero .badge {
    display: inline-block;
    background: rgba(255,255,255,0.18);
    backdrop-filter: blur(6px);
    border: 1px solid rgba(255,255,255,0.28);
    color: white;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 999px;
    margin-bottom: 10px;
    letter-spacing: 0.08em;
}

/* Hide default Streamlit title margin */
.main .block-container { padding-top: 1.5rem; }

/* Metric cards */
[data-testid="stMetric"] {
    background: white;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    transition: all 0.2s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 24px -12px rgba(37, 99, 235, 0.25);
    border-color: #BFDBFE;
}
[data-testid="stMetricLabel"] {
    font-size: 12px !important;
    font-weight: 600 !important;
    color: #64748B !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] {
    font-size: 22px !important;
    font-weight: 800 !important;
    color: #1E3A8A !important;
}
[data-testid="stMetricDelta"] {
    font-size: 12px !important;
    color: #2563EB !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FFFFFF 0%, #F1F5F9 100%) !important;
    border-right: 1px solid #E2E8F0;
}
[data-testid="stSidebar"] h2 {
    font-size: 14px !important;
    font-weight: 700 !important;
    color: #1E3A8A !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-top: 8px !important;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
    color: white;
    border: none;
    border-radius: 10px;
    font-weight: 600;
    padding: 10px 18px;
    box-shadow: 0 4px 12px -2px rgba(37, 99, 235, 0.35);
    transition: all 0.2s ease;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 20px -4px rgba(37, 99, 235, 0.45);
    color: white;
}
.stDownloadButton > button {
    background: white;
    color: #2563EB;
    border: 1.5px solid #BFDBFE;
    border-radius: 10px;
    font-weight: 600;
}
.stDownloadButton > button:hover {
    background: #EFF6FF;
    color: #1D4ED8;
    border-color: #2563EB;
}

/* Inputs */
.stTextInput input, .stNumberInput input, .stSelectbox > div > div {
    border-radius: 10px !important;
    border-color: #E2E8F0 !important;
}
.stTextInput input:focus, .stNumberInput input:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12) !important;
}

/* Slider track */
.stSlider [data-baseweb="slider"] > div > div > div {
    background: linear-gradient(90deg, #3B82F6, #1D4ED8) !important;
}

/* Expander */
[data-testid="stExpander"] {
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    background: white !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    color: #1E3A8A !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #E2E8F0;
    box-shadow: 0 4px 12px -4px rgba(15, 23, 42, 0.06);
}

/* Divider */
hr {
    border-color: #E2E8F0 !important;
    margin: 1.5rem 0 !important;
}

/* Headings */
h1, h2, h3 {
    color: #0F172A !important;
    letter-spacing: -0.01em !important;
}
h3 { color: #1E3A8A !important; font-weight: 700 !important; }

/* Alert/info boxes */
.stAlert {
    border-radius: 12px !important;
    border: none !important;
}

/* Caption */
[data-testid="stCaption"] {
    color: #64748B !important;
    font-size: 12px !important;
}

/* Tabs / Radio */
.stRadio > div { gap: 8px; }
.stRadio label {
    background: white;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 6px 14px !important;
    transition: all 0.15s ease;
}
.stRadio label:has(input:checked) {
    background: #EFF6FF;
    border-color: #2563EB;
    color: #1D4ED8;
    font-weight: 600;
}

/* JSON viewer */
[data-testid="stJson"] {
    background: #F8FAFC !important;
    border-radius: 10px !important;
    border: 1px solid #E2E8F0 !important;
}
</style>
""", unsafe_allow_html=True)

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

    # 가까운 지하철역 enrich 병합 (pre-computed)
    if os.path.exists(SUBWAY_ENRICH):
        enrich = pd.read_csv(SUBWAY_ENRICH, encoding="utf-8-sig", dtype={"단지번호": str})
        df = df.merge(enrich, on="단지번호", how="left")
        df["가까운지하철_km"] = df["가까운역_km"]

    # RTMS 가격 지표 enrich (pre-computed)
    if os.path.exists(RTMS_ENRICH):
        rtms = pd.read_csv(RTMS_ENRICH, encoding="utf-8-sig", dtype={"단지번호": str})
        rtms_cols = ["단지번호", "매칭_방식", "전고점_만원", "전고점_거래일",
                     "전저점_만원", "전저점_거래일", "직전거래_만원", "직전거래_거래일",
                     "첫거래_만원", "첫거래_거래일", "첫거래대비_pct",
                     "회복률_pct", "메인평형_㎡", "메인평형_회복률_pct",
                     "메인평형_거래수", "최근6개월_거래수", "최근12개월_거래수",
                     "매칭_거래수", "RTMS_신뢰도", "RTMS_자치구"]
        rtms_cols = [c for c in rtms_cols if c in rtms.columns]
        df = df.merge(rtms[rtms_cols], on="단지번호", how="left")

        # 시구 자동 재분류 — RTMS sggCd가 다른 시 단지면 catalog 분류 오류로 보고 덮어쓰기
        # (동탄구 같이 시 prefix 일치하면 catalog 자치구 정보 유지)
        def _prefix(s):
            return str(s).split()[0] if pd.notna(s) else None

        df["시구_원본"] = df["시구"]
        mismatch = (
            df["RTMS_자치구"].notna()
            & (df["시구"].apply(_prefix) != df["RTMS_자치구"].apply(_prefix))
        )
        df.loc[mismatch, "시구"] = df.loc[mismatch, "RTMS_자치구"]
        df["지역구분"] = df["시구"].apply(lambda s: "서울" if s in SEOUL_DISTRICTS else "경기")

    # 분양가 enrich (청약홈 데이터, 2020~2025 분양 단지)
    if os.path.exists(SUPPLY_ENRICH):
        sup = pd.read_csv(SUPPLY_ENRICH, encoding="utf-8-sig", dtype={"단지번호": str})
        sup_cols = ["단지번호", "분양가_만원", "분양가매칭_방식", "모집공고일", "분양가대비_pct"]
        sup_cols = [c for c in sup_cols if c in sup.columns]
        df = df.merge(sup[sup_cols], on="단지번호", how="left")

    # 자치구 수급 신호 (RTMS derive)
    if os.path.exists(DISTRICT_SUPPLY):
        ds = pd.read_csv(DISTRICT_SUPPLY, encoding="utf-8-sig", dtype={"단지번호": str})
        ds_cols = ["단지번호", "자치구_거래활성도", "자치구_가격모멘텀",
                   "자치구_신축비율", "자치구_수급점수"]
        ds_cols = [c for c in ds_cols if c in ds.columns]
        df = df.merge(ds[ds_cols], on="단지번호", how="left")

    # 학군 enrich (apt2 + [필디] 통합, v2 점수)
    if os.path.exists(SCHOOL_ENRICH):
        sch = pd.read_csv(SCHOOL_ENRICH, encoding="utf-8-sig", dtype={"단지번호": str})
        sch_cols = ["단지번호", "점수_학군", "점수_학군_v2",
                    "학군_성취율", "학군_특목고",
                    "apt2_중_평균", "apt2_중_A%", "apt2_고_평균", "apt2_고_A%",
                    "apt2_특목비율", "학군_매칭"]
        sch_cols = [c for c in sch_cols if c in sch.columns]
        df = df.merge(sch[sch_cols], on="단지번호", how="left")

    # 자치구 전세가율 enrich (RTMS 전월세 derive)
    if os.path.exists(JEONSE_ENRICH):
        jn = pd.read_csv(JEONSE_ENRICH, encoding="utf-8-sig", dtype={"단지번호": str})
        jn_cols = ["단지번호", "자치구_전세가율_84㎡", "자치구_전세가율_전체",
                   "자치구_월세비중_pct", "자치구_전세거래수_12M"]
        jn_cols = [c for c in jn_cols if c in jn.columns]
        df = df.merge(jn[jn_cols], on="단지번호", how="left")
    return df


@st.cache_data
def load_subway(_key):
    df = pd.read_csv(SUBWAY, encoding="utf-8-sig")
    return df


def compute_personal_km(catalog, p_lat, p_lng):
    """단지별 사용자 선택 역까지 거리."""
    out = []
    for _, row in catalog.iterrows():
        lat, lon = row["위도"], row["경도"]
        if pd.isna(lat) or pd.isna(lon):
            out.append(None); continue
        out.append(round(haversine_km(lat, lon, p_lat, p_lng), 2))
    return out


PYEONG_PER_SQM = 1 / 3.305785


def sqm_to_pyeong(v):
    if v is None or pd.isna(v):
        return None
    return round(float(v) * PYEONG_PER_SQM, 1)


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
    df["s_me"] = df["본인직장_km"].apply(lambda v: linear_score(v, cuts["me"]))
    df["s_spouse"] = df["배우자직장_km"].apply(lambda v: linear_score(v, cuts["spouse"]))
    # 학군 점수 (catalog_apt2_school_scored.csv 에서 점수_학군_v2 또는 점수_학군)
    if "점수_학군_v2" in df.columns:
        df["s_school"] = pd.to_numeric(df["점수_학군_v2"], errors="coerce").fillna(0)
    elif "점수_학군" in df.columns:
        df["s_school"] = pd.to_numeric(df["점수_학군"], errors="coerce").fillna(0)
    else:
        df["s_school"] = 0

    def total(row):
        if row["지역구분"] == "서울":
            w = weights_seoul
            factors = {"직장": row["s_job"], "교통": row["s_transit"],
                       "환경": row["s_env"], "학군": row["s_school"],
                       "본인직장": row["s_me"], "배우자직장": row["s_spouse"]}
        else:
            w = weights_gg
            factors = {"서울접근성": row["s_job"], "자체일자리": row["s_jache"],
                       "교통": row["s_transit"], "환경": row["s_env"],
                       "학군": row["s_school"],
                       "본인직장": row["s_me"], "배우자직장": row["s_spouse"]}
        total_w = sum(w.values())
        if total_w == 0:
            return 0
        return round(sum(factors[k] * w[k] for k in w) / total_w, 1)

    df["입지점수"] = df.apply(total, axis=1)
    return df


# ============================================================
# 데이터 로딩
# ============================================================
st.markdown("""
<div class="hero">
    <span class="badge">PHASE 1 · MVP</span>
    <h1>한강 이남 입지 점수 검색</h1>
    <p>예산을 입력하면 직장·교통·환경·개인동선까지 반영한 입지 점수로 단지를 정렬합니다.</p>
</div>
""", unsafe_allow_html=True)

if not os.path.exists(CATALOG_RAW) or not os.path.exists(SUBWAY):
    st.error(f"필수 파일 없음: {CATALOG_RAW} 또는 {SUBWAY}")
    st.stop()

mtime = datetime.datetime.fromtimestamp(os.path.getmtime(CATALOG_RAW))
mtime_key = mtime.isoformat()
catalog = load_catalog(mtime_key).copy()
subway = load_subway(mtime_key)
if "가까운지하철_km" not in catalog.columns:
    st.warning(f"⚠ {SUBWAY_ENRICH} 없음 — `python enrich_with_subway.py` 먼저 실행하세요.")
    st.stop()

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
    st.header("💳 DSR 매수 가능 가격")
    st.caption("2026년 스트레스 DSR 3단계 룰 기반 — 실제 살 수 있는 가격대 자동 계산")
    annual_income = st.number_input("연소득 (만원)", 0, 50000, 10000, step=500,
                                     help="세전. 부부 합산은 0 입력 또는 합계로")
    existing_debt = st.number_input("기존 대출 잔액 (만원)", 0, 200000, 0, step=1000)
    cash_down = st.number_input("자기자본(현금/전세보증금 등, 만원)", 0, 200000, 30000, step=1000)
    dsr_limit = st.slider("DSR 한도 (%)", 30, 50, 40, help="규제 DSR 40% (2금융권 50%)")
    loan_term_yr = st.slider("대출 기간 (년)", 10, 50, 30)
    apply_dsr_filter = st.checkbox("DSR 통과 단지만 표시", value=False)

    st.divider()
    st.header("🚉 출근지 (본인 / 배우자)")
    all_stations = sorted(subway["station_name"].unique())

    def _pick_station(label, default_name, key):
        all_lines = sorted(subway["line_no"].astype(str).unique())
        lines = st.multiselect(f"{label} — 노선 필터 (선택)", all_lines, default=[], key=f"{key}_lines")
        sub_sw = subway[subway["line_no"].astype(str).isin(lines)] if lines else subway
        opts = sorted(sub_sw["station_name"].unique())
        idx = opts.index(default_name) if default_name in opts else 0
        name = st.selectbox(f"{label} — 역 선택", opts, index=idx, key=f"{key}_station")
        matched = sub_sw[sub_sw["station_name"] == name].iloc[0]
        lat, lng = float(matched["lat"]), float(matched["lng"])
        line_str = ", ".join(sub_sw[sub_sw["station_name"] == name]["line_no"].astype(str).unique())
        st.caption(f"📍 **{name}**역 ({line_str}) — {lat:.4f}, {lng:.4f}")
        return name, lat, lng

    with st.expander("🙋 본인 직장", expanded=True):
        me_name, me_lat, me_lng = _pick_station("본인", "합정", "me")
    with st.expander("💑 배우자 직장", expanded=True):
        sp_name, sp_lat, sp_lng = _pick_station("배우자", "강남", "spouse")

    st.divider()
    st.header("⚖️ 가중치")
    with st.expander("서울 단지 (합 100 권장)", expanded=False):
        w_s_job = st.slider("직장(강남)", 0, 100, 30, key="ws_job")
        w_s_transit = st.slider("교통(지하철)", 0, 100, 20, key="ws_transit")
        w_s_env = st.slider("환경(세대·신축)", 0, 100, 15, key="ws_env")
        w_s_school = st.slider("학군", 0, 100, 15, key="ws_school")
        w_s_me = st.slider("본인 출근지", 0, 100, 10, key="ws_me")
        w_s_spouse = st.slider("배우자 출근지", 0, 100, 10, key="ws_spouse")
        st.caption(f"합계: {w_s_job + w_s_transit + w_s_env + w_s_school + w_s_me + w_s_spouse}")
    with st.expander("경기 단지 (합 100 권장)", expanded=False):
        w_g_seoul = st.slider("서울접근성(강남)", 0, 100, 20, key="wg_seoul")
        w_g_jache = st.slider("자체일자리", 0, 100, 15, key="wg_jache")
        w_g_transit = st.slider("교통(지하철)", 0, 100, 15, key="wg_transit")
        w_g_env = st.slider("환경(세대·신축)", 0, 100, 13, key="wg_env")
        w_g_school = st.slider("학군", 0, 100, 12, key="wg_school")
        w_g_me = st.slider("본인 출근지", 0, 100, 12, key="wg_me")
        w_g_spouse = st.slider("배우자 출근지", 0, 100, 13, key="wg_spouse")
        st.caption(f"합계: {w_g_seoul + w_g_jache + w_g_transit + w_g_env + w_g_school + w_g_me + w_g_spouse}")

    st.header("📏 컷오프 (0점 되는 거리·기준)")
    with st.expander("거리 컷오프 (km)", expanded=False):
        st.caption("0km=100점, cutoff=0점, 그 사이 선형")
        c_seoul_gn = st.slider("강남 (서울)", 5.0, 30.0, 15.0, step=0.5)
        c_gg_gn = st.slider("강남 (경기)", 10.0, 50.0, 30.0, step=1.0)
        c_hub = st.slider("자체일자리 거점", 3.0, 20.0, 10.0, step=0.5)
        c_subway = st.slider("지하철역", 0.5, 5.0, 1.5, step=0.1)
        c_me = st.slider("본인 출근지", 3.0, 30.0, 12.0, step=0.5)
        c_spouse = st.slider("배우자 출근지", 3.0, 30.0, 12.0, step=0.5)
    with st.expander("환경 점수 기준", expanded=False):
        st.caption("세대수·연식 각각 선형으로 0-100 산출 후 평균")
        c_env_hh_min = st.number_input("세대 0점", 100, 1000, 300, step=100)
        c_env_hh_max = st.number_input("세대 만점", 500, 5000, 1500, step=100)
        c_env_age_min = st.number_input("연식 만점 (년)", 0, 30, 5, step=1)
        c_env_age_max = st.number_input("연식 0점 (년)", 10, 60, 30, step=1)

    st.divider()
    st.header("📊 결과 표 컬럼")
    column_groups = st.multiselect(
        "표시할 컬럼 그룹",
        options=["가격 시계열", "분양가", "수급(자치구)", "학군", "거리·교통", "평형·메타"],
        default=["가격 시계열", "거리·교통"],
        help="기본 컬럼(점수·단지명·가격) 외에 보고 싶은 그룹만 선택",
    )

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
weights_seoul = {"직장": w_s_job, "교통": w_s_transit, "환경": w_s_env,
                 "학군": w_s_school,
                 "본인직장": w_s_me, "배우자직장": w_s_spouse}
weights_gg = {"서울접근성": w_g_seoul, "자체일자리": w_g_jache,
              "교통": w_g_transit, "환경": w_g_env,
              "학군": w_g_school,
              "본인직장": w_g_me, "배우자직장": w_g_spouse}
cuts = {
    "seoul_gangnam": c_seoul_gn, "gyeonggi_gangnam": c_gg_gn,
    "job_hub": c_hub, "subway": c_subway,
    "me": c_me, "spouse": c_spouse,
    "env_hh_min": c_env_hh_min, "env_hh_max": c_env_hh_max,
    "env_age_min": c_env_age_min, "env_age_max": c_env_age_max,
}

# 본인/배우자 출근지 거리 (사용자 선택 역 기반 매번 재계산)
catalog["본인직장_km"] = compute_personal_km(catalog, me_lat, me_lng)
catalog["배우자직장_km"] = compute_personal_km(catalog, sp_lat, sp_lng)
# 평형 (㎡ → 평 환산)
catalog["최소평"] = catalog["최소면적_㎡"].apply(sqm_to_pyeong)
catalog["최대평"] = catalog["최대면적_㎡"].apply(sqm_to_pyeong)
scored = score_dataframe(catalog, weights_seoul, weights_gg, cuts)


def _price_score(row):
    """가격축 점수 (0-100). 회복률 + 분양가대비(있을 때 가중).

    임계값은 catalog 실제 분포 percentile 기반 (2026-05 검증):
      회복률 75% → 0점, 100% → 100점 (25 percentile ~ 최대)
      분양가대비 100% → 0점, 200% → 100점 (분양 후 +0% ~ +100%)
    분양가 매칭된 단지는 두 신호 결합, 없으면 회복률만.
    """
    rec = row.get("회복률_pct")
    sup = row.get("분양가대비_pct")
    s_rec = None
    if pd.notna(rec):
        s_rec = max(0, min(100, (float(rec) - 75) / 25 * 100))
    s_sup = None
    if pd.notna(sup):
        s_sup = max(0, min(100, (float(sup) - 100) / 100 * 100))
    if s_rec is not None and s_sup is not None:
        return round(s_rec * 0.6 + s_sup * 0.4, 1)
    if s_rec is not None:
        return round(s_rec, 1)
    if s_sup is not None:
        return round(s_sup, 1)
    return None


scored["가격점수"] = scored.apply(_price_score, axis=1)


# ============================================================
# DSR 매수 가능 가격 계산 (2026 스트레스 DSR 3단계)
# ============================================================
# 가산금리 적용 — 수도권 스트레스 +3.0%p, 기본 주담대 약 4.5% → 약 7.5%
STRESS_RATE = 0.075  # 연이율
# 고가주택 한도 (2026 정책)
HIGH_PRICE_15 = 150000  # 15억(만원)
HIGH_PRICE_25 = 250000  # 25억(만원)
HIGH_PRICE_15_LIMIT = 40000  # 15억 초과 시 한도 4억
HIGH_PRICE_25_LIMIT = 20000  # 25억 초과 시 한도 2억


def _annuity_loan_capacity(annual_payment_won: float, rate: float, years: int) -> float:
    """연 상환액으로 감당 가능한 원금 (원리금균등 PV)."""
    if rate <= 0 or years <= 0:
        return 0
    monthly = annual_payment_won / 12
    r = rate / 12
    n = years * 12
    pv = monthly * (1 - (1 + r) ** -n) / r
    return pv


def calc_max_house_price(income, existing_debt, cash, dsr_pct, term_yr):
    """주어진 소득·기존 대출·현금으로 최대 매수 가능 주택 가격(만원)."""
    if income <= 0:
        return 0
    income_won = income * 10000
    # DSR 룰: 연 (주담대 + 기존 대출 이자) ≤ income × dsr_pct
    # 기존 대출 이자 단순 가정 — 잔액 × 5%/년
    existing_annual = existing_debt * 10000 * 0.05
    max_annual_for_new_loan = income_won * (dsr_pct / 100) - existing_annual
    if max_annual_for_new_loan <= 0:
        return 0
    max_loan_won = _annuity_loan_capacity(max_annual_for_new_loan, STRESS_RATE, term_yr)
    max_loan = max_loan_won / 10000  # 만원

    # 매수 가능 가격 = 현금 + 대출 (단, 고가주택 한도 적용)
    # 일단 가격 추정: 현금 + max_loan
    candidate = cash + max_loan
    # 고가주택 한도 적용 (반복 검증)
    for _ in range(3):
        if candidate > HIGH_PRICE_25:
            allowed_loan = min(max_loan, HIGH_PRICE_25_LIMIT)
        elif candidate > HIGH_PRICE_15:
            allowed_loan = min(max_loan, HIGH_PRICE_15_LIMIT)
        else:
            allowed_loan = max_loan
        new_candidate = cash + allowed_loan
        if abs(new_candidate - candidate) < 1:
            break
        candidate = new_candidate
    return round(candidate, 0)


max_house_price = calc_max_house_price(annual_income, existing_debt, cash_down,
                                        dsr_limit, loan_term_yr)
scored["DSR_매수가능"] = scored["최저매매가_만원"].apply(
    lambda p: "✅" if pd.notna(p) and p <= max_house_price else "✗"
)

# ============================================================
# 필터링
# ============================================================
bmin = budget - rng
bmax = budget + rng
mask = (scored["최고매매가_만원"] >= bmin) & (scored["최저매매가_만원"] <= bmax)
mask &= scored["입지점수"] >= min_score
if apply_dsr_filter and max_house_price > 0:
    mask &= scored["최저매매가_만원"] <= max_house_price
if region != "전체":
    mask &= scored["지역구분"] == region

filtered = scored[mask].sort_values("입지점수", ascending=False).head(top_n)

# ============================================================
# 메트릭
# ============================================================
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("예산 범위", f"{bmin:,} ~ {bmax:,}")
col2.metric("매칭 단지", f"{len(scored[mask])}개", f"표시: 상위 {len(filtered)}")
col3.metric("본인 출근지", f"{me_name}역")
col4.metric("배우자 출근지", f"{sp_name}역")
col5.metric("평균 입지점수",
            f"{filtered['입지점수'].mean():.1f}" if len(filtered) else "—")
col6.metric(
    "DSR 매수가능",
    f"{max_house_price:,.0f}만" if max_house_price > 0 else "—",
    help="연소득·기존대출·자본·DSR한도로 산출한 최대 매수가",
)

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
            f"본인({me_name})": c_me,
            f"배우자({sp_name})": c_spouse,
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

    # 기본(항상) — 식별·점수·가격
    BASE_COLS = ["입지점수", "가격점수", "자치구_수급점수", "점수_학군_v2", "DSR_매수가능",
                 "지역구분", "시구", "동", "단지명",
                 "최저매매가_만원", "최고매매가_만원"]
    GROUP_COLS = {
        "가격 시계열": ["전고점_만원", "직전거래_만원", "회복률_pct",
                       "메인평형_㎡", "메인평형_회복률_pct", "메인평형_거래수",
                       "첫거래_만원", "첫거래대비_pct", "최근12개월_거래수",
                       "RTMS_신뢰도"],
        "분양가": ["분양가_만원", "분양가대비_pct", "모집공고일"],
        "수급(자치구)": ["자치구_거래활성도", "자치구_가격모멘텀", "자치구_신축비율",
                       "자치구_전세가율_84㎡", "자치구_전세가율_전체",
                       "자치구_월세비중_pct"],
        "학군": ["점수_학군", "학군_성취율", "학군_특목고",
                "apt2_중_A%", "apt2_고_A%", "apt2_특목비율", "학군_매칭"],
        "거리·교통": ["가까운역_이름", "가까운역_노선", "가까운역_도보분",
                     "가까운역_강남까지_km", "강남까지_km",
                     "본인직장_km", "배우자직장_km",
                     "가까운지하철_km", "자체일자리_km", "회사2_남양_km"],
        "평형·메타": ["평형구간", "최소평", "최대평", "세대수", "준공년월",
                    "매칭_방식", "분양가매칭_방식", "RTMS_자치구", "시구_원본"],
    }
    DISPLAY = list(BASE_COLS)
    for g in column_groups:
        DISPLAY.extend(GROUP_COLS.get(g, []))
    DISPLAY.append("Naver")
    DISPLAY = [c for c in DISPLAY if c in show.columns]

    st.dataframe(
        show[DISPLAY].reset_index(drop=True),
        width="stretch",
        column_config={
            "Naver": st.column_config.LinkColumn("Naver", display_text="🔗 보기"),
            "입지점수": st.column_config.NumberColumn("입지", format="%.1f"),
            "가격점수": st.column_config.NumberColumn("가격", format="%.1f", help="회복률·분양가대비 결합(0-100). 회복률 60→90% 0→100점, 분양가대비 100→200% 0→100점, 둘 다 있을 때 회복률 0.6 가중"),
            "DSR_매수가능": st.column_config.TextColumn("매수", help="현재 사이드바 DSR 설정으로 살 수 있는지 (✅/✗)"),
            "자치구_수급점수": st.column_config.NumberColumn("수급", format="%.1f", help="RTMS 자체 derive — 자치구 거래활성도(50%) + 가격모멘텀(30%) + 신축비율 역(20%)"),
            "자치구_거래활성도": st.column_config.NumberColumn("거래활성도", format="%.2f", help="최근12개월 월평균거래 ÷ 전체기간 월평균. 1.0=평균, >1=증가"),
            "자치구_가격모멘텀": st.column_config.NumberColumn("가격모멘텀", format="%.2f", help="최근12개월 평균가 ÷ 전체기간 평균가"),
            "자치구_신축비율": st.column_config.NumberColumn("신축비율", format="%.2f", help="자치구 단지 중 2020년 이후 입주 비율"),
            "자치구_전세가율_84㎡": st.column_config.NumberColumn("전세가율84%", format="%.1f", help="국평(80-88㎡) 최근12개월 평균전세보증금/평균매매가 × 100"),
            "자치구_전세가율_전체": st.column_config.NumberColumn("전세가율%", format="%.1f", help="전 평형 최근12개월 평균전세/평균매매 × 100"),
            "자치구_월세비중_pct": st.column_config.NumberColumn("월세%", format="%.1f", help="자치구 임대거래 중 월세(1만원+) 비율"),
            "점수_학군_v2": st.column_config.NumberColumn("학군", format="%.1f", help="중·고 성취도 + 5년 추세 + 특목 진학 결합 (apt2.me + [필디] 데이터, 0-100)"),
            "점수_학군": st.column_config.NumberColumn("학군 v1", format="%.1f", help="[필디] 중학교 성취율·특목 단일 기반 점수"),
            "학군_성취율": st.column_config.NumberColumn("성취율%", format="%.1f"),
            "학군_특목고": st.column_config.NumberColumn("특목진학", format="%.1f", help="시구 평균 특목 진학자 수"),
            "apt2_중_A%": st.column_config.NumberColumn("중A%", format="%.1f", help="apt2.me 중학교 A등급 비율"),
            "apt2_고_A%": st.column_config.NumberColumn("고A%", format="%.1f", help="apt2.me 고등학교 A등급 비율"),
            "apt2_특목비율": st.column_config.NumberColumn("특목비율", format="%.3f", help="apt2.me 시군구 특목 진학 비율"),
            "학군_매칭": st.column_config.TextColumn("학군매칭", help="동/시구/시 매칭 단계"),
            "시구_원본": st.column_config.TextColumn("원본시구", help="catalog 빌드 시 분류 (RTMS 매칭으로 자동 보정된 경우 시구 컬럼과 다름)"),
            "최저매매가_만원": st.column_config.NumberColumn("최저(만원)", format="%d"),
            "최고매매가_만원": st.column_config.NumberColumn("최고(만원)", format="%d"),
            "평형구간": st.column_config.TextColumn("평형구간"),
            "최소평": st.column_config.NumberColumn("최소평", format="%.1f"),
            "최대평": st.column_config.NumberColumn("최대평", format="%.1f"),
            "강남까지_km": st.column_config.NumberColumn("강남km", format="%.2f"),
            "본인직장_km": st.column_config.NumberColumn(f"본인({me_name})km", format="%.2f"),
            "배우자직장_km": st.column_config.NumberColumn(f"배우자({sp_name})km", format="%.2f"),
            "회사2_남양_km": st.column_config.NumberColumn("남양km", format="%.2f"),
            "가까운지하철_km": st.column_config.NumberColumn("지하철km", format="%.2f"),
            "가까운역_이름": st.column_config.TextColumn("가까운역"),
            "가까운역_노선": st.column_config.TextColumn("노선"),
            "가까운역_도보분": st.column_config.NumberColumn("도보분", format="%.0f"),
            "가까운역_강남까지_km": st.column_config.NumberColumn("역→강남km", format="%.1f"),
            "전고점_만원": st.column_config.NumberColumn("전고점(만원)", format="%d"),
            "직전거래_만원": st.column_config.NumberColumn("직전거래(만원)", format="%d"),
            "회복률_pct": st.column_config.NumberColumn("회복률%", format="%.1f", help="전체 면적 거래 기준 (33평/24평 혼재 단지는 outlier 가능 — 메인평형_회복률 참고)"),
            "메인평형_㎡": st.column_config.NumberColumn("메인㎡", format="%.1f", help="단지 내 최빈 면적대 (±3㎡ 클러스터링)"),
            "메인평형_회복률_pct": st.column_config.NumberColumn("메인회복률%", format="%.1f", help="단지 메인 평형 한정 회복률 — outlier 줄임"),
            "메인평형_거래수": st.column_config.NumberColumn("메인거래수", format="%d"),
            "RTMS_신뢰도": st.column_config.TextColumn("신뢰도", help="매칭_거래수 기반 — 30+ 높음 / 10-29 중간 / 3-9 낮음 / 1-2 매우낮음"),
            "첫거래_만원": st.column_config.NumberColumn("첫거래(만원)", format="%d", help="RTMS 시계열의 가장 빠른 거래 — 신축 단지에서 분양 직후 가격 근사"),
            "첫거래대비_pct": st.column_config.NumberColumn("첫거래대비%", format="%.1f", help="직전거래÷첫거래 — 분양 직후 대비 시세 상승률 대용"),
            "분양가_만원": st.column_config.NumberColumn("분양가(만원)", format="%d", help="청약홈 공식 분양가(2020~2025 분양 단지만, 평형별 중간값)"),
            "분양가대비_pct": st.column_config.NumberColumn("분양가대비%", format="%.1f", help="직전거래÷분양가 — 분양 대비 시세 상승률"),
            "모집공고일": st.column_config.TextColumn("모집공고일"),
            "최근12개월_거래수": st.column_config.NumberColumn("최근12M거래", format="%d"),
            "매칭_방식": st.column_config.TextColumn("매칭", help="exact: 단지명 정확 일치 · fuzzy: 유사 매칭"),
            "RTMS_자치구": st.column_config.TextColumn("RTMS구", help="catalog 시구와 다르면 catalog 분류 오류 가능성"),
            "자체일자리_km": st.column_config.NumberColumn("자체일자리km", format="%.2f"),
            "세대수": st.column_config.NumberColumn("세대", format="%d"),
        },
        hide_index=True,
        height=500,
    )

    csv = show[DISPLAY].to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 CSV 다운로드", csv,
        file_name=f"budget_{budget}_top{top_n}_{me_name}_{sp_name}_{datetime.date.today()}.csv",
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
        pyeong_txt = ""
        if pd.notna(row.get("최소평")) and pd.notna(row.get("최대평")):
            pyeong_txt = f" · 평형 {row['최소평']:.1f}~{row['최대평']:.1f}평"
        st.caption(
            f"세대 {row['세대수']:,} · 준공 {row['준공년월']}{pyeong_txt} · "
            f"가격 {row['최저매매가_만원']:,.0f}~{row['최고매매가_만원']:,.0f}만원 · "
            f"입지점수 **{row['입지점수']:.1f}**"
        )

        school_match = row.get("학군_매칭", "—")
        if region_ == "서울":
            factors = [
                ("직장", row["s_job"], weights["직장"],
                 f"강남 {row['강남까지_km']:.2f}km / cut {c_seoul_gn}km"),
                ("교통", row["s_transit"], weights["교통"],
                 f"지하철 {row['가까운지하철_km']:.2f}km / cut {c_subway}km"),
                ("환경", row["s_env"], weights["환경"],
                 f"세대 {row['세대수']:,} / 준공 {row['준공년월']}"),
                ("학군", row["s_school"], weights["학군"],
                 f"점수 {row['s_school']:.1f} (매칭 {school_match})"),
                ("본인직장", row["s_me"], weights["본인직장"],
                 f"{me_name} {row['본인직장_km']:.2f}km / cut {c_me}km"),
                ("배우자직장", row["s_spouse"], weights["배우자직장"],
                 f"{sp_name} {row['배우자직장_km']:.2f}km / cut {c_spouse}km"),
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
                ("학군", row["s_school"], weights["학군"],
                 f"점수 {row['s_school']:.1f} (매칭 {school_match})"),
                ("본인직장", row["s_me"], weights["본인직장"],
                 f"{me_name} {row['본인직장_km']:.2f}km / cut {c_me}km"),
                ("배우자직장", row["s_spouse"], weights["배우자직장"],
                 f"{sp_name} {row['배우자직장_km']:.2f}km / cut {c_spouse}km"),
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
