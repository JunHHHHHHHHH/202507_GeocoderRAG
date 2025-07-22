import pandas as pd
import requests
import time
import re
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
import json
import os

class UniversalKoreaGeocoderV3:
    """
    🗺️ 전국 최적화 한국 주소 지오코딩 서비스 v3.0
    - 모든 지역 균등 지원
    - 다단계 폴백 시스템
    - 스마트 주소 변형 생성
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.vworld.kr/req/address"
        self.request_count = 0
        self.daily_limit = 40000
        self.success_count = 0
        self.fail_count = 0
        self._success_cache: Dict[str, Tuple[float, float]] = {}
        
        # 지역별 통계 강화
        self.stats = {
            'total_processed': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'success_geocoding': 0,
            'region_stats': {},
            'fallback_success': 0,
            'optimization_success': 0
        }
        
        print(f"🚀 UniversalKoreaGeocoderV3 초기화 완료")
        print(f"📊 일일 API 한도: {self.daily_limit:,}건")

    def universal_address_optimize(self, address: str) -> List[str]:
        """
        🛠️ 전국 대응 주소 최적화 - 다양한 변형 생성
        """
        variants = []
        address = address.strip()
        
        # 1. 원본 주소
        variants.append(address)
        
        # 2. 기본 정리
        cleaned = re.sub(r'\s+', ' ', address)
        cleaned = re.sub(r'[(),]', '', cleaned)
        if cleaned != address:
            variants.append(cleaned)
        
        # 3. 지역별 표준화 (더 유연하게)
        standardized = self._standardize_by_region(cleaned)
        variants.extend(standardized)
        
        # 4. 세부 주소 단계별 제거
        variants.extend(self._generate_simplified_variants(cleaned))
        
        # 5. 번지/호수 처리 변형
        variants.extend(self._generate_number_variants(cleaned))
        
        # 중복 제거
        unique_variants = []
        for variant in variants:
            if variant and variant.strip() and variant not in unique_variants:
                unique_variants.append(variant)
        
        return unique_variants

    def _standardize_by_region(self, address: str) -> List[str]:
        """지역별 표준화 - 모든 지역 균등 처리"""
        variants = []
        
        # 서울특별시 처리
        if '서울' in address:
            # 서울특별시 -> 서울
            v1 = re.sub(r'서울특별시|서울시', '서울', address)
            variants.append(v1)
            # 서울 제거 버전
            v2 = re.sub(r'서울특별시\s*|서울시\s*|서울\s*', '', address)
            if v2 != address:
                variants.append(v2)
        
        # 광역시 처리 (균등하게)
        metro_cities = ['부산', '대구', '인천', '광주', '대전', '울산']
        for city in metro_cities:
            if city in address:
                # 광역시 제거
                v1 = re.sub(f'{city}광역시|{city}시', city, address)
                variants.append(v1)
                # 도시명도 제거 (구/군 중심)
                v2 = re.sub(f'{city}광역시\s*|{city}시\s*|{city}\s*', '', address)
                if v2 != address:
                    variants.append(v2)
        
        # 경기도 처리
        if '경기' in address:
            v1 = re.sub(r'경기도\s*', '', address)
            variants.append(v1)
            v2 = re.sub(r'경기도\s*', '경기 ', address)
            variants.append(v2)
        
        # 도 단위 지역 처리 (표준화)
        province_mapping = {
            '충청북도': ['충북', '충청북도'],
            '충청남도': ['충남', '충청남도'],
            '전라북도': ['전북', '전라북도', '전라북도특별자치도'],
            '전라남도': ['전남', '전라남도'],
            '경상북도': ['경북', '경상북도'],
            '경상남도': ['경남', '경상남도']
        }
        
        for full_name, alternatives in province_mapping.items():
            for alt in alternatives:
                if alt in address:
                    # 다양한 형태로 변형
                    for target in alternatives:
                        if target != alt:
                            v = address.replace(alt, target)
                            variants.append(v)
                    # 도명 제거 버전
                    v_removed = address.replace(alt, '').strip()
                    if v_removed:
                        variants.append(v_removed)
        
        return variants

    def _generate_simplified_variants(self, address: str) -> List[str]:
        """단계별 간소화 변형 생성"""
        variants = []
        
        # 건물명/아파트명 제거
        simplified = re.sub(r'(아파트|APT|빌라|빌딩|타워|오피스텔|맨션).*$', '', address)
        if simplified != address:
            variants.append(simplified.strip())
        
        # 상세번호 제거 (동호수 등)
        simplified = re.sub(r'\d+동\s*\d+호.*$', '', address)
        if simplified != address:
            variants.append(simplified.strip())
        
        # 층수 정보 제거
        simplified = re.sub(r'\d+층.*$', '', address)
        if simplified != address:
            variants.append(simplified.strip())
        
        return variants

    def _generate_number_variants(self, address: str) -> List[str]:
        """번지/번호 처리 변형"""
        variants = []
        
        # 번지 추가/제거
        if '번지' not in address and re.search(r'\d+(-\d+)?$', address):
            with_bunji = re.sub(r'(\d+(-\d+)?)$', r'\1번지', address)
            variants.append(with_bunji)
        
        if '번지' in address:
            without_bunji = address.replace('번지', '')
            variants.append(without_bunji)
        
        # 산번지 처리
        if '산' in address and '번지' not in address:
            with_bunji = re.sub(r'산(\d+(-\d+)?)$', r'산\1번지', address)
            variants.append(with_bunji)
        
        return variants

    def _get_universal_api_params(self, attempt: int = 1) -> dict:
        """단계별 API 파라미터 - 점진적으로 관대해짐"""
        if attempt == 1:
            return {"refine": "true", "simple": "false"}  # 정밀 검색
        elif attempt == 2:
            return {"refine": "false", "simple": "false"} # 중간 검색
        else:
            return {"refine": "false", "simple": "true"}  # 관대한 검색

    def _detect_region(self, address: str) -> str:
        """지역 감지 개선"""
        address = address.upper()
        
        if '서울' in address:
            return '서울'
        elif any(city in address for city in ['부산', '대구', '인천', '광주', '대전', '울산']):
            for city in ['부산', '대구', '인천', '광주', '대전', '울산']:
                if city in address:
                    return city
        elif '경기' in address:
            return '경기'
        elif any(keyword in address for keyword in ['충북', '충청북']):
            return '충북'
        elif any(keyword in address for keyword in ['충남', '충청남', '홍성']):
            return '충남'
        elif any(keyword in address for keyword in ['전북', '전라북']):
            return '전북'
        elif any(keyword in address for keyword in ['전남', '전라남']):
            return '전남'
        elif any(keyword in address for keyword in ['경북', '경상북']):
            return '경북'
        elif any(keyword in address for keyword in ['경남', '경상남']):
            return '경남'
        else:
            return '기타'

    def analyze_address_type(self, address: str) -> str:
        """개선된 주소 타입 판별"""
        # 확실한 도로명주소
        if re.search(r'.*[로대]\s*\d+(-\d+)?$', address):
            return 'ROAD'
        if re.search(r'.*길\s*\d+(-\d+)?$', address):
            return 'ROAD'
        
        # 확실한 지번주소
        if re.search(r'.*[동리가]\s*\d+(-\d+)?(번지)?$', address):
            return 'PARCEL'
        if re.search(r'.*산\d+(-\d+)?(번지)?$', address):
            return 'PARCEL'
        
        # 키워드 기반 판별
        road_keywords = ['로', '대로', '길', '번길']
        parcel_keywords = ['동', '리', '가', '읍', '면', '번지', '산']
        
        road_score = sum(1 for keyword in road_keywords if keyword in address)
        parcel_score = sum(1 for keyword in parcel_keywords if keyword in address)
        
        return 'PARCEL' if parcel_score > road_score else 'ROAD'

    def _call_api_with_fallback(self, address: str, addr_type: str, debug: bool = False) -> Optional[Tuple[float, float]]:
        """다단계 폴백 API 호출"""
        
        # 캐시 확인
        cache_key = f"{address}_{addr_type}"
        if cache_key in self._success_cache:
            if debug:
                print(f"💾 캐시 히트: {address}")
            self.stats['cache_hits'] += 1
            return self._success_cache[cache_key]
        
        # 3단계 시도 (점진적으로 관대해짐)
        for attempt in range(1, 4):
            if self.request_count >= self.daily_limit:
                raise RuntimeError("일일 API 한도 초과")
            
            params = {
                "service": "address",
                "request": "getCoord",
                "version": "2.0",
                "crs": "epsg:4326",
                "address": address,
                "format": "json",
                "type": addr_type.upper(),
                "key": self.api_key,
                **self._get_universal_api_params(attempt)
            }
            
            try:
                if debug:
                    print(f"📡 API 호출 시도 {attempt}: {address} ({addr_type})")
                
                response = requests.get(self.base_url, params=params, timeout=15)
                self.request_count += 1
                self.stats['api_calls'] += 1
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("response", {}).get("status", "UNKNOWN")
                    
                    if status == "OK":
                        result_data = data.get("response", {}).get("result", {})
                        point = result_data.get("point", {})
                        
                        if "x" in point and "y" in point:
                            try:
                                longitude = float(point["x"])
                                latitude = float(point["y"])
                                
                                # 좌표 유효성 검증
                                if 33.0 <= latitude <= 38.5 and 124.0 <= longitude <= 132.0:
                                    if debug:
                                        print(f"✅ 성공 (시도 {attempt}): {address} -> ({latitude:.6f}, {longitude:.6f})")
                                    
                                    # 성공 결과 캐시
                                    self._success_cache[cache_key] = (latitude, longitude)
                                    
                                    if attempt > 1:
                                        self.stats['fallback_success'] += 1
                                    
                                    return latitude, longitude
                                else:
                                    if debug:
                                        print(f"⚠️ 좌표 범위 벗어남: ({latitude}, {longitude})")
                                    
                            except (ValueError, TypeError):
                                if debug:
                                    print(f"❌ 좌표 변환 실패: {point}")
                
                # 실패시 잠시 대기 (API 부하 방지)
                time.sleep(0.1)
                
            except Exception as e:
                if debug:
                    print(f"❌ 시도 {attempt} 에러: {e}")
                time.sleep(0.1)
        
        return None

    def geocode_address(self, address: str, optimize: bool = True, debug: bool = False) -> Tuple[Optional[float], Optional[float], str]:
        """🎯 전국 최적화 지오코딩"""
        original_address = address.strip()
        if not original_address:
            return None, None, "UNKNOWN"
        
        if debug:
            print(f"\n🔍 지오코딩 시작: {original_address}")
        
        # 통계 업데이트
        self.stats['total_processed'] += 1
        region = self._detect_region(original_address)
        
        if region not in self.stats['region_stats']:
            self.stats['region_stats'][region] = {'total': 0, 'success': 0}
        self.stats['region_stats'][region]['total'] += 1
        
        if debug:
            print(f"🗺️ 감지된 지역: {region}")
        
        # 주소 타입 판별
        detected_type = self.analyze_address_type(original_address)
        if debug:
            print(f"🤖 판별된 주소 타입: {detected_type}")
        
        # 주소 변형 생성
        if optimize:
            variants = self.universal_address_optimize(original_address)
        else:
            variants = [original_address]
        
        if debug:
            print(f"🔄 생성된 주소 변형 ({len(variants)}개):")
            for i, variant in enumerate(variants, 1):
                print(f"  {i}. {variant}")
        
        # 1단계: 예측된 타입으로 시도
        for variant in variants:
            result = self._call_api_with_fallback(variant, detected_type, debug)
            if result:
                self.success_count += 1
                self.stats['success_geocoding'] += 1
                self.stats['region_stats'][region]['success'] += 1
                
                if variant != original_address:
                    self.stats['optimization_success'] += 1
                
                if debug:
                    print(f"✅ 성공! 사용된 주소: {variant} (타입: {detected_type})")
                return result[0], result[1], detected_type
        
        # 2단계: 대체 타입으로 시도
        alternative_type = 'PARCEL' if detected_type == 'ROAD' else 'ROAD'
        if debug:
            print(f"🔄 대체 타입으로 재시도: {alternative_type}")
        
        for variant in variants:
            result = self._call_api_with_fallback(variant, alternative_type, debug)
            if result:
                self.success_count += 1
                self.stats['success_geocoding'] += 1
                self.stats['region_stats'][region]['success'] += 1
                
                if variant != original_address:
                    self.stats['optimization_success'] += 1
                
                if debug:
                    print(f"✅ 성공! 사용된 주소: {variant} (타입: {alternative_type})")
                return result[0], result[1], alternative_type
        
        # 실패
        self.fail_count += 1
        if debug:
            print(f"❌ 실패: 모든 변형과 타입으로 시도했으나 변환 실패")
        
        return None, None, detected_type

    def process_dataframe(self, df: pd.DataFrame, address_column: str, 
                         progress_callback=None, optimize_address=True) -> pd.DataFrame:
        """📊 DataFrame 일괄 처리"""
        print(f"🚀 전국 최적화 지오코딩 시작")
        print(f"📝 총 {len(df)}건의 주소 처리 예정")
        
        latitudes = []
        longitudes = []
        used_types = []
        optimized_addresses = []
        
        start_time = time.time()
        
        for idx, row in df.iterrows():
            addr = row[address_column]
            
            if pd.isna(addr):
                latitudes.append(None)
                longitudes.append(None)
                used_types.append("UNKNOWN")
                optimized_addresses.append(None)
                continue
            
            lat, lon, used_type = self.geocode_address(str(addr), optimize=optimize_address)
            
            latitudes.append(lat)
            longitudes.append(lon)
            used_types.append(used_type)
            optimized_addresses.append(str(addr))  # 원본 주소 저장
            
            # 진행률 콜백
            if progress_callback:
                progress_callback(idx + 1, len(df))
            
            # 진행률 출력
            if (idx + 1) % 50 == 0:  # 더 자주 업데이트
                elapsed_time = time.time() - start_time
                rate = (idx + 1) / elapsed_time
                remaining_time = (len(df) - idx - 1) / rate if rate > 0 else 0
                success_rate = self.success_count / (idx + 1) * 100
                
                print(f"⏳ 진행률: {idx + 1}/{len(df)} ({((idx + 1)/len(df)*100):.1f}%) "
                      f"| 성공률: {success_rate:.1f}% "
                      f"| 예상 완료: {remaining_time/60:.1f}분")
        
        # 결과 DataFrame 생성
        result_df = df.copy()
        result_df['latitude'] = latitudes
        result_df['longitude'] = longitudes  
        result_df['geocoding_success'] = [lat is not None for lat in latitudes]
        result_df['ai_predicted_type'] = used_types
        result_df['actual_used_type'] = used_types
        
        if optimize_address:
            result_df['optimized_address'] = optimized_addresses
        
        # 최종 통계
        total_time = time.time() - start_time
        success_rate = self.success_count / len(df) * 100
        
        print(f"\n🎉 전국 최적화 지오코딩 완료!")
        print(f"⏱️ 총 소요시간: {total_time/60:.1f}분")
        print(f"📊 전체 성공률: {success_rate:.1f}%")
        print(f"🔗 총 API 호출: {self.stats['api_calls']}회")
        print(f"💾 캐시 효율성: {self.stats['cache_hits']}회")
        print(f"🔄 폴백 성공: {self.stats['fallback_success']}회")
        print(f"🛠️ 최적화 성공: {self.stats['optimization_success']}회")
        
        # 지역별 상세 통계
        print(f"\n📊 지역별 성공률:")
        for region, stats in self.stats['region_stats'].items():
            region_rate = (stats['success'] / stats['total']) * 100 if stats['total'] > 0 else 0
            print(f"  {region}: {stats['success']}/{stats['total']} ({region_rate:.1f}%)")
        
        return result_df

    def get_statistics(self) -> Dict[str, Any]:
        """📈 상세 통계 정보 반환"""
        return {
            'total_processed': self.stats['total_processed'],
            'success_geocoding': self.stats['success_geocoding'],
            'success_rate': (self.stats['success_geocoding'] / max(self.stats['total_processed'], 1)) * 100,
            'api_calls': self.stats['api_calls'],
            'cache_hits': self.stats['cache_hits'],
            'cache_efficiency': (self.stats['cache_hits'] / max(self.stats['api_calls'] + self.stats['cache_hits'], 1)) * 100,
            'region_stats': self.stats['region_stats'],
            'remaining_api_calls': self.daily_limit - self.request_count,
            'fallback_success': self.stats['fallback_success'],
            'optimization_success': self.stats['optimization_success']
        }

# 기존 클래스명 호환성을 위한 별칭
VWorldGeocoder = UniversalKoreaGeocoderV3
KoreaGeocoderV2 = UniversalKoreaGeocoderV3

# 사용 예시
if __name__ == "__main__":
    API_KEY = "여기에_실제_API_키를_입력하세요"
    
    # 전국 대응 지오코더 초기화
    geocoder = UniversalKoreaGeocoderV3(API_KEY)
    
    # 전국 테스트 주소
    test_addresses = [
        "서울특별시 강남구 테헤란로 152",
        "부산광역시 해운대구 해운대해변로 264", 
        "경기도 성남시 분당구 판교역로 235",
        "충청북도 청주시 상당구 상당로 82",
        "충청남도 홍성군 홍성읍 오관리 254",
        "전라북도 전주시 완산구 전주천동로 20",
        "전라남도 목포시 해안로 249",
        "경상북도 경주시 첨성로 169",
        "경상남도 창원시 의창구 원이대로 362"
    ]
    
    print("🧪 전국 주소 테스트")
    print("=" * 70)
    
    for addr in test_addresses:
        lat, lon, addr_type = geocoder.geocode_address(addr, debug=True)
        if lat and lon:
            print(f"✅ {addr}")
            print(f"   -> ({lat:.6f}, {lon:.6f}) [{addr_type}]")
        else:
            print(f"❌ {addr} -> 변환 실패")
        print("-" * 50)
    
    # 최종 통계
    stats = geocoder.get_statistics()
    print(f"\n📈 최종 통계:")
    print(f"성공률: {stats['success_rate']:.1f}%")
    print(f"폴백 성공: {stats['fallback_success']}회")
    print(f"최적화 성공: {stats['optimization_success']}회")
