# geocoding_logic.py
import time
from functools import lru_cache
from typing import Optional, Tuple
from urllib.parse import quote_plus

import pandas as pd
import requests


class VWorldGeocoder:
    """
    VWorld Geocoder 2.0 래퍼
    - road → parcel 순으로 2회 시도
    - 요청 캐싱(lru_cache)으로 중복 호출 최소화
    """

    def __init__(self, api_key: str, daily_limit: int = 40_000, sleep: float = 0.1):
        self.api_key = api_key
        self.base_url = "https://api.vworld.kr/req/address"
        self.daily_limit = daily_limit
        self.sleep = sleep
        self.request_count = 0

    # ------------------------------------------------------------------
    # 내부 메서드 : 실제 API 호출 (중복 주소 캐싱)
    # ------------------------------------------------------------------
    @lru_cache(maxsize=10_000)
    def _call_api(self, encoded_addr: str, addr_type: str) -> Optional[Tuple[float, float]]:
        if self.request_count >= self.daily_limit:
            raise RuntimeError("일일 API 요청 한도(40,000건) 초과")

        params = {
            "service": "address",
            "request": "getcoord",
            "version": "2.0",
            "crs": "epsg:4326",
            "address": encoded_addr,
            "format": "json",
            "type": addr_type,      # ★ 반드시 소문자(road, parcel)
            "refine": "true",
            "simple": "false",
            "key": self.api_key,
        }

        r = requests.get(self.base_url, params=params, timeout=10)
        self.request_count += 1

        if r.status_code != 200:
            return None

        data = r.json()
        if data.get("response", {}).get("status") == "OK":
            pt = data["response"]["result"]["point"]
            return float(pt["y"]), float(pt["x"])
        return None

    # ------------------------------------------------------------------
    # 외부 메서드 : 단일 주소 변환
    # ------------------------------------------------------------------
    def geocode_address(self, address: str) -> Tuple[Optional[float], Optional[float]]:
        address = address.strip()
        if not address:
            return None, None

        enc_addr = quote_plus(address)  # 한글 안전처리

        # 도로명 → 지번 순으로 두 번 시도
        for addr_type in ("road", "parcel"):
            result = self._call_api(enc_addr, addr_type)
            if result:
                return result
            time.sleep(self.sleep)  # 짧은 딜레이
        return None, None

    # ------------------------------------------------------------------
    # 외부 메서드 : DataFrame 일괄 변환
    # ------------------------------------------------------------------
    def process_dataframe(self, df: pd.DataFrame, address_column: str) -> pd.DataFrame:
        if address_column not in df.columns:
            raise KeyError(f"'{address_column}' 컬럼이 존재하지 않습니다.")

        latitudes, longitudes = [], []

        for idx, addr in enumerate(df[address_column]):
            if pd.isna(addr) or str(addr).strip() == "":
                lat, lon = None, None
            else:
                lat, lon = self.geocode_address(str(addr))
            latitudes.append(lat)
            longitudes.append(lon)

            # 50건마다 콘솔 진행률 출력
            if (idx + 1) % 50 == 0:
                print(f"[Geocoder] 진행 {idx + 1}/{len(df)}")

            time.sleep(self.sleep)

        result_df = df.copy()
        result_df["latitude"] = latitudes
        result_df["longitude"] = longitudes
        result_df["geocoding_success"] = [lat is not None for lat in latitudes]
        return result_df
