[VWorld Geocoder API 2.0 + AI 기반 주소 타입 자동 판별 + 주소 최적화]
- AI가 주소를 확인하고 이 주소정보를 좌표로 변환하는 로컬 서비스 
- Geocoder API 2.0 레퍼런스를 활용하여 주소를 좌표로 변환 

[Geocoder API 2.0 레퍼런스]
- 요청URL을 전송하면 지오코딩 서비스를 사용하실 수 있으며 일일 지오코딩 요청건수는 최대 40,000건 입니다.
- 단, API 요청은 실시간으로 사용하셔야 하며 별도의 저장장치나 데이터베이스에 저장할 수 없습니다.
- (출처 : https://www.vworld.kr/dev/v4dv_geocoderguide2_s001.do)
- V-WORLD 디지털트윈국토에 회원가입 후 해당 API 인증키를 발급 받아야 함.

- project/
├── app.py
├── geocoding_logic.py
└── .env (API 인증키)
