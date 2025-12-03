# 💧 KODV: 대한민국 가뭄 취약성 지식그래프 지도
> **5-Star Open Data** 모델을 기반으로 구축된, AI 기반 대화형 가뭄 정보 시각화 서비스입니다.

## 📌 프로젝트 소개
이 프로젝트는 공공데이터포털에서 제공하는 국가가뭄정보포털과 한국수자원공사의 가뭄 관련 데이터를 **RDF(Resource Description Framework)** 형태로 변환하고, **Wikidata**와 연결(LOD)하여 구축한 지식그래프를 웹에서 시각화합니다.

단순한 지도 서비스를 넘어, **Gemini AI**를 활용한 자연어 검색과 **SPARQL** 쿼리를 통한 심층 데이터 분석 기능을 제공합니다.

## ✨ 주요 기능
1.  **3단 시맨틱 줌 지도 (Semantic Zooming):**
    * 광역(L1) → 기초(L2) → 읍면동(L3) 레벨별 자동 전환
    * Wikidata 연동을 통한 지역 사진 및 로고 실시간 로딩
2.  **AI 자연어 데이터 검색 (RAG):**
    * "전북에서 가뭄 빈도가 50회 이상인 곳은?"과 같은 자연어 질문 처리
    * Google Gemini 2.5 Flash 모델 탑재
3.  **전문가용 SPARQL 콘솔:**
    * 직접 쿼리를 입력하여 데이터 무결성 검증 및 심화 분석 가능

## 🛠️ 기술 스택 (Tech Stack)
* **Frontend:** HTML5, CSS3, JavaScript (Leaflet.js, Bootstrap 5)
* **Backend:** Python Flask
* **Database:** BlazeGraph (GraphDB / RDF Store)
* **AI Model:** Google Gemini 2.5 Flash
* **Data Format:** Turtle (.ttl), GeoJSON

---

## 🚀 설치 및 실행 방법 (Installation)

### 1. 필수 요구 사항
* Python 3.8 이상
* Java 11 이상 (BlazeGraph 구동용)

### 2. 프로젝트 클론
```bash
git clone [https://github.com/semplicevita/KODV_Project.git](https://github.com/semplicevita/KODV_Project.git)
cd KODV_Project
```

### 3. 라이브러리 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정 (.env)
프로젝트 루트 경로에 `.env` 파일을 생성하고, 발급받은 Google Gemini API 키를 입력합니다.
```bash
GEMINI_API_KEY=AIzaSy...여기에_키를_입력하세요
```

### 5. 데이터베이스(BlazeGraph) 설정
⚠️ 주의: `blazegraph.jar` 파일은 용량 문제로 Git 저장소에 포함되어 있지 않습니다.

1. **다운로드:** BlazeGraph Releases에서 blazegraph.jar (2.1.6) 다운로드 후 루트 폴더에 위치. (https://github.com/blazegraph/database/releases)
2. **DB 실행:** 램할당은 본인 환경에 맞게 하시면 됩니다. (1GB로도 충분)
```bash
java -server -Xmx4g -jar blazegraph.jar
```
3. 데이터 적재:
    * 브라우저에서 http://localhost:9999/blazegraph/ 접속
    * [Update] 탭 클릭 -> KODV_KnowledgeGraph_Final.ttl 파일 업로드

### 6. 웹 서버 실행
새로운 터미널 창을 열고 실행합니다.
```bash
python app.py
```
브라우저에서 http://localhost:80 (또는 설정된 포트)으로 접속하면 서비스가 시작됩니다.

## 📂 폴더 구조 (Directory Structure)
```text
KODV_Project/
├── app.py                          # 메인 Flask 어플리케이션
├── KODV_KnowledgeGraph_Final.ttl   # 핵심 RDF 데이터 파일
├── blazegraph.jar                  # (Git 제외) DB 실행 파일
├── requirements.txt                # Python 의존성 목록
├── .env                            # (Git 제외) API Key 보안 파일
│
├── static/                         # 정적 리소스
│   ├── style.css                   # 커스텀 스타일
│   ├── sido.json                   # L1 광역 지도 (GeoJSON)
│   ├── sig.json                    # L2 기초 지도 (GeoJSON)
│   └── emd.geojson                 # L3 상세 지도 (GeoJSON)
│
└── templates/                      # HTML 템플릿
    └── index.html                  # 메인 UI 페이지
```
