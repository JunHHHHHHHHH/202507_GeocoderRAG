# geocoding_logic.py
import requests
import pandas as pd
import time
from typing import Tuple, List, Optional

class VWorldGeocoder:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.vworld.kr/req/address"
        self.request_count = 0
        self.daily_limit = 40000
    
    def geocode_address(self, address: str, address_type: str = "PARCEL") -> Tuple[Optional[float], Optional[float]]:
        """단일 주소를 위도, 경도로 변환"""
        if self.request_count >= self.daily_limit:
            raise Exception("일일 API 요청 한도 초과")
        
        params = {
            "service": "address",
            "request": "getcoord",
            "version": "2.0",
            "crs": "epsg:4326",
            "address": address,
            "format": "json",
            "type": address_type,
            "key": self.api_key
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            self.request_count += 1
            
            if response.status_code == 200:
                data = response.json()
                if data.get("response", {}).get("status") == "OK":
                    point = data["response"]["result"]["point"]
                    return float(point.get("y")), float(point.get("x"))  # 위도, 경도
            
            # PARCEL로 실패시 ROAD 타입으로 재시도
            if address_type == "PARCEL":
                time.sleep(0.1)  # API 호출 간격
                return self.geocode_address(address, "ROAD")
                
        except Exception as e:
            print(f"Geocoding 오류 ({address}): {str(e)}")
        
        return None, None
    
    def process_dataframe(self, df: pd.DataFrame, address_column: str) -> pd.DataFrame:
        """데이터프레임의 주소 컬럼을 일괄 변환"""
        result_df = df.copy()
        latitudes = []
        longitudes = []
        success_count = 0
        
        for idx, address in enumerate(df[address_column]):
            if pd.isna(address) or str(address).strip() == "":
                lat, lon = None, None
            else:
                lat, lon = self.geocode_address(str(address).strip())
                if lat is not None and lon is not None:
                    success_count += 1
            
            latitudes.append(lat)
            longitudes.append(lon)
            
            # 진행상황 표시
            if (idx + 1) % 10 == 0:
                print(f"진행: {idx + 1}/{len(df)} ({success_count}건 성공)")
            
            time.sleep(0.1)  # API 호출 간격
        
        result_df['latitude'] = latitudes
        result_df['longitude'] = longitudes
        result_df['geocoding_success'] = [lat is not None for lat in latitudes]
        
        return result_df
