[VWorld Geocoder API 2.0 + AI 기반 주소 타입 자동 판별 + 주소 최적화]
- AI가 주소를 확인하고 Geocoder API 2.0를 활용하여 주소정보를 좌표로 변환하는 로컬 서비스
- 기능 : 사용자 엑셀 파일(.xlsx/.csv) 업로드 / 주소가 포함된 특정 열을 지정 / 도로명or지번주소 판별 / 해당 열의 각 주소를 vworld Geocoder API로 위도(x), 경도(y) 조회 / 원본 데이터에 위도(latitude), 경도(longitude) 열 추가 후 결과 다운로드
- 제약 : 일일 최대 요청건수: 40,000건 / 인증키(required): vworld 개발자센터에서 발급 / 좌표계: EPSG:4326 (WGS84)

- project/
- ├── app.py
- ├── geocoding_logic.py
- └── .env (API 인증키)
-
-
[Geocoder API 2.0 레퍼런스]
- 요청URL을 전송하면 지오코딩 서비스를 사용하실 수 있으며 일일 지오코딩 요청건수는 최대 40,000건 입니다.
- 단, API 요청은 실시간으로 사용하셔야 하며 별도의 저장장치나 데이터베이스에 저장할 수 없습니다.
- (출처 : https://www.vworld.kr/dev/v4dv_geocoderguide2_s001.do)
