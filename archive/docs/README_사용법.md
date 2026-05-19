# 네이버 부동산 자동 수집 스크립트 사용 가이드

3가지 버전의 스크립트가 있습니다. **추천 순서대로** 시도해보세요.

---

## 📋 사전 준비

### Python 설치 확인
터미널/명령 프롬프트에서:
```bash
python --version
# 또는
python3 --version
```
Python 3.8 이상이면 OK. 없으면 https://www.python.org/downloads/ 에서 설치.

---

## 🥇 추천 1: Selenium 버전 (가장 안정적)

### 장점
- 실제 Chrome 브라우저로 동작 → 차단 가능성 가장 낮음
- 사람이 보는 것과 동일한 화면을 처리
- 디버깅 쉬움 (창이 떠있어서 어떤 일이 일어나는지 보임)

### 단점
- Chrome 브라우저 필요
- 약간 느림 (단지당 5~10초)

### 사용법

**1단계: 라이브러리 설치**
```bash
pip install selenium webdriver-manager beautifulsoup4
```

**2단계: 스크립트 수정**
`naver_realty_selenium.py` 파일을 열고 `APT_LIST` 부분 수정:
```python
APT_LIST = [
    "하안주공9단지",
    "강서힐스테이트",
    # ... 원하는 단지명 추가
]
```

**3단계: 실행**
```bash
python naver_realty_selenium.py
```

Chrome 창이 자동으로 뜨면서 단지를 하나씩 검색합니다. 

**4단계: 결과 확인**
- `naver_selenium_results.json` - 전체 데이터
- `naver_selenium_results.csv` - 엑셀에서 열 수 있는 CSV

### 잘 되면?
스크립트 안의 `headless=False`를 `headless=True`로 바꾸면 창이 안 뜨고 백그라운드에서 실행됩니다.

---

## 🥈 추천 2: 네이버 부동산 API 버전 (가장 빠름)

### 장점
- 매우 빠름 (단지당 1~2초)
- JSON으로 정확한 데이터 받음
- 평형별 상세 정보 가능

### 단점
- 비공식 API라 변경/차단 위험
- 인증 토큰이 필요할 수 있음

### 사용법

**1단계: 라이브러리 설치**
```bash
pip install requests
```

**2단계: 일단 그냥 실행해보기**
```bash
python naver_realty_api.py
```

**3단계: 토큰 에러 나면 수동 토큰 추출**

크롬에서 다음 단계 수행:
1. https://new.land.naver.com 접속
2. F12 (개발자 도구) 열기
3. Network 탭으로 이동
4. 단지 하나 검색
5. `articles` 또는 `complexes`로 시작하는 요청 클릭
6. Headers 섹션에서 `Authorization: Bearer xxxxx` 값 복사
7. 스크립트의 `auth_token` 변수에 붙여넣기

### 결과
- `naver_realty_api_results.json`
- `naver_realty_api_results.csv`

---

## 🥉 추천 3: 간단 검색 버전 (실패 가능성 있음)

### 장점
- 가장 가벼움 (라이브러리 적음)
- 빠름

### 단점
- 네이버가 정적 HTML에 부동산 카드를 안 넣을 수 있음 → 빈 결과
- 차단 가능성 가장 높음

### 사용법
```bash
pip install requests beautifulsoup4
python naver_realty_v1_simple.py
```

---

## 🔧 트러블슈팅

### "ChromeDriver가 없습니다" 에러
```bash
pip install --upgrade webdriver-manager
```

### 403 Forbidden 에러
- 너무 빠르게 요청해서 차단됨
- 스크립트의 `time.sleep()` 값을 늘리세요 (예: 3초 → 5초)
- VPN 사용 중이면 끄세요

### CAPTCHA가 뜸
- Selenium 버전에서 직접 풀고 계속 진행 가능
- 또는 단지 수를 줄여서 (10개씩) 나눠서 실행

### 빈 결과만 나옴
- 네이버 페이지 구조가 변경됐을 수 있음
- 스크립트의 `extract_realty_card` 함수에서 정규식을 페이지에 맞게 수정 필요
- 또는 저(Claude)에게 실제 페이지 HTML 일부를 보내주시면 수정해드림

### 단지명이 정확히 안 잡힘
- 동일 이름 단지가 여러 곳에 있는 경우
- 단지명을 더 구체적으로 (예: "광명 하안주공9단지" 대신 "광명시 하안동 주공9단지")

---

## 📊 결과물을 Claude에게 공유

1. CSV 또는 JSON 파일 생성됨
2. 파일을 Claude 채팅창에 업로드
3. "이 CSV 데이터를 월부 엑셀 양식에 정확히 채워줘" 요청

Claude가 자동으로:
- 매매가, 전고점, 전저점 등 매핑
- 자동 수식 계산
- 비교 분석

---

## ⚠️ 주의사항

- **개인 용도로만 사용**: 상업적 대량 크롤링은 네이버 약관 위반
- **속도 조절**: 단지 간 최소 1~2초 대기 권장
- **API 변경 가능성**: 네이버가 언제든 페이지 구조나 API를 바꿀 수 있음

문제 발생 시 결과 파일이나 에러 메시지를 Claude에게 공유하시면 디버깅 도와드립니다.
