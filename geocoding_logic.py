import re
import time
from functools import lru_cache
from typing import Optional, Tuple
from urllib.parse import quote_plus
import pandas as pd
import requests

class VWorldGeocoder:
    """
    VWorld Geocoder API 2.0 + AI 기반 주소 타입 자동 판별 + 주소 최적화
    """
    
    def __init__(self, api_key: str, daily_limit: int = 40_000, delay: float = 0.1):
        self.api_key = api_key
        self.base_url = "https://api.vworld.kr/req/address"
        self.daily_limit = daily_limit
        self.delay = delay
        self.request_count = 0
        
        # 주소 패턴 정의
        self._init_patterns()
    
    def _init_patterns(self):
        """주소 타입 판별을 위한 정규식 패턴 초기화"""
        
        # 도로명주소 패턴
        self.road_patterns = [
            r'.*[로대길]\s*\d+',                    # 테헤란로 123, 강남대로 456
            r'.*[로대].*길\s*\d+',                  # 논현로28길 15, 부림로169번길 22
            r'.*로\d+번길\s*\d+',                   # 판교로242번길 15
            r'.*대로\d+길\s*\d+',                   # 강남대로94길 20
            r'.*길\s*\d+(-\d+)?$',                  # 서초중앙로길 123-4
        ]
        
        # 지번주소 패턴  
        self.parcel_patterns = [
            r'.*[동리가]\s*\d+(-\d+)?$',            # 역삼동 123-45, 청담리 678
            r'.*[동리가]\s*\d+번지',                 # 신사동 123번지
            r'.*[동리가]\s*산\d+(-\d+)?',            # 관양동 산123-4
            r'.*[읍면]\s+.*[동리]\s*\d+',            # 기흥읍 상갈동 123
        ]
        
        # 도로명 키워드 (확실한 도로명 표시어)
        self.road_keywords = ['로', '대로', '길', '번길', '가길']
        
        # 지번 키워드 (확실한 지번 표시어)  
        self.parcel_keywords = ['동', '리', '가', '읍', '면', '번지', '산']
    
    def optimize_address(self, address: str) -> str:
        """
        🛠️ VWorld API에 최적화된 주소 형식으로 변환
        특히 농촌 지역과 복잡한 행정구역 주소를 단순화
        """
        address = address.strip()
        
        # 1단계: 기본 정리
        # 연속된 공백 제거
        address = re.sub(r'\s+', ' ', address)
        
        # 불필요한 단어 제거
        unnecessary_words = ['특별시', '광역시', '특별자치시', '특별자치도']
        for word in unnecessary_words:
            address = address.replace(word, '')
        
        # 2단계: 홍성군 특화 최적화
        if '홍성군' in address:
            # "충청남도 홍성군 홍성읍 오관리 254" → "홍성군 홍성읍 오관리 254"
            address = re.sub(r'^충청남도\s*', '', address)
            
            # 더 간단한 형태로 변환 시도
            # "홍성군 홍성읍 오관리 254" → "홍성읍 오관리 254"
            patterns_to_try = [
                address,  # 원본
                re.sub(r'^[^군]*군\s*', '', address),  # 군 이름 제거
            ]
            
            # 가장 간단한 형태 반환 (읍/면/동부터 시작)
            for pattern in patterns_to_try:
                if re.search(r'[읍면동]\s', pattern):
                    address = pattern
                    break
        
        # 3단계: 일반적인 최적화
        # "XX시 XX구" → "XX구" (시도별 간소화)
        address = re.sub(r'^[^도]*도\s*[^시]*시\s*', '', address)
        address = re.sub(r'^[^시]*시\s*', '', address)
        
        # 4단계: 번지 표기 정리
        # "254번지" → "254"
        address = re.sub(r'(\d+)번지', r'\1', address)
        
        # 5단계: 최종 정리
        address = address.strip()
        
        return address
    
    def analyze_address_type(self, address: str) -> str:
        """
        🤖 AI 기반 주소 타입 자동 판별 (최적화 강화)
        Returns: 'ROAD' 또는 'PARCEL'
        """
        address = address.strip()
        
        # 1단계: 확실한 패턴 매칭
        for pattern in self.road_patterns:
            if re.search(pattern, address):
                return 'ROAD'
        
        for pattern in self.parcel_patterns:
            if re.search(pattern, address):
                return 'PARCEL'
        
        # 2단계: 키워드 기반 점수 계산
        road_score = sum(1 for keyword in self.road_keywords if keyword in address)
        parcel_score = sum(1 for keyword in self.parcel_keywords if keyword in address)
        
        # 3단계: 복합 분석
        # 숫자 패턴 분석
        number_patterns = re.findall(r'\d+(-\d+)?', address)
        
        # 도로명주소는 보통 단순한 숫자 (예: 123)
        # 지번주소는 복합 숫자가 많음 (예: 123-45)
        has_complex_number = any('-' in pattern for pattern in number_patterns)
        
        if has_complex_number:
            parcel_score += 2  # 가중치 증가
        else:
            road_score += 1
        
        # 4단계: 홍성군 특화 분석 (지번주소 가능성 높음)
        if '홍성군' in address or any(x in address for x in ['읍', '면', '리']):
            parcel_score += 2
        
        # 5단계: 최종 판별
        if road_score > parcel_score:
            return 'ROAD'
        elif parcel_score > road_score:
            return 'PARCEL'
        else:
            # 농촌 지역은 지번주소 우선
            if any(x in address for x in ['읍', '면', '리', '군']):
                return 'PARCEL'
            else:
                return 'ROAD'
    
    @lru_cache(maxsize=10_000)
    def _call_api(self, encoded_addr: str, addr_type: str) -> Optional[Tuple[float, float]]:
        """VWorld API 2.0 호출 (응답 파싱 로직 수정)"""
        
        if self.request_count >= self.daily_limit:
            raise RuntimeError("일일 40,000건 API 한도 초과")
        
        params = {
            "service": "address",
            "request": "getCoord",
            "version": "2.0",
            "crs": "epsg:4326",
            "address": encoded_addr,
            "format": "json",
            "type": addr_type.upper(),
            "refine": "true",
            "simple": "false",
            "key": self.api_key,
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            self.request_count += 1
            
            if response.status_code != 200:
                print(f"HTTP 에러: {response.status_code}")
                return None
            
            data = response.json()
            
            # 디버깅용 출력 (첫 번째 요청만)
            if self.request_count <= 1:
                print(f"API 응답 구조: {data}")
            
            # 응답 상태 확인 (수정된 부분)
            if data.get("response", {}).get("status") == "OK":
                # result와 point 존재 여부 확인
                result_data = data.get("response", {}).get("result")
                if result_data and "point" in result_data:
                    point = result_data["point"]
                    
                    # x, y 좌표 존재 여부 확인
                    if "x" in point and "y" in point:
                        try:
                            # 문자열로 된 좌표를 float으로 변환
                            longitude = float(point["x"])  # x = 경도
                            latitude = float(point["y"])   # y = 위도
                            
                            print(f"성공: {encoded_addr} -> ({latitude}, {longitude})")
                            return latitude, longitude
                        
                        except (ValueError, TypeError) as e:
                            print(f"좌표 변환 실패: {point}, 에러: {e}")
                            return None
                    else:
                        print(f"point에 x 또는 y 좌표가 없음: {point}")
                        return None
                else:
                    print(f"result 또는 point가 없음: {result_data}")
                    return None
            else:
                status = data.get("response", {}).get("status", "UNKNOWN")
                print(f"API 상태 에러: {status}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"네트워크 에러: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            print(f"데이터 파싱 에러: {e}, 응답: {data if 'data' in locals() else 'None'}")
            return None
        
        return None
    
    def geocode_address(self, address: str, optimize: bool = True) -> Tuple[Optional[float], Optional[float], str]:
        """
        🎯 스마트 지오코딩: 최적화 + AI 판별 + 다중 시도
        Returns: (위도, 경도, 사용된_타입)
        """
        
        original_address = address.strip()
        if not original_address:
            return None, None, "UNKNOWN"
        
        # 시도할 주소 변형들
        address_variants = [original_address]
        
        if optimize:
            optimized_addr = self.optimize_address(original_address)
            if optimized_addr != original_address:
                address_variants.insert(0, optimized_addr)  # 최적화된 주소를 먼저 시도
        
        # 각 주소 변형에 대해 시도
        for addr_variant in address_variants:
            encoded_addr = quote_plus(addr_variant)
            
            # AI가 판별한 타입으로 먼저 시도
            predicted_type = self.analyze_address_type(addr_variant)
            result = self._call_api(encoded_addr, predicted_type)
            
            if result:
                return result[0], result[1], predicted_type
            
            time.sleep(self.delay)
            
            # 반대 타입으로 재시도
            fallback_type = "PARCEL" if predicted_type == "ROAD" else "ROAD"
            result = self._call_api(encoded_addr, fallback_type)
            
            if result:
                return result[0], result[1], fallback_type
            
            time.sleep(self.delay)
        
        return None, None, "FAILED"
    
    def process_dataframe(self, df: pd.DataFrame, address_column: str, progress_callback=None, optimize_address=True) -> pd.DataFrame:
        """DataFrame 일괄 처리 + AI 분석 결과 포함 + 진행률 콜백 + 주소 최적화"""
        
        if address_column not in df.columns:
            raise KeyError(f"'{address_column}' 컬럼이 존재하지 않습니다.")
        
        latitudes = []
        longitudes = []
        used_types = []
        predicted_types = []
        optimized_addresses = [] if optimize_address else None
        
        total_rows = len(df)
        
        for idx, addr in enumerate(df[address_column]):
            if pd.isna(addr):
                lat, lon, used_type = None, None, "UNKNOWN"
                predicted_type = "UNKNOWN"
                optimized_addr = None
            else:
                original_addr = str(addr)
                
                # 주소 최적화
                if optimize_address:
                    optimized_addr = self.optimize_address(original_addr)
                    analysis_addr = optimized_addr
                else:
                    optimized_addr = original_addr
                    analysis_addr = original_addr
                
                # AI 예측 저장
                predicted_type = self.analyze_address_type(analysis_addr)
                
                # 실제 지오코딩 수행
                lat, lon, used_type = self.geocode_address(original_addr, optimize=optimize_address)
            
            latitudes.append(lat)
            longitudes.append(lon)
            used_types.append(used_type)
            predicted_types.append(predicted_type)
            
            if optimize_address:
                optimized_addresses.append(optimized_addr)
            
            # 진행률 콜백 호출
            if progress_callback:
                progress_callback(idx + 1, total_rows)
            
            # 콘솔 진행률 표시
            if (idx + 1) % 10 == 0 or (idx + 1) == total_rows:
                success_count = sum(1 for lat in latitudes if lat is not None)
                success_rate = (success_count / (idx + 1)) * 100
                print(f"진행률: {idx + 1}/{total_rows} ({(idx + 1)/total_rows*100:.1f}%) - 성공률: {success_rate:.1f}%")
        
        # 결과 DataFrame 생성
        result_df = df.copy()
        result_df["latitude"] = latitudes
        result_df["longitude"] = longitudes
        result_df["geocoding_success"] = [lat is not None for lat in latitudes]
        result_df["ai_predicted_type"] = predicted_types
        result_df["actual_used_type"] = used_types
        
        if optimize_address:
            result_df["optimized_address"] = optimized_addresses
        
        return result_df

