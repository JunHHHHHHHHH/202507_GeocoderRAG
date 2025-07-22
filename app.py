import os
from io import BytesIO
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from geocoding_logic import VWorldGeocoder

# .env 파일 로드
load_dotenv()

st.set_page_config(page_title="🤖 AI 주소 → 좌표 변환기", page_icon="🗺️")

# CSS 스타일 추가 - 제목 크기를 절반으로
st.markdown("""
<style>
.small-title {
    font-size: 1.8rem !important;
    font-weight: bold;
    color: #1f77b4;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

# 제목을 HTML로 표시 (기존 st.title() 대신)
st.markdown('<h1 class="small-title">🗺️ AI지오코딩(주소→좌표 변환기)</h1>', 
            unsafe_allow_html=True)

# 앱 설명 추가
st.markdown("""
🤖 **AI 기능**: 주소를 자동 분석하여 지번주소/도로명주소를 판별해 최적의 API 호출을 수행합니다.
- 📊 AI 예측 정확도 분석
- ⚡ API 호출 횟수 최적화 (최대 50% 절약)
- 🔄 실패시 자동으로 반대 타입 재시도
- 🛠️ 주소 형식 자동 최적화
""")

# 1) API 키 입력
api_key = st.sidebar.text_input(
    "VWorld API 키",
    value=os.getenv("VWORLD_API_KEY", ""),
    type="password",
    help="https://www.vworld.kr에서 발급"
)

if not api_key:
    st.warning("좌측 사이드바에 API 키를 입력하세요.")
    st.stop()

# API 키 로드 확인 메시지
if os.getenv("VWORLD_API_KEY"):
    st.sidebar.success("✅ API 키가 환경변수에서 로드되었습니다.")

# 2) 파일 업로드
file = st.file_uploader(
    "엑셀(.xlsx) 또는 CSV 파일을 올리세요",
    type=["xlsx", "csv"]
)

if not file:
    st.info("📤 파일을 업로드하여 시작하세요.")
    st.stop()

# 3) 데이터 읽기
try:
    df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
except Exception as e:
    st.error(f"파일 읽기 오류: {e}")
    st.stop()

st.success(f"✅ 로드 완료: {len(df)}행 × {len(df.columns)}열")

with st.expander("미리보기"):
    st.dataframe(df.head())

# 4) 주소 컬럼 선택 & 행 수 제한
addr_col = st.selectbox("주소 컬럼 선택", df.columns.tolist())

max_rows = st.number_input(
    "변환할 최대 행 수", 
    1, len(df), 
    min(500, len(df)), 
    step=100,
    help="VWorld API 일일 한도: 40,000건"
)

# 주소 형식 최적화 옵션 추가
optimize_address = st.checkbox(
    "🛠️ 주소 형식 자동 최적화", 
    value=True,
    help="VWorld API에 최적화된 형태로 주소를 자동 변환합니다"
)

# AI 분석 미리보기 (옵션)
if st.checkbox("🤖 AI 주소 분석 미리보기 (선택사항)"):
    with st.expander("AI 주소 타입 분석 결과"):
        geocoder_preview = VWorldGeocoder(api_key)
        sample_addresses = df[addr_col].dropna().head(10)
        
        preview_data = []
        for addr in sample_addresses:
            original_addr = str(addr)
            optimized_addr = geocoder_preview.universal_address_optimize(original_addr)[0] if optimize_address else original_addr
            
            preview_data.append({
                "원본 주소": original_addr,
                "최적화된 주소": optimized_addr if optimize_address else "최적화 안함",
                "AI 예측 타입": predicted_type,
                "설명": "도로명주소" if predicted_type == "ROAD" else "지번주소"
            })
        
        preview_df = pd.DataFrame(preview_data)
        st.dataframe(preview_df, use_container_width=True)

# 5) 변환 실행
if st.button("🤖 스마트 지오코딩 시작"):
    geocoder = VWorldGeocoder(api_key)
    
    # 진행률 표시를 위한 진행바 생성
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with st.spinner("🤖 AI가 주소를 분석하고 API 호출 중…"):
        # 진행률 업데이트를 위한 콜백 함수
        def update_progress(current, total):
            progress = current / total
            progress_bar.progress(progress)
            status_text.text(f"진행중... {current}/{total} ({progress*100:.1f}%)")
        
        result = geocoder.process_dataframe(
            df.head(max_rows), 
            addr_col, 
            progress_callback=update_progress,
            optimize_address=optimize_address
        )
    
    # 진행률 표시 완료
    progress_bar.progress(1.0)
    status_text.text("✅ 완료!")
    
    # 결과 통계
    ok = result["geocoding_success"].sum()
    total = len(result)
    success_rate = ok/total*100
    
    st.success(f"🎉 변환 완료! 성공 {ok}/{total}행 ({success_rate:.1f}%)")
    
    # 변수 초기화 (에러 방지)
    ai_accuracy = 0
    api_calls_saved = 0
    saved_percentage = 0
    
    # AI 분석 정확도 표시 (성공한 경우에만)
    if ok > 0:
        # 성공한 케이스 중에서 AI 예측이 맞은 비율
        successful_cases = result[result["geocoding_success"] == True]
        correct_predictions = (successful_cases["ai_predicted_type"] == successful_cases["actual_used_type"]).sum()
        ai_accuracy = correct_predictions / ok * 100
        
        # API 호출 절약 효과
        first_try_success = correct_predictions
        api_calls_saved = first_try_success  # 첫 시도 성공시 1번 절약
        total_possible_calls = ok * 2  # 최대 2번씩 호출 가능
        actual_calls = ok + (ok - first_try_success)  # 실제 호출 횟수
        saved_percentage = (api_calls_saved / total_possible_calls) * 100
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("🎯 AI 예측 정확도", f"{ai_accuracy:.1f}%")
        
        with col2:
            st.metric("⚡ API 호출 절약", f"{api_calls_saved}회")
        
        with col3:
            st.metric("💡 절약 효율", f"{saved_percentage:.1f}%")
        
        # 주소 최적화 효과 표시
        if optimize_address and 'optimized_address' in result.columns:
            optimized_success = result[
                (result["geocoding_success"] == True) & 
                (result["optimized_address"] != result[addr_col])
            ].shape[0]
            
            if optimized_success > 0:
                st.info(f"🛠️ 주소 최적화를 통한 성공: {optimized_success}건")
        
        # 추가 통계 정보
        with st.expander("📊 상세 분석 결과"):
            road_predicted = (result["ai_predicted_type"] == "ROAD").sum()
            parcel_predicted = (result["ai_predicted_type"] == "PARCEL").sum()
            
            road_success = ((result["actual_used_type"] == "ROAD") & (result["geocoding_success"] == True)).sum()
            parcel_success = ((result["actual_used_type"] == "PARCEL") & (result["geocoding_success"] == True)).sum()
            
            st.write("**AI 예측 분포:**")
            st.write(f"- 도로명주소 예측: {road_predicted}건")
            st.write(f"- 지번주소 예측: {parcel_predicted}건")
            
            st.write("**실제 성공 분포:**")
            st.write(f"- 도로명주소로 성공: {road_success}건")
            st.write(f"- 지번주소로 성공: {parcel_success}건")
    
    else:
        # 모든 변환이 실패한 경우 디버깅 정보 표시
        st.error("🚨 모든 주소 변환이 실패했습니다!")
        
        with st.expander("🔧 디버깅 정보"):
            # API 키 유효성 테스트
            st.write("**API 키 정보:**")
            st.write(f"- API 키 길이: {len(api_key)}")
            st.write(f"- API 키 형식: {'정상' if len(api_key) > 30 else '비정상 (너무 짧음)'}")
            
            # 샘플 주소로 직접 테스트
            st.write("**샘플 주소 테스트:**")
            sample_addr = df[addr_col].dropna().iloc[0] if len(df[addr_col].dropna()) > 0 else "테스트 주소 없음"
            st.write(f"- 원본 주소: `{sample_addr}`")
            
            if sample_addr != "테스트 주소 없음":
                if optimize_address:
                    optimized_addr = geocoder.optimize_address(str(sample_addr))
                    st.write(f"- 최적화된 주소: `{optimized_addr}`")
                    test_addr = optimized_addr
                else:
                    test_addr = str(sample_addr)
                
                predicted_type = geocoder.analyze_address_type(test_addr)
                st.write(f"- AI 예측 타입: `{predicted_type}`")
                
                # 직접 API 테스트 (디버깅 모드)
                st.write("**API 직접 호출 테스트:**")
                try:
                    from urllib.parse import quote_plus
                    import requests
                    
                    encoded_addr = quote_plus(test_addr)
                    test_url = f"https://api.vworld.kr/req/address?service=address&request=getCoord&version=2.0&crs=epsg:4326&address={encoded_addr}&format=json&type={predicted_type}&refine=true&simple=false&key={api_key}"
                    
                    response = requests.get(test_url, timeout=10)
                    st.write(f"- HTTP 상태: {response.status_code}")
                    
                    if response.status_code == 200:
                        response_data = response.json()
                        st.json(response_data)
                    else:
                        st.write(f"- 응답 내용: {response.text[:500]}...")
                    
                except Exception as e:
                    st.write(f"- 에러: {str(e)}")
            
            # 일반적인 해결 방법 제시
            st.info("""
            **🔍 가능한 해결방법:**
            1. **API 키 확인**: VWorld 홈페이지에서 API 키가 유효한지 확인
            2. **주소 최적화 사용**: 위의 '주소 형식 자동 최적화' 체크박스 활성화
            3. **주소 형식 수정**: 더 간단한 형태로 변경 (예: 'OO군 OO읍 OO리 123')
            4. **네트워크 확인**: 인터넷 연결 상태 확인
            5. **API 한도 확인**: VWorld 일일 40,000건 한도 초과 여부 확인
            """)
    
    # 결과 미리보기
    with st.expander("🔍 결과 미리보기"):
        cols_to_show = [addr_col, "latitude", "longitude", "ai_predicted_type", "actual_used_type", "geocoding_success"]
        
        # 최적화된 주소 컬럼이 있으면 추가
        if optimize_address and 'optimized_address' in result.columns:
            cols_to_show.insert(1, "optimized_address")
        
        # 컬럼명을 한글로 변경해서 표시
        display_df = result[cols_to_show].head(20).copy()
        
        if optimize_address and 'optimized_address' in result.columns:
            display_df.columns = ["원본주소", "최적화주소", "위도", "경도", "AI예측타입", "실제성공타입", "변환성공"]
        else:
            display_df.columns = ["원본주소", "위도", "경도", "AI예측타입", "실제성공타입", "변환성공"]
        
        # 성공/실패 표시 개선
        display_df["변환성공"] = display_df["변환성공"].map({True: "✅ 성공", False: "❌ 실패"})
        display_df["AI예측타입"] = display_df["AI예측타입"].map({
            "ROAD": "🛣️ 도로명", 
            "PARCEL": "🏠 지번", 
            "UNKNOWN": "❓ 불명"
        })
        display_df["실제성공타입"] = display_df["실제성공타입"].map({
            "ROAD": "🛣️ 도로명", 
            "PARCEL": "🏠 지번", 
            "FAILED": "❌ 실패",
            "UNKNOWN": "❓ 불명"
        })
        
        st.dataframe(display_df, use_container_width=True)
    
    # 실패한 주소 분석 (개선)
    failed_addresses = result[result["geocoding_success"] == False]
    if len(failed_addresses) > 0:
        with st.expander(f"⚠️ 실패한 주소 분석 ({len(failed_addresses)}건)"):
            failed_cols = [addr_col, "ai_predicted_type"]
            if optimize_address and 'optimized_address' in result.columns:
                failed_cols.insert(1, "optimized_address")
            
            failed_display = failed_addresses[failed_cols].head(20).copy()
            
            if optimize_address and 'optimized_address' in result.columns:
                failed_display.columns = ["원본주소", "최적화주소", "AI예측타입"]
            else:
                failed_display.columns = ["원본주소", "AI예측타입"]
            
            # AI 예측 타입 변환
            failed_display["AI예측타입"] = failed_display["AI예측타입"].map({
                "ROAD": "🛣️ 도로명", 
                "PARCEL": "🏠 지번", 
                "UNKNOWN": "❓ 불명"
            })
            
            st.dataframe(failed_display, use_container_width=True)
            
            # 실패 패턴 분석
            st.subheader("🔍 실패 패턴 분석")
            
            # 주소 길이 분석
            addr_lengths = failed_addresses[addr_col].astype(str).str.len()
            avg_length = addr_lengths.mean()
            st.write(f"- **평균 주소 길이**: {avg_length:.1f}자")
            
            # 공통 키워드 분석
            all_failed_text = " ".join(failed_addresses[addr_col].astype(str))
            common_words = []
            for word in ['읍', '면', '동', '리', '로', '길', '아파트', '빌딩']:
                count = all_failed_text.count(word)
                if count > 0:
                    common_words.append(f"{word}({count}번)")
            
            if common_words:
                st.write(f"- **공통 키워드**: {', '.join(common_words)}")
                
    # 6) 다운로드
    st.subheader("📥 결과 다운로드")
    
    # 다운로드 옵션
    download_options = st.radio(
        "다운로드 컬럼 선택",
        ["기본 (좌표만)", "전체 (AI 분석 포함)", "성공한 데이터만"],
        horizontal=True
    )
    
    if download_options == "기본 (좌표만)":
        exclude_cols = ["ai_predicted_type", "actual_used_type"]
        if not optimize_address:
            exclude_cols.append("optimized_address")
        download_df = result[[col for col in result.columns if col not in exclude_cols]]
    elif download_options == "전체 (AI 분석 포함)":
        download_df = result
    else:  # 성공한 데이터만
        download_df = result[result["geocoding_success"] == True]
    
    if len(download_df) > 0:
        buffer = BytesIO()
        
        if file.name.endswith(".csv"):
            download_df.to_csv(buffer, index=False, encoding="utf-8-sig")
            mime = "text/csv"
            file_extension = "csv"
        else:
            download_df.to_excel(buffer, index=False)
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            file_extension = "xlsx"
        
        # 파일명에 결과 정보 포함
        timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M")
        result_filename = f"geocoded_{success_rate:.0f}percent_{timestamp}.{file_extension}"
        
        st.download_button(
            "📥 결과 다운로드",
            data=buffer.getvalue(),
            file_name=result_filename,
            mime=mime,
            help=f"성공률 {success_rate:.1f}%의 지오코딩 결과를 다운로드합니다."
        )
    else:
        st.warning("다운로드할 데이터가 없습니다.")
    
    # 추가 정보 (수정)
    st.info(f"""
    📊 **처리 완료 정보**
    - 총 처리: {total}건
    - 성공: {ok}건 ({success_rate:.1f}%)
    - AI 정확도: {ai_accuracy:.1f}% (성공 케이스 기준)
    - API 호출 절약: {api_calls_saved}회
    - 주소 최적화: {'사용' if optimize_address else '미사용'}
    """)

# 사이드바에 사용 가이드 추가
with st.sidebar:
    st.markdown("---")
    st.subheader("📖 사용 가이드")
    
    with st.expander("주소 형식 가이드"):
        st.write("""
        **🎯 성공률이 높은 주소 형식:**
        
        **🛣️ 도로명주소 (권장):**
        - 서울시 강남구 테헤란로 123
        - 부산시 해운대구 해운대로 456
        
        **🏠 지번주소:**
        - 서울시 강남구 역삼동 123-45
        - 경기도 성남시 분당구 정자동 178
        
        **❌ 피해야 할 형식:**
        - 불완전한 주소: "강남구 어딘가"
        - 건물명만: "롯데타워"
        - 과도한 상세: "...아파트 101동 202호"
        """)
    
    with st.expander("AI 분석 설명"):
        st.write("""
        **🤖 AI가 자동으로 판별하는 주소 타입:**
        
        **🛣️ 도로명주소:**
        - 테헤란로 123
        - 강남대로 456  
        - 논현로28길 15
        
        **🏠 지번주소:**
        - 역삼동 123-45
        - 청담리 678
        - 관양동 산123-4
        """)
    
    with st.expander("API 사용량"):
        if 'geocoder' in locals():
            st.write(f"""
            **일일 한도:** 40,000건
            **현재 요청:** {geocoder.request_count}건
            **AI 절약 효과:** 최대 50% 호출 감소
            """)
        else:
            st.write("""
            **일일 한도:** 40,000건
            **현재 요청:** 0건
            **AI 절약 효과:** 최대 50% 호출 감소
            """)
