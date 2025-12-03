import os
from flask import Flask, render_template, jsonify, request
from SPARQLWrapper import SPARQLWrapper, JSON
import requests
import google.generativeai as genai
from dotenv import load_dotenv
import json

# 1. 환경변수 로드
load_dotenv()

# 2. Gemini 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

app = Flask(__name__)
BLAZEGRAPH_URL = "http://localhost:9999/blazegraph/namespace/kb/sparql"
sparql = SPARQLWrapper(BLAZEGRAPH_URL)

# --- ★ 시스템 프롬프트 (모든 네임스페이스 반영) ---
SYSTEM_PROMPT = SYSTEM_PROMPT = """
You are an expert SPARQL query generator for the 'KODV (Korea Drought Vulnerability)' Knowledge Graph.
Convert natural language questions into valid SPARQL 1.1 queries based on the ontology below.

### 1. Output Format (STRICT)
- Return **ONLY** a JSON object: `{"sparql": "SELECT ..."}`
- **NO** markdown code blocks (```json), **NO** explanations.
- **DO NOT** include `PREFIX` definitions in the output string (The system adds them automatically). Start with `SELECT`.

### 2. Namespace & Schema
- **Prefixes (Context):** kodv, koad, kodvid, rdfs, skos
- **Hierarchy:** L1 (Province) -> L2 (City/County/District) -> L3 (Eup/Myeon/Dong)
- **Relationship:** `?child koad:isNeighborhoodOf|koad:isTownOf|koad:isTownshipOf|koad:isDistrictOf|koad:isCityOf|koad:isCountyOf ?parent`
- **Data Location:** All drought properties exist **ONLY on L3 (Eup/Myeon/Dong)** nodes.

### 3. Property & Variable Mapping (CRITICAL)
You **MUST** use the exact **Variable Name** defined below for the frontend to render icons correctly.

| Keyword (Korean) | Property URI | Required Variable Name |
| :--- | :--- | :--- |
| **인구** | `kodv:population` | `?population` |
| **급수율** | `kodv:waterSupplyRate` | `?waterSupplyRate` |
| **급수인구** | `kodv:waterSupplyPopulation` | `?waterSupplyPopulation` |
| **평균가뭄심도** | `kodv:droughtSeverityAvg` | `?droughtSeverityAvg` |
| **가뭄빈도** | `kodv:droughtFrequency` | `?droughtFrequency` |
| **가뭄노출도** | `kodv:droughtExposureScore` | `?droughtExposureScore` |
| **노출도계수** | `kodv:exposureCoefficient` | `?exposureCoefficient` |
| **생활용수** | `kodv:domesticWaterUsage` | `?domesticWaterUsage` |
| **공업용수** | `kodv:industrialWaterUsage` | `?industrialWaterUsage` |
| **생공용수** | `kodv:livingIndustrialWaterUsage` | `?livingIndustrialWaterUsage` |
| **민감도계수** | `kodv:sensitivityCoefficient` | `?sensitivityCoefficient` |
| **저수지용량** | `kodv:reservoirCapacity` | `?reservoirCapacity` |
| **지하수량** | `kodv:groundwaterAvailable` | `?groundwaterAvailable` |
| **보조수원능력** | `kodv:auxWaterSourceCapacity` | `?auxWaterSourceCapacity` |
| **보조수원계수** | `kodv:auxWaterSourceCoefficient` | `?auxWaterSourceCoefficient` |
| **공급가능일수** | `kodv:waterSupplyAvailableDays` | `?waterSupplyAvailableDays` |
| **대응능력계수** | `kodv:responseCapacityCoefficient` | `?responseCapacityCoefficient` |
| **취약성점수** | `kodv:vulnerabilityScore` | `?vulnerabilityScore` |
| **취약성등급(수치)** | `kodv:vulnerabilityRatingNumeric` | `?vulnerabilityRatingNumeric` |
| **취약성등급(URI)** | `kodv:vulnerabilityRating` | `?vulnerabilityRating` |

### 4. Query Strategies

**Type A: List & Highlight (Find specific L3 regions)**
- **Goal:** Find L3 regions satisfying a condition.
- **Select:** `?name`, `?code`, and the **Specific Variable** (e.g., `?population`).
- **Pattern:** 1. Identify target L3 nodes (`koad:Dong`, `koad:Eup`, `koad:Myeon`).
  2. Filter by parent region name using recursive path `+`.
  3. Filter by value condition.
- **Sort/Limit:** Always apply `ORDER BY` and `LIMIT` (default 20) if asking for "Top/Bottom" or "List".

**Type B: Aggregation (Average, Sum, Max, Min)**
- **Goal:** Calculate statistics for a larger area (L1 or L2).
- **Target:** First, find all child L3 nodes. Then aggregate their values.
- **Calculation:**
  - "Average Vulnerability Grade": Use `AVG(?val)` on `kodv:vulnerabilityRatingNumeric`.
  - "Total Population": Use `SUM(?val)` on `kodv:population`.
- **Select:** `(AVG(?var) AS ?result)`. DO NOT select `?name` or `?code` of L3 nodes in aggregation mode.

### 5. Administrative Name Expansion
- "서울" -> "서울특별시" / "경기" -> "경기도" / "충남" -> "충청남도" / "충북" -> "충청북도"
- "전남" -> "전라남도" / "전북" -> "전북특별자치도" / "경남" -> "경상남도" / "경북" -> "경상북도"
- "강원" -> "강원특별자치도" / "제주" -> "제주특별자치도"

### 6. Few-Shot Examples

**User:** "충남에서 인구가 3만 명을 넘는 곳은?"
**Response:**
{ "sparql": "SELECT ?name ?code ?population WHERE { ?s a ?type . VALUES ?type { koad:Dong koad:Eup koad:Myeon } . ?s rdfs:label ?name ; koad:divisionCode ?code ; kodv:population ?population . ?s (koad:isNeighborhoodOf|koad:isTownOf|koad:isTownshipOf|koad:isDistrictOf|koad:isCityOf|koad:isCountyOf)+ ?parent . ?parent rdfs:label ?pName . FILTER(CONTAINS(?pName, '충청남도') && ?population > 30000) } ORDER BY DESC(?population) LIMIT 30" }

**User:** "전국에서 급수율이 낮은 지역 하위 20곳을 알려줘"
**Response:**
{ "sparql": "SELECT ?name ?code ?waterSupplyRate WHERE { ?s a ?type . VALUES ?type { koad:Dong koad:Eup koad:Myeon } . ?s rdfs:label ?name ; koad:divisionCode ?code ; kodv:waterSupplyRate ?waterSupplyRate . } ORDER BY ASC(?waterSupplyRate) LIMIT 20" }

**User:** "서울의 평균 취약성 등급은?"
**Response:**
{ "sparql": "SELECT (ROUND(AVG(?tempVal)) AS ?vulnerabilityRatingNumeric) WHERE { ?s a ?type . VALUES ?type { koad:Dong koad:Eup koad:Myeon } . ?s kodv:vulnerabilityRatingNumeric ?tempVal . ?s (koad:isNeighborhoodOf|koad:isTownOf|koad:isTownshipOf|koad:isDistrictOf|koad:isCityOf|koad:isCountyOf)+ ?parent . ?parent rdfs:label ?pName . FILTER(CONTAINS(?pName, '서울특별시')) }" }
"""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/existing-codes')
def get_existing_codes():
    try:
        query = """
        PREFIX koad: <http://vocab.datahub.kr/def/administrative-division/>
        SELECT DISTINCT ?code WHERE { ?s koad:divisionCode ?code . }
        """
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        codes = set()
        for result in results['results']['bindings']:
            full_code = result['code']['value']
            if len(full_code) >= 2: codes.add(full_code[:2])
            if len(full_code) >= 5: codes.add(full_code[:5])
        return jsonify(list(codes))
    except: return jsonify([])

