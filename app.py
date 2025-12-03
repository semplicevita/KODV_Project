import os
from flask import Flask, render_template, jsonify, request
from SPARQLWrapper import SPARQLWrapper, JSON
import requests
import google.generativeai as genai
from dotenv import load_dotenv

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
SYSTEM_PROMPT = """
You are an expert SPARQL query generator for the 'KODV (Korea Drought Vulnerability)' Knowledge Graph.
Convert natural language questions into valid SPARQL 1.1 queries.

### 1. Schema Information
- **Namespaces (Available):** koad, kodv, kodvid, rdfs, owl, xsd, skos, dcterms, schema, qudt, unit, qk
- **Classes:** koad:Province(L1), koad:City/County/District(L2), koad:Eup/Myeon/Dong(L3)

### 2. Property Dictionary (Korean -> URI) [CRITICAL]
You MUST use the correct property URI based on the user's keyword.

**[Basic Info]**
- **인구 (Population):** `kodv:population`
- **급수율 (Water Supply Rate):** `kodv:waterSupplyRate`
- **급수인구 (Supply Population):** `kodv:waterSupplyPopulation`

**[Exposure]**
- **평균 가뭄 심도 (Avg Drought Severity):** `kodv:droughtSeverityAvg`
- **가뭄 빈도 (Drought Frequency):** `kodv:droughtFrequency`
- **가뭄 노출도 (Exposure Score):** `kodv:droughtExposureScore`
- **노출도 계수 (Exposure Coeff):** `kodv:exposureCoefficient`

**[Sensitivity]**
- **생활용수 이용량 (Domestic Water Usage):** `kodv:domesticWaterUsage`
- **공업용수 이용량 (Industrial Water Usage):** `kodv:industrialWaterUsage`
- **생공용수 / 총 이용량 (Total Usage):** `kodv:domesticIndustrialWaterUsage`
- **민감도 계수 (Sensitivity Coeff):** `kodv:sensitivityCoefficient`

**[Auxiliary Water]**
- **저수지 용량 (Reservoir Capacity):** `kodv:reservoirCapacity`
- **지하수 개발가능량 (Groundwater Available):** `kodv:groundwaterAvailable`
- **보조수원 능력 (Aux Water Capacity):** `kodv:auxWaterSourceCapacity`
- **보조수원 계수 (Aux Water Coeff):** `kodv:auxWaterSourceCoefficient`

**[Response Capacity]**
- **용수공급 가능일수 (Supply Days):** `kodv:waterSupplyAvailableDays`
- **대응능력 계수 (Response Coeff):** `kodv:responseCapacityCoefficient`

**[Vulnerability Results]**
- **취약성 점수 (Vulnerability Score):** `kodv:vulnerabilityScore`
- **취약성 등급 (Numeric 1~5):** `kodv:vulnerabilityRatingNumeric`
- **취약성 등급 (URI Concept):** `kodv:vulnerabilityRating`
  * Grade 1: `kodvid:Rating_I`, Grade 2: `kodvid:Rating_II`, Grade 3: `kodvid:Rating_III`, Grade 4: `kodvid:Rating_IV`, Grade 5: `kodvid:Rating_V`

### 3. Korean Administrative Name Mapping (CRITICAL)
Users often use abbreviations. You MUST expand them in your `FILTER` conditions.
- **"서울" (Seoul)** -> Search for "서울특별시"
- **"경기" (Gyeonggi)** -> Search for "경기도"
- **"충남" (Chungnam)** -> Search for "충청남도"
- **"충북" (Chungbuk)** -> Search for "충청북도"
- **"전남" (Jeonnam)** -> Search for "전라남도"
- **"전북" (Jeonbuk)** -> Search for "전북특별자치도"
- **"강원" (Gangwon)** -> Search for "강원특별자치도"
- **"경남" (Gyeongnam)** -> Search for "경상남도"
- **"경북" (Gyeongbuk)** -> Search for "경상북도"
- **"제주" (Jeju)** -> Search for "제주특별자치도"

### 4. Logic & Rules
1. **DO NOT include PREFIX definitions.** Start with `SELECT` immediately.
2. **Recursive Parent Search:** Use Property Paths `+` to find ancestors.
   - Pattern: `?s (koad:isNeighborhoodOf|koad:isTownOf|koad:isTownshipOf|koad:isDistrictOf|koad:isCityOf|koad:isCountyOf)+ ?ancestor .`
3. **Target Variables:** Always select `?name`, `?code`, and `?val` (the value being filtered/queried).
4. **Output:** Return **ONLY** the query string. No markdown.
5. **Grade Calculation:** When asking for "Average Grade", ALWAYS use `ROUND(AVG(?val))` on `kodv:vulnerabilityRatingNumeric` to return an integer.
6. **Grade Comparison:** When filtering grades (e.g., "Grade 3 or higher"), use `FILTER(?val >= 3)` on `kodv:vulnerabilityRatingNumeric`.

### 5. Example
**User:** "전북에서 취약성 등급이 '심각(IV)'인 곳은?"
**SPARQL:**
SELECT ?name ?code ?val
WHERE {
  ?s a ?type . VALUES ?type { koad:Dong koad:Eup koad:Myeon }
  ?s rdfs:label ?name ; koad:divisionCode ?code .
  
  # Use URI for specific grade filtering
  ?s kodv:vulnerabilityRating kodvid:Rating_IV .
  BIND("IV" AS ?val) 
  
  ?s (koad:isNeighborhoodOf|koad:isTownOf|koad:isTownshipOf|koad:isDistrictOf|koad:isCityOf|koad:isCountyOf)+ ?ancestor .
  ?ancestor rdfs:label ?aname .
  FILTER(CONTAINS(?aname, "전북특별자치도"))
}
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
        # 1. 로컬 DB 조회
        query = f"""
        PREFIX koad: <http://vocab.datahub.kr/def/administrative-division/>
        PREFIX kodv: <https://knowledgemap.kr/kodv/def/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX schema: <http://schema.org/>

        SELECT ?label ?pop ?severity ?freq ?vulScore ?gradeLabel ?wikiURI
        WHERE {{
            BIND(IRI(CONCAT("https://knowledgemap.kr/kodv/id/", "{region_code}")) AS ?region)
            
            OPTIONAL {{ ?region rdfs:label ?label . }}
            OPTIONAL {{ ?region owl:sameAs ?wikiURI . }}
            OPTIONAL {{ ?region kodv:population ?pop . }}
            OPTIONAL {{ ?region kodv:vulnerabilityScore ?vulScore . }}
            OPTIONAL {{ 
                ?region kodv:vulnerabilityRating ?gradeURI .
                ?gradeURI skos:prefLabel ?gradeLabel . 
            }}
        }} LIMIT 1
        """
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)
        local_results = sparql.query().convert()
        bindings = local_results['results']['bindings']
        
        if not bindings:
            return jsonify({"status": "empty", "message": "데이터 없음"})
        
        data = bindings[0]
        
        # 2. 위키데이터 조회 (이미지 4종 세트 무작위 - 사용자님 요청 로직)
        if 'wikiURI' in data:
            wiki_url = data['wikiURI']['value']
            
            wiki_sparql = f"""
            PREFIX wdt: <http://www.wikidata.org/prop/direct/>
            PREFIX schema: <http://schema.org/>
            
            SELECT ?image ?desc WHERE {{
                <{wiki_url}> wdt:P18|wdt:P154|wdt:P94|wdt:P41 ?image .
                OPTIONAL {{ <{wiki_url}> schema:description ?desc . FILTER(LANG(?desc) = "ko") }}
            }} LIMIT 1
            """
            
            try:
                response = requests.get(
                    "https://query.wikidata.org/sparql", 
                    params={'query': wiki_sparql, 'format': 'json'},
                    headers={'User-Agent': 'KODV_Project_Bot/1.0'}
                )
                if response.status_code == 200:
                    wiki_data = response.json()['results']['bindings']
                    if wiki_data:
                        if 'image' in wiki_data[0]: data['image'] = wiki_data[0]['image']
                        if 'desc' in wiki_data[0]: data['desc'] = wiki_data[0]['desc']
            except: pass

        return jsonify({"status": "success", "data": data})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/ask', methods=['POST'])
def ask_ai():
    try:
        user_question = request.json.get('question')
        if not user_question: return jsonify({"status": "error", "message": "질문 없음"})

        print(f"🗣️ 질문: {user_question}")

        # 1. Gemini 호출
        prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_question}\nSPARQL:"
        response = model.generate_content(prompt)
        generated_body = response.text.replace("```sparql", "").replace("```", "").strip()
        
        # ★ [핵심] 모든 네임스페이스 강제 주입 (AI 검색용)
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
        
        {generated_body}
        """
        print(f"🤖 실행 쿼리:\n{final_sparql}")

        # 3. 쿼리 실행
        sparql.setQuery(final_sparql)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        
        return jsonify({
            "status": "success", 
            "sparql": generated_body,
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

        print(f"💻 전문가 쿼리 실행:\n{query}")

        # 2. 실행
        sparql.setQuery(query)
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