# app.py
import streamlit as st
import pandas as pd
import tempfile
import os
from io import BytesIO
from rag_logic import initialize_rag_chain, get_answer
from geocoding_logic import VWorldGeocoder

st.set_page_config(page_title="주소 변환 & RAG Chatbot", page_icon="🗺️")

# 사이드바 탭 선택
tab_selection = st.sidebar.selectbox(
    "서비스 선택",
    ["🗺️ 주소→좌표 변환", "🤖 PDF 기반 RAG 챗봇"]
)

if tab_selection == "🗺️ 주소→좌표 변환":
    st.title("🗺️ 주소→좌표 변환 서비스")
    
    # API 키 입력
    st.sidebar.title("🔑 API 설정")
    vworld_api_key = st.sidebar.text_input(
        "VWorld API 키를 입력하세요:",
        type="password",
        placeholder="발급받은_인증키"
    )
    
    if not vworld_api_key:
        st.warning("⚠️ VWorld API 키를 입력해주세요.")
        st.info("📋 API 키 발급: https://www.vworld.kr/dev/v4dv_guide2_s001.do")
        st.stop()
    
    # 파일 업로드
    uploaded_file = st.file_uploader(
        "주소가 포함된 엑셀/CSV 파일을 업로드하세요:",
        type=['xlsx', 'csv'],
        help="주소 정보가 포함된 컬럼이 있는 파일을 업로드하세요."
    )
    
    if uploaded_file:
        try:
            # 파일 읽기
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.success(f"✅ 파일 로드 완료: {len(df)}행 × {len(df.columns)}열")
            
            # 데이터 미리보기
            with st.expander("📊 데이터 미리보기"):
                st.dataframe(df.head())
            
            # 주소 컬럼 선택
            address_column = st.selectbox(
                "주소가 포함된 컬럼을 선택하세요:",
                options=df.columns.tolist(),
                help="주소 정보가 들어있는 컬럼을 선택하세요."
            )
            
            # 변환 설정
            col1, col2 = st.columns(2)
            with col1:
                max_rows = st.number_input(
                    "변환할 최대 행 수:",
                    min_value=1,
                    max_value=len(df),
                    value=min(100, len(df)),
                    help="API 한도를 고려하여 적절한 수를 선택하세요."
                )
            
            with col2:
                if st.button("🗺️ 주소 변환 시작", type="primary"):
                    geocoder = VWorldGeocoder(vworld_api_key)
                    
                    # 선택된 행 수만큼 처리
                    df_to_process = df.head(max_rows)
                    
                    with st.spinner(f"주소 변환 중... (최대 {max_rows}건)"):
                        progress_bar = st.progress(0)
                        
                        # 변환 진행상황을 실시간으로 보여주기 위한 플레이스홀더
                        status_placeholder = st.empty()
                        
                        try:
                            result_df = geocoder.process_dataframe(df_to_process, address_column)
                            
                            # 성공률 계산
                            success_count = result_df['geocoding_success'].sum()
                            success_rate = (success_count / len(result_df)) * 100
                            
                            st.success(f"✅ 변환 완료! 성공률: {success_rate:.1f}% ({success_count}/{len(result_df)})")
                            
                            # 결과 미리보기
                            with st.expander("📍 변환 결과 미리보기"):
                                st.dataframe(result_df[['주소', 'latitude', 'longitude', 'geocoding_success']].head(10))
                            
                            # 결과 다운로드
                            output = BytesIO()
                            if uploaded_file.name.endswith('.csv'):
                                result_df.to_csv(output, index=False, encoding='utf-8-sig')
                                file_extension = 'csv'
                                mime_type = 'text/csv'
                            else:
                                result_df.to_excel(output, index=False)
                                file_extension = 'xlsx'
                                mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                            
                            st.download_button(
                                label="📥 변환 결과 다운로드",
                                data=output.getvalue(),
                                file_name=f"geocoded_{uploaded_file.name}",
                                mime=mime_type
                            )
                            
                        except Exception as e:
                            st.error(f"❌ 변환 중 오류: {str(e)}")
                            
        except Exception as e:
            st.error(f"❌ 파일 읽기 오류: {str(e)}")

else:  # RAG 챗봇 탭
    st.title("🤖 PDF 문서 기반 RAG Chatbot")
    
    # 기존 RAG 코드 (동일)
    st.sidebar.title("🔑 API 설정")
    openai_api_key = st.sidebar.text_input(
        "OpenAI API 키를 입력하세요:",
        type="password",
        placeholder="sk-..."
    )
    
    if not openai_api_key:
        st.warning("⚠️ OpenAI API 키를 입력해주세요.")
        st.stop()
    
    # 기존 RAG 기능 코드 계속...
    # (기존 app.py의 PDF 업로드 및 RAG 기능 부분 그대로 유지)