@app.route('/api/data/<region_code>')
def get_region_data(region_code):
    try:
        # [수정 1] 로컬 DB 조회 (19종 속성 전체 + 라벨 + WikiURI)
        # koad 관계 속성은 팝업 표출용이 아니므로 제외하여 성능 최적화
        query = f"""
        PREFIX kodv: <https://knowledgemap.kr/kodv/def/>
        PREFIX kodvid: <https://knowledgemap.kr/kodv/id/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

        SELECT * WHERE {{
            # URI 생성: 사용자가 클릭한 코드로 직접 리소스 URI 바인딩
            BIND(IRI(CONCAT("https://knowledgemap.kr/kodv/id/", "{region_code}")) AS ?region)
            
            # [기본] 이름, 위키URI
            OPTIONAL {{ ?region rdfs:label ?label . }}
            OPTIONAL {{ ?region owl:sameAs ?wikiURI . }}
            
            # [1] 급수 인구 정보
            OPTIONAL {{ ?region kodv:population ?population . }}
            OPTIONAL {{ ?region kodv:waterSupplyRate ?waterSupplyRate . }}
            OPTIONAL {{ ?region kodv:waterSupplyPopulation ?waterSupplyPopulation . }}
            
            # [2] 노출도
            OPTIONAL {{ ?region kodv:droughtSeverityAvg ?droughtSeverityAvg . }}
            OPTIONAL {{ ?region kodv:droughtFrequency ?droughtFrequency . }}
            OPTIONAL {{ ?region kodv:droughtExposureScore ?droughtExposureScore . }}
            OPTIONAL {{ ?region kodv:exposureCoefficient ?exposureCoefficient . }}
            
            # [3] 민감도
            OPTIONAL {{ ?region kodv:domesticWaterUsage ?domesticWaterUsage . }}
            OPTIONAL {{ ?region kodv:industrialWaterUsage ?industrialWaterUsage . }}
            OPTIONAL {{ ?region kodv:livingIndustrialWaterUsage ?livingIndustrialWaterUsage . }}
            OPTIONAL {{ ?region kodv:sensitivityCoefficient ?sensitivityCoefficient . }}
            
            # [4] 보조수원
            OPTIONAL {{ ?region kodv:reservoirCapacity ?reservoirCapacity . }}
            OPTIONAL {{ ?region kodv:groundwaterAvailable ?groundwaterAvailable . }}
            OPTIONAL {{ ?region kodv:auxWaterSourceCapacity ?auxWaterSourceCapacity . }}
            OPTIONAL {{ ?region kodv:auxWaterSourceCoefficient ?auxWaterSourceCoefficient . }}
            
            # [5] 대응능력
            OPTIONAL {{ ?region kodv:waterSupplyAvailableDays ?waterSupplyAvailableDays . }}
            OPTIONAL {{ ?region kodv:responseCapacityCoefficient ?responseCapacityCoefficient . }}
            
            # [6] 취약성 (점수, 등급URI -> 라벨)
            OPTIONAL {{ ?region kodv:vulnerabilityScore ?vulScore . }}
            OPTIONAL {{ ?region kodv:vulnerabilityRatingNumeric ?vulnerabilityRatingNumeric . }}
            OPTIONAL {{ 
                ?region kodv:vulnerabilityRating ?ratingUri .
                ?ratingUri skos:prefLabel ?gradeLabel . 
            }}
        }} LIMIT 1
        """
        
        sparql = SPARQLWrapper(BLAZEGRAPH_URL) # 전역 변수 BLAZEGRAPH_URL 사용 가정
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)
        local_results = sparql.query().convert()
        bindings = local_results['results']['bindings']
        
        if not bindings:
            return jsonify({"status": "empty", "message": "해당 지역 코드의 데이터가 없습니다."})
        
        data = bindings[0]
        
        # [수정 2] 위키데이터 조회 (이미지 6종 파이프 연산자 검색)
        if 'wikiURI' in data:
            wiki_url = data['wikiURI']['value']
            
            # 파이프(|) 사용: P18(이미지)|P154(로고)|P94(인장)|P41(기)|P242(지도)|P948(배너)
            # 순서는 위키데이터가 먼저 발견하는 순서입니다.
            wiki_sparql = f"""
            PREFIX wdt: <http://www.wikidata.org/prop/direct/>
            PREFIX schema: <http://schema.org/>
            
            SELECT ?image ?desc WHERE {{
                <{wiki_url}> wdt:P18|wdt:P154|wdt:P94|wdt:P41|wdt:P242|wdt:P948 ?image .
                OPTIONAL {{ <{wiki_url}> schema:description ?desc . FILTER(LANG(?desc) = "ko") }}
            }} LIMIT 1
            """
            
            try:
                response = requests.get(
                    "https://query.wikidata.org/sparql", 
                    params={'query': wiki_sparql, 'format': 'json'},
                    headers={'User-Agent': 'KODV_Project_Bot/1.0'},
                    timeout=2  # 타임아웃 2초 (응답 지연 방지)
                )
                if response.status_code == 200:
                    wiki_data = response.json()['results']['bindings']
                    if wiki_data:
                        if 'image' in wiki_data[0]: data['image'] = wiki_data[0]['image']
                        if 'desc' in wiki_data[0]: data['desc'] = wiki_data[0]['desc']
            except Exception as e:
                # 위키데이터 에러는 무시하고(이미지 없이) 로컬 데이터만 반환
                print(f"Wikidata Fetch Error: {e}")
                pass

        return jsonify({"status": "success", "data": data})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
