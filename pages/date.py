import pathlib
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="데이트 동행 신청서", page_icon="💌", layout="wide")

# Hide all Streamlit chrome
st.markdown("""
<style>
#MainMenu, header, footer,
[data-testid="stSidebar"],
[data-testid="stToolbar"],
.stDeployButton { display: none !important; }
.main .block-container {
    padding: 0 !important;
    max-width: 100% !important;
    margin: 0 !important;
}
section.main { padding: 0 !important; }
.stApp { overflow: hidden !important; }
</style>
""", unsafe_allow_html=True)

html = pathlib.Path("index.html").read_text(encoding="utf-8")

# height는 일반 화면 기준 900px; 모바일 대응은 scrolling=False로 고정
components.html(html, height=900, scrolling=False)
