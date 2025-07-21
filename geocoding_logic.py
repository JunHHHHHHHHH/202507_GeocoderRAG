import re
import time
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
        
        # 수동 캐시 (성공한 결과만 캐시)
        self._success_cache = {}
        
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
        """
        address = address.strip()
        
        # 1단계: 기본 정리
        address = re.sub(r'\s+', ' ', address)
        
        # 2단계: 불필요한 행정구역명 제거
        unnecessary_words = ['특별시', '광역시', '특별자치시', '특별자치도']
        for word in unnecessary_words:
            address = address.replace(word, '')
        
        # 3단계: 홍성군 등 농촌 지역 최적화
        if '홍성군' in address:
            # "충청남도 홍성군 홍성읍 오관리 254" → "홍성군 홍성읍 오관리 254"
            address = re.sub(r'^충청남도\s*', '', address)
        
        # 4단계: 시/도 단위 간소화 (선택적)
        address = re.sub(r'^[^도]*도\s*[^시]*시\s*', '', address)
        address = re.sub(r'^[^시]*시\s*', '', address)
        
        # 5단계: 번지 표기 정리
        address = re.sub(r'(\d+)번지', r'\1', address)
        
        return address.strip()
    
    def analyze_address_type(self, address: str) -> str:
        """🤖 AI 기반 주소 타입 자동 판별"""
        address = address.strip()
        
        # 확실한 패턴 매칭
        for pattern in self.road_patterns:
            if re.search(pattern, address):
                return 'ROAD'
        
        for pattern in self.parcel_patterns:
            if re.search(pattern, address):
                return 'PARCEL'
        
        # 키워드 기반 점수 계산
        road_score = sum(1 for keyword in self.road_keywords if keyword in address)
        parcel_score = sum(1 for keyword in self.parcel_keywords if keyword in address)
        
        # 복합 번지 분석
        number_patterns = re.findall(r'\d+(-\d+)?', address)
        has_complex_number = any('-' in pattern for pattern in number_patterns)
        
        if has_complex_number:
            parcel_score += 2
        else:
            road_score += 1
        
        # 농촌 지역 가중치
        if any(x in address for x in ['읍', '면', '리', '군']):
            parcel_score += 2
        
        # 최종 판별
        if parcel_score >= road_score:
            return 'PARCEL'
        else:
            return 'ROAD'
    
    def _call_api(self, encoded_addr: str, addr_type: str) -> Optional[Tuple[float, float]]:
        """
        VWorld API 2.0 호출 (캐시 문제 해결됨)
        """
        
        if self.request_count >= self.daily_limit:
            raise RuntimeError("일일 40,000건 API 한도 초과")
        
        # 캐시 확인 (성공한 결과만)
        cache_key = f"{encoded_addr}_{addr_type}"
        if cache_key in self._success_cache:
            print(f"캐시 사용: {encoded_addr}")
            return self._success_cache[cache_key]
        
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
            print(f"API 호출: {encoded_addr} ({addr_type})")
            response = requests.get(self.base_url, params=params, timeout=10)
            self.request_count += 1
            
            if response.status_code != 200:
                print(f"HTTP 에러: {response.status_code}")
                return None
            
            data = response.json()
            
            # 응답 상태 확인
            if data.get("response", {}).get("status") == "OK":
                # result와 point 존재 여부 확인
                result_data = data.get("response", {}).get("result", {})
                point = result_data.get("point", {})
                
                if "x" in point and "y" in point:
                    try:
                        # 좌표 추출
                        longitude = float(point["x"])  # x = 경도
                        latitude = float(point["y"])   # y = 위도
                        
                        print(f"✅ 성공: {encoded_addr} -> ({latitude:.6f}, {longitude:.6f})")
                        
                        # 성공한 결과만 캐시에 저장
                        self._success_cache[cache_key] = (latitude, longitude)
                        
                        return latitude, longitude
                    
                    except (ValueError, TypeError) as e:
                        print(f"❌ 좌표 변환 실패: {point}, 에러: {e}")
                        return None
                else:
                    print(f"❌ 좌표 정보 없음: {point}")
                    return None
            else:
                status = data.get("response", {}).get("status", "UNKNOWN")
                print(f"❌ API 상태 에러: {status}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 네트워크 에러: {e}")
            return None
        except Exception as e:
            print(f"❌ 기타 에러: {e}")
            return None
        
        return None
    
    def geocode_address(self, address: str, optimize: bool = True) -> Tuple[Optional[float], Optional[float], str]:
        """🎯 스마트 지오코딩"""
        
        original_address = address.strip()
        if not original_address:
            return None, None, "UNKNOWN"
        
        print(f"\n🔍 지오코딩 시작: {original_address}")
        
        # 시도할 주소 변형들
        address_variants = [original_address]
        
        if optimize:
            optimized_addr = self.optimize_address(original_address)
            if optimized_addr != original_address:
                print(f"🛠️ 최적화: {original_address} -> {optimized_addr}")
                address_variants.insert(0, optimized_addr)  # 최적화된 주소를 먼저 시도
        
        # 각 주소 변형에 대해 시도
        for variant_idx, addr_variant in enumerate(address_variants):
            print(f"📍 시도 {variant_idx + 1}: {addr_variant}")
            encoded_addr = quote_plus(addr_variant)
            
            # AI가 판별한 타입으로 먼저 시도
            predicted_type = self.analyze_address_type(addr_variant)
            print(f"🤖 AI 예측: {predicted_type}")
            
            result = self._call_api(encoded_addr, predicted_type)
            
            if result:
                print(f"✅ 첫 시도 성공: {predicted_type}")
                return result[0], result[1], predicted_type
            
            time.sleep(self.delay)
            
            # 반대 타입으로 재시도
            fallback_type = "PARCEL" if predicted_type == "ROAD" else "ROAD"
            print(f"🔄 재시도: {fallback_type}")
            
            result = self._call_api(encoded_addr, fallback_type)
            
            if result:
                print(f"✅ 재시도 성공: {fallback_type}")
                return result[0], result[1], fallback_type
            
            time.sleep(self.delay)
        
        print(f"❌ 모든 시도 실패: {original_address}")
        return None, None, "FAILED"
    
    def process_dataframe(self, df: pd.DataFrame, address_column: str, progress_callback=None, optimize_address=True) -> pd.DataFrame:
        """DataFrame 일괄 처리"""
        
        if address_column not in df.columns:
            raise KeyError(f"'{address_column}' 컬럼이 존재하지 않습니다.")
        
        latitudes = []
        longitudes = []
        used_types = []
        predicted_types = []
        optimized_addresses = [] if optimize_address else None
        
        total_rows = len(df)
        
        print(f"\n🚀 지오코딩 시작: 총 {total_rows}건")
        
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
            success_count = sum(1 for lat in latitudes if lat is not None)
            success_rate = (success_count / (idx + 1)) * 100
            print(f"📊 진행률: {idx + 1}/{total_rows} ({(idx + 1)/total_rows*100:.1f}%) - 성공률: {success_rate:.1f}% ({success_count}건 성공)")
        
        print(f"\n🎉 지오코딩 완료!")
        print(f"📊 최종 결과: {sum(1 for lat in latitudes if lat is not None)}/{total_rows}건 성공")
        
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