@app.route('/api/ask', methods=['POST'])
def ask_ai():
    try:
        user_question = request.json.get('question')
        if not user_question: return jsonify({"status": "error", "message": "질문 없음"})

        print(f"🗣️ 질문: {user_question}")

        # 1. Gemini 호출 (JSON 포맷 강제)
        # 프롬프트 끝에 "JSON Format:"을 명시하여 AI가 JSON으로 시작하도록 유도
        prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_question}\nOutput JSON:"
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        
        sparql_query = ""

        # 2. 결과 파싱 (JSON 추출 시도 -> 실패 시 텍스트 그대로 사용)
        # 마크다운 제거 (```json, ```sparql 등)
        clean_text = raw_text.replace("```json", "").replace("```sparql", "").replace("```", "").strip()
        
        try:
            # JSON 파싱 시도
            ai_data = json.loads(clean_text)
            sparql_query = ai_data.get("sparql", "").strip()
        except json.JSONDecodeError:
            # JSON 파싱 실패 시, 혹시 AI가 그냥 쿼리만 줬을 경우를 대비해 원본 텍스트 사용
            print("⚠️ JSON 파싱 실패, 원본 텍스트 사용 시도")
            sparql_query = clean_text
            
        if not sparql_query:
            return jsonify({"status": "error", "message": "AI가 쿼리를 생성하지 못했습니다."})

        # 3. 최종 쿼리 조립 (Prefix 강제 주입 - 기존 로직 유지)
        final_sparql = f"""
        PREFIX kodv:    <https://knowledgemap.kr/kodv/def/>
        PREFIX kodvid:  <https://knowledgemap.kr/kodv/id/>
        PREFIX koad:    <http://vocab.datahub.kr/def/administrative-division/>
        PREFIX rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl:     <http://www.w3.org/2002/07/owl#>
        PREFIX xsd:     <http://www.w3.org/2001/XMLSchema#>
        PREFIX skos:    <http://www.w3.org/2004/02/skos/core#>
        PREFIX dcterms: <http://purl.org/dc/terms/>
        PREFIX schema:  <http://schema.org/>
        PREFIX qudt:    <http://qudt.org/schema/qudt/>
        PREFIX unit:    <http://qudt.org/vocab/unit/>
        PREFIX qk:      <http://qudt.org/vocab/quantitykind/>
        
        {sparql_query}
        """
        print(f"🤖 실행 쿼리:\n{final_sparql}")

        # 4. 쿼리 실행
        sparql = SPARQLWrapper(BLAZEGRAPH_URL) # 전역 변수 사용
        sparql.setQuery(final_sparql)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        
        return jsonify({
            "status": "success", 
            "sparql": sparql_query, # 파싱된 순수 쿼리만 반환
            "data": results['results']['bindings']
        })

    except Exception as e:
        print(f"AI Error: {e}")
        return jsonify({"status": "error", "message": str(e)})
    
