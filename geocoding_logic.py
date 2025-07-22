import re
import time
from typing import Optional, Tuple, List
from urllib.parse import quote_plus
import pandas as pd
import requests

class VWorldGeocoder:
    """
    VWorld Geocoder API 2.0 + AI 기반 주소 타입 자동 판별 + 번지 추가 최적화
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
            r'.*[로대길]\s*\d+',
            r'.*[로대].*길\s*\d+',
            r'.*로\d+번길\s*\d+',
            r'.*대로\d+길\s*\d+',
            r'.*길\s*\d+(-\d+)?$',
        ]
        
        # 지번주소 패턴
        self.parcel_patterns = [
            r'.*[동리가]\s*\d+(-\d+)?$',
            r'.*[동리가]\s*\d+번지',
            r'.*[동리가]\s*산\d+(-\d+)?',
            r'.*[읍면]\s+.*[동리]\s*\d+',
        ]
        
        # 도로명 키워드
        self.road_keywords = ['로', '대로', '길', '번길', '가길']
        
        # 지번 키워드
        self.parcel_keywords = ['동', '리', '가', '읍', '면', '번지', '산']
    
    def optimize_address(self, address: str) -> str:
        """
        🛠️ 기본 주소 최적화
        """
        address = address.strip()
        
        # 기본 정리
        address = re.sub(r'\s+', ' ', address)
        
        # 불필요한 행정구역명 제거
        unnecessary_words = ['특별시', '광역시', '특별자치시', '특별자치도']
        for word in unnecessary_words:
            address = address.replace(word, '')
        
        return address.strip()
    
    def generate_address_variants(self, address: str, addr_type: str) -> List[str]:
        """
        🔄 간소화된 주소 변형 생성 (원본 + 번지 추가만)
        """
        variants = []
        original = address.strip()
        
        # 1. 원본 주소
        variants.append(original)
        
        # 2. 지번주소인 경우 번지 추가
        if addr_type == 'PARCEL':
            # 마지막 숫자 뒤에 '번지' 추가
            # '충청남도 홍성군 홍성읍 오관리 254' → '충청남도 홍성군 홍성읍 오관리 254번지'
            # '충청남도 홍성군 홍성읍 오관리 296-5' → '충청남도 홍성군 홍성읍 오관리 296-5번지'
            
            # 이미 '번지'가 있는지 확인
            if not re.search(r'\d+(-\d+)?번지', original):
                # 마지막 숫자 패턴 찾기
                number_match = re.search(r'(\d+(-\d+)?)$', original)
                if number_match:
                    with_bunji = re.sub(r'(\d+(-\d+)?)$', r'\1번지', original)
                    if with_bunji != original:
                        variants.append(with_bunji)
        
        # 중복 제거
        unique_variants = []
        for variant in variants:
            if variant and variant.strip() and variant not in unique_variants:
                unique_variants.append(variant)
        
        return unique_variants
    
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
        return 'PARCEL' if parcel_score >= road_score else 'ROAD'
    
    def _call_api(self, address: str, addr_type: str, debug: bool = False) -> Optional[Tuple[float, float]]:
        """VWorld API 2.0 호출 (수정된 버전)"""
        
        if self.request_count >= self.daily_limit:
            raise RuntimeError("일일 40,000건 API 한도 초과")
        
        # 캐시 확인
        cache_key = f"{address}_{addr_type}"
        if cache_key in self._success_cache:
            if debug:
                print(f"💾 캐시 사용: {address}")
            return self._success_cache[cache_key]
        
        params = {
            "service": "address",
            "request": "getCoord",
            "version": "2.0",
            "crs": "epsg:4326",
            "address": address,  # URL 인코딩 없이 직접 전달
            "format": "json",
            "type": addr_type.upper(),
            "refine": "true",
            "simple": "false",
            "key": self.api_key,
        }
        
        try:
            if debug:
                print(f"📡 API 호출: {address} ({addr_type})")
            
            response = requests.get(self.base_url, params=params, timeout=10)
            self.request_count += 1
            
            if response.status_code != 200:
                if debug:
                    print(f"❌ HTTP 에러: {response.status_code}")
                return None
            
            data = response.json()
            
            if debug:
                print(f"📋 API 응답: {data}")
            
            # 응답 상태 확인
            status = data.get("response", {}).get("status", "UNKNOWN")
            
            if status == "OK":
                # result와 point 존재 여부 확인
                result_data = data.get("response", {}).get("result", {})
                point = result_data.get("point", {})
                
                if "x" in point and "y" in point:
                    try:
                        longitude = float(point["x"])  # x = 경도
                        latitude = float(point["y"])   # y = 위도
                        
                        if debug:
                            print(f"✅ 성공: {address} -> ({latitude:.6f}, {longitude:.6f})")
                        
                        # 성공한 결과만 캐시에 저장
                        self._success_cache[cache_key] = (latitude, longitude)
                        
                        return latitude, longitude
                    
                    except (ValueError, TypeError) as e:
                        if debug:
                            print(f"❌ 좌표 변환 실패: {point}, 에러: {e}")
                        return None
                else:
                    if debug:
                        print(f"❌ 좌표 정보 없음")
                    return None
            
            elif status == "NOT_FOUND":
                if debug:
                    print(f"❌ 주소 찾을 수 없음")
                return None
            else:
                if debug:
                    print(f"❌ API 상태 에러: {status}")
                return None
                
        except requests.exceptions.RequestException as e:
            if debug:
                print(f"❌ 네트워크 에러: {e}")
            return None
        except Exception as e:
            if debug:
                print(f"❌ 기타 에러: {e}")
            return None
        
        return None
    
    def geocode_address(self, address: str, optimize: bool = True, debug: bool = False) -> Tuple[Optional[float], Optional[float], str]:
        """🎯 스마트 지오코딩 - 번지 추가 + URL 인코딩 수정"""
        
        original_address = address.strip()
        if not original_address:
            return None, None, "UNKNOWN"
        
        if debug:
            print(f"\n🔍 지오코딩 시작: {original_address}")
        
        # AI로 주소 타입 먼저 판별
        predicted_type = self.analyze_address_type(original_address)
        if debug:
            print(f"🤖 AI 예측: {predicted_type}")
        
        # 주소 변형 생성 (원본 + 번지 추가)
        address_variants = self.generate_address_variants(original_address, predicted_type)
        if debug:
            print(f"🔄 생성된 변형: {len(address_variants)}개")
            for i, variant in enumerate(address_variants):
                print(f"  {i+1}. {variant}")
        
        for variant_idx, addr_variant in enumerate(address_variants):
            if debug:
                print(f"\n📍 변형 {variant_idx + 1}/{len(address_variants)}: {addr_variant}")
            
            # 예측된 타입으로 먼저 시도
            result = self._call_api(addr_variant, predicted_type, debug=debug)
            
            if result:
                if debug:
                    print(f"🎉 성공! 변형 {variant_idx + 1}에서 {predicted_type}으로 성공")
                return result[0], result[1], predicted_type
            
            time.sleep(self.delay)
            
            # 반대 타입으로 재시도
            fallback_type = "PARCEL" if predicted_type == "ROAD" else "ROAD"
            if debug:
                print(f"🔄 재시도: {fallback_type}")
            
            result = self._call_api(addr_variant, fallback_type, debug=debug)
            
            if result:
                if debug:
                    print(f"🎉 성공! 변형 {variant_idx + 1}에서 {fallback_type}으로 성공")
                return result[0], result[1], fallback_type
            
            time.sleep(self.delay)
        
        if debug:
            print(f"💥 모든 변형 실패: {original_address}")
        return None, None, "FAILED"
    
    def process_dataframe(self, df: pd.DataFrame, address_column: str, progress_callback=None, optimize_address=True) -> pd.DataFrame:
        """DataFrame 일괄 처리"""
        
        if address_column not in df.columns:
            raise KeyError(f"'{address_column}' 컬럼이 존재하지 않습니다.")
        
        latitudes = []
        longitudes = []
        used_types = []
        predicted_types = []
        successful_variants = []
        
        total_rows = len(df)
        
        print(f"\n🚀 지오코딩 시작: 총 {total_rows}건")
        
        for idx, addr in enumerate(df[address_column]):
            if pd.isna(addr):
                lat, lon, used_type = None, None, "UNKNOWN"
                predicted_type = "UNKNOWN"
                successful_variant = "빈 주소"
            else:
                original_addr = str(addr)
                predicted_type = self.analyze_address_type(original_addr)
                
                # 첫 번째와 마지막 주소는 디버그 모드로 실행
                debug_mode = (idx == 0 or idx == total_rows - 1)
                
                # 실제 지오코딩 수행
                lat, lon, used_type = self.geocode_address(
                    original_addr,
                    optimize=optimize_address,
                    debug=debug_mode
                )
                
                # 성공한 경우 기록
                if lat is not None:
                    successful_variant = f"성공 ({used_type})"
                else:
                    successful_variant = "실패"
            
            latitudes.append(lat)
            longitudes.append(lon)
            used_types.append(used_type)
            predicted_types.append(predicted_type)
            successful_variants.append(successful_variant)
            
            # 진행률 콜백 호출
            if progress_callback:
                progress_callback(idx + 1, total_rows)
            
            # 콘솔 진행률 표시
            success_count = sum(1 for lat in latitudes if lat is not None)
            success_rate = (success_count / (idx + 1)) * 100
            
            if idx == 0 or (idx + 1) % 3 == 0 or (idx + 1) == total_rows:
                print(f"\n📊 진행률: {idx + 1}/{total_rows} ({(idx + 1)/total_rows*100:.1f}%) - 성공률: {success_rate:.1f}% ({success_count}건 성공)")
            
            # API 과부하 방지
            if idx < total_rows - 1:
                time.sleep(0.2)
        
        print(f"\n🎉 지오코딩 완료!")
        print(f"📊 최종 결과: {sum(1 for lat in latitudes if lat is not None)}/{total_rows}건 성공")
        
        # 결과 DataFrame 생성
        result_df = df.copy()
        result_df["latitude"] = latitudes
        result_df["longitude"] = longitudes
        result_df["geocoding_success"] = [lat is not None for lat in latitudes]
        result_df["ai_predicted_type"] = predicted_types
        result_df["actual_used_type"] = used_types
        result_df["result_status"] = successful_variants
        
        # 최적화된 주소 컬럼도 추가 (app.py 호환성)
        if optimize_address:
            optimized_addresses = [self.optimize_address(str(addr)) if pd.notna(addr) else None 
                                 for addr in df[address_column]]
            result_df["optimized_address"] = optimized_addresses
        
        return result_df
