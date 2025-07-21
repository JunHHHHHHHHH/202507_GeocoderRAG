# app.py
import pandas as pd
import streamlit as st
from io import BytesIO

# RAG 모듈이 선택적으로 존재할 수 있으므로 예외 처리
try:
    from rag_logic import initialize_rag_chain, get_answer
    RAG_AVAILABLE = True
except ModuleNotFoundError:
    RAG_AVAILABLE = False

from geocoding_logic import VWorldGeocoder

st.set_page_config(page_title="주소 변환 & RAG Chatbot", page_icon="🗺️")

# -------------------------------------------------------------
# 사이드바 탭
# -------------------------------------------------------------
tab = st.sidebar.selectbox("서비스 선택", ["🗺️ 주소→좌표 변환", "🤖 PDF 기반 RAG 챗봇"])

# -------------------------------------------------------------
# 🗺️ 주소 → 좌표 변환
# -------------------------------------------------------------
if tab == "🗺️ 주소→좌표 변환":
    st.title("🗺️ 주소 → 좌표 변환 서비스")

    st.sidebar.title("🔑 VWorld API 키")
    vworld_key = st.sidebar.text_input("API 키를 입력하세요", type="password")

    if not vworld_key:
        st.warning("VWorld API 키를 입력해야 합니다.")
        st.stop()

    # 파일 업로드
    file = st.file_uploader("엑셀(.xlsx) 또는 CSV 업로드", type=["xlsx", "csv"])

    if file:
        # ---------------- 파일 읽기 ----------------
        try:
            df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
        except Exception as e:
            st.error(f"파일 읽기 오류: {e}")
            st.stop()

        st.success(f"✅ 파일 로드 완료: {len(df)}행 × {len(df.columns)}열")

        with st.expander("📊 데이터 미리보기"):
            st.dataframe(df.head())

        # 주소 컬럼 선택
        addr_col = st.selectbox("주소 컬럼 선택", df.columns.tolist())

        # 최대 행 수
        max_rows = st.number_input(
            "변환할 최대 행 수", 1, len(df), min(100, len(df)), step=100
        )

        if st.button("🗺️ 변환 시작", type="primary"):
            geocoder = VWorldGeocoder(vworld_key)

            with st.spinner("주소 변환 중..."):
                result_df = geocoder.process_dataframe(df.head(max_rows), addr_col)

            ok = result_df["geocoding_success"].sum()
            rate = ok / len(result_df) * 100
            st.success(f"변환 완료! 성공률 {rate:.1f}%  ({ok}/{len(result_df)})")

            with st.expander("📍 결과 미리보기"):
                preview_cols = [addr_col, "latitude", "longitude", "geocoding_success"]
                st.dataframe(result_df[preview_cols].head(10))

            # ---------------- 결과 다운로드 ----------------
            buffer = BytesIO()
            if file.name.endswith(".csv"):
                result_df.to_csv(buffer, index=False, encoding="utf-8-sig")
                mime = "text/csv"
            else:
                result_df.to_excel(buffer, index=False)
                mime = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            st.download_button(
                "📥 결과 다운로드",
                data=buffer.getvalue(),
                file_name=f"geocoded_{file.name}",
                mime=mime,
            )

# -------------------------------------------------------------
# 🤖 PDF 기반 RAG 챗봇  (선택적)
# -------------------------------------------------------------
else:
    st.title("🤖 PDF 문서 기반 RAG Chatbot")

    if not RAG_AVAILABLE:
        st.error("rag_logic 모듈이 없어서 챗봇 기능을 사용할 수 없습니다.")
        st.stop()

    st.sidebar.title("🔑 OpenAI API 키")
    openai_key = st.sidebar.text_input("OpenAI API 키", type="password")

    if not openai_key:
        st.warning("OpenAI API 키를 입력해야 합니다.")
        st.stop()

    # 이 아래에는 기존 PDF-RAG 로직을 그대로 두시면 됩니다.