# ★ [수정] 전문가 콘솔 실행 API
@app.route('/api/sparql', methods=['POST'])
def run_sparql_console():
    try:
        query = request.json.get('query')
        if not query: return jsonify({"status": "error", "message": "쿼리가 비어있습니다."})

        # 1. 보안 필터링
        forbidden_keywords = ['DELETE', 'INSERT', 'DROP', 'UPDATE', 'CLEAR', 'LOAD', 'COPY', 'MOVE']
        upper_query = query.upper()
        if any(word in upper_query for word in forbidden_keywords):
            return jsonify({"status": "error", "message": "🚫 보안 경고: 데이터 수정/삭제 쿼리는 허용되지 않습니다."})

        # 2. ★ [수정] 네임스페이스 강제 주입
        # 사용자가 SELECT 구문만 입력해도 작동하도록 모든 Prefix를 미리 붙여줍니다.
        full_query = f"""
        PREFIX kodv:    <https://knowledgemap.kr/kodv/def/>
        PREFIX kodvid:  <https://knowledgemap.kr/kodv/id/>
        PREFIX koad:    <http://vocab.datahub.kr/def/administrative-division/>
        PREFIX rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl:     <http://www.w3.org/2002/07/owl#>
        PREFIX xsd:     <http://www.w3.org/2001/XMLSchema#>
        PREFIX skos:    <http://www.w3.org/2004/02/skos/core#>
        PREFIX dcterms: <http://purl.org/dc/terms/>
        PREFIX schema:  <http://schema.org/>
        PREFIX qudt:    <http://qudt.org/schema/qudt/>
        PREFIX unit:    <http://qudt.org/vocab/unit/>
        PREFIX qk:      <http://qudt.org/vocab/quantitykind/>
        
        {query}
        """

        print(f"💻 전문가 쿼리 실행 (Auto-Prefix):\n{full_query}")

        # 3. 실행
        sparql.setQuery(full_query) # full_query로 변경됨
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        
        return jsonify({
            "status": "success",
            "vars": results['head']['vars'],
            "data": results['results']['bindings']
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    # 윈도우(nt)인지 리눅스(posix)인지 확인
    if os.name == 'nt': 
        # [로컬 윈도우] 개발 모드: 디버그 켜고, 80번 포트 
        print("💻 로컬(Windows) 환경에서 실행합니다.")
        app.run(host='0.0.0.0', debug=True, port=80) 
    else:
        # [Azure 리눅스] 배포 모드: 디버그 끄고, 5000번 포트 
        print("☁️ 서버(Linux) 환경에서 실행합니다.")
        app.run(host='0.0.0.0', debug=False, port=5000)