# 🏗️ Text2SQL - Teknik Mimari Dokümantasyonu

## 📋 İçindekiler
1. [Sistem Mimarisi](#sistem-mimarisi)
2. [Veri Akışı](#veri-akışı)
3. [Bileşenler](#bileşenler)
4. [Algoritmalar](#algoritmalar)
5. [Veritabanı Yapısı](#veritabanı-yapısı)

---

## 🏛️ Sistem Mimarisi

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                             │
│  ┌──────────────┐         ┌──────────────┐                      │
│  │  Web Browser │◄────────│  WebSocket   │                      │
│  │  (chat.html) │         │  Connection  │                      │
│  └──────────────┘         └──────────────┘                      │
└────────────────────────────────┬────────────────────────────────┘
                                 │ HTTP/WS
┌────────────────────────────────▼────────────────────────────────┐
│                      APPLICATION LAYER                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              FastAPI Server (Text2SQL_Agent.py)          │  │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────────┐  │  │
│  │  │  Routing   │  │   Chat     │  │   Session Mgmt   │  │  │
│  │  │  Layer     │  │  Endpoint  │  │   (WebSocket)    │  │  │
│  │  └────────────┘  └────────────┘  └──────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           INTERACTIVE SQL GENERATOR                       │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │  │
│  │  │ Semantic │  │  Schema  │  │   SQL    │  │  Auto   │ │  │
│  │  │  Search  │→ │  Builder │→ │Generator │→ │  Fix    │ │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────┬───────────────────────────┬────────────────────┬───────┘
         │                           │                    │
┌────────▼────────┐      ┌───────────▼────────┐  ┌───────▼──────┐
│  VECTOR STORE   │      │     AI MODELS      │  │   DATABASE   │
│                 │      │                    │  │              │
│  ┌───────────┐  │      │  ┌──────────────┐ │  │ ┌──────────┐ │
│  │  Qdrant   │  │      │  │ Embedding    │ │  │ │PostgreSQL│ │
│  │           │  │      │  │ Model (GPU)  │ │  │ │          │ │
│  │ - Schema  │  │      │  └──────────────┘ │  │ │ - Tables │ │
│  │ - Keywords│  │      │  ┌──────────────┐ │  │ │ - FK     │ │
│  │ - Lexical │  │      │  │ LLM Model    │ │  │ │ - Data   │ │
│  │ - Data    │  │      │  │ (Qwen-7B)    │ │  │ └──────────┘ │
│  └───────────┘  │      │  └──────────────┘ │  │              │
└─────────────────┘      └────────────────────┘  └──────────────┘
```

---

## 🔄 Veri Akışı

### Complete Query Processing Flow

```
1. USER INPUT
   └─► "Ankara'daki aktif sayaçları listele"

2. HYBRID SEARCH (3 parallel streams)
   ├─► Semantic Search (Qdrant)
   │   ├─ Query → Embedding Model → Vector
   │   ├─ Search: schema_embeddings collection
   │   ├─ Search: schema_keywords collection
   │   └─ Results: {e_sayac: 0.89, il: 0.82, m_meter_status: 0.76}
   │
   ├─► Lexical Search (FastText/TF-IDF)
   │   ├─ Query → Character n-grams
   │   ├─ Search: lexical_embeddings collection
   │   └─ Results: {e_sayac: 0.71, sayac_durumu: 0.65}
   │
   └─► Data Values Search (Qdrant)
       ├─ Query → Embedding Model → Vector
       ├─ Search: data_samples collection
       └─ Results: {il.adi='Ankara': 0.93}

3. RESULT FUSION & SCORING
   ├─ Normalize scores (min-max scaling)
   ├─ Apply weights: semantic(0.5) + lexical(0.3) + keyword(0.2)
   └─ Top tables: [e_sayac, il, m_meter_status]

4. SCHEMA INTELLIGENCE
   ├─ Load FK Graph (fk_graph.json)
   ├─ BFS Algorithm: Find connecting paths
   │   e_sayac.il_id → il.id
   │   e_sayac.meter_status_id → m_meter_status.id
   └─ Build schema_pool (metadata for LLM)

5. PROMPT CONSTRUCTION
   ├─ Static system prompt (Turkish instructions)
   ├─ Dynamic context:
   │   ├─ Allowed tables & columns (only relevant ones)
   │   ├─ Turkish keywords (from schema_keywords.py)
   │   ├─ FK relationships (JOIN paths)
   │   └─ Sample values (if found)
   └─ User query

6. LLM GENERATION
   ├─ Load Qwen-7B Turkish model
   ├─ GPU inference (if available)
   ├─ Generate SQL
   └─ Extract SQL from response

7. AUTO-FIX & VALIDATION
   ├─ Parse SQL (sqlglot)
   ├─ Check table names (fuzzy match if wrong)
   ├─ Check column names (auto-correct typos)
   ├─ Validate syntax
   └─ Fix common errors

8. EXECUTION
   ├─ Connect to PostgreSQL
   ├─ Execute SQL
   ├─ Fetch results
   └─ Handle errors (retry with correction)

9. RESPONSE
   └─► Return to user (SQL + Results + Explanation)
```

---

## 🧩 Bileşenler

### 1. **Semantic Search Engine**

**Dosya**: `Text2SQL_Agent.py` (lines ~494-520)

**Görev**: Türkçe doğal dil sorgusunu vektöre çevirip en alakalı tabloları bulma

**Teknolojiler**:
- SentenceTransformer (Turkish BERT)
- Qdrant Vector Database
- Cosine Similarity

**Akış**:
```python
def semantic_search(query: str, top_k: int = 10):
    # 1. Query'yi embedle (GPU'da)
    query_vector = EMBEDDING_MODEL.encode(query)
    
    # 2. Qdrant'ta ara (3 collection)
    results = []
    for collection in [schema_embeddings, schema_keywords, data_samples]:
        hits = QDRANT_CLIENT.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k
        )
        results.extend(hits)
    
    # 3. Skorları normalize et
    return normalize_scores(results)
```

**Collections**:
- `schema_embeddings`: Tablo.kolon metadata
- `schema_keywords`: Türkçe açıklamalar
- `data_samples`: Gerçek veri örnekleri

---

### 2. **FK Graph & Path Finding**

**Dosya**: `fk_graph.json`, `Text2SQL_Agent.py` (lines ~1468-1548)

**Görev**: Tablolar arası ilişkileri bulup otomatik JOIN yapmak

**Veri Yapısı**:
```json
{
  "edges": [
    {
      "table": "m_load_profile",
      "column": "meter_id",
      "ref_table": "e_sayac",
      "ref_column": "id"
    }
  ],
  "adjacency": {
    "m_load_profile": ["e_sayac"],
    "e_sayac": ["il", "m_meter_status", "..."]
  }
}
```

**Algoritma**: BFS (Breadth-First Search)
```python
def find_minimal_connecting_paths(fk_graph, selected_tables, max_hops=2):
    # Her tablo çifti için en kısa yolu bul
    paths = {}
    for t1 in selected_tables:
        for t2 in selected_tables:
            if t1 != t2:
                path = bfs_shortest_path(fk_graph, t1, t2, max_hops)
                if path:
                    paths[f"{t1}->{t2}"] = path
    
    # Gereksiz alt-yolları filtrele
    return filter_maximal_paths(paths)
```

**Örnek Çıktı**:
```python
{
  "m_load_profile->e_sayac": [
    {"from": "m_load_profile.meter_id", "to": "e_sayac.id"}
  ],
  "e_sayac->il": [
    {"from": "e_sayac.il_id", "to": "il.id"}
  ]
}
```

---

### 3. **Prompt Engineering**

**Dosya**: `Text2SQL_Agent.py` (STATIC_PROMPT, generate_strict_prompt_dynamic_only)

**Görev**: LLM'e talimatları ve konteksti doğru şekilde vermek

**Yapı**:
```
┌────────────────────────────────────────┐
│         STATIC PROMPT (sabit)          │
│  - SQL kuralları                       │
│  - Türkçe talimatlar                   │
│  - Örnek sorgular                      │
│  - Karar matrisi                       │
└────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────┐
│      DYNAMIC PROMPT (değişken)         │
│  - İzin verilen tablolar               │
│  - Sütunlar + Türkçe açıklamalar       │
│  - FK ilişkileri (JOIN yolları)        │
│  - Örnek değerler                      │
│  - Kullanıcı sorusu                    │
└────────────────────────────────────────┘
            │
            ▼
          [LLM]
            │
            ▼
         [SQL]
```

**Örnek Dynamic Prompt**:
```
=== İZİN VERİLEN TABLO VE SÜTUNLAR ===

helios.e_sayac (  -- sayaç, elektrik sayacı
    id bigint -- PK
    seri_no bigint (seri numarası, serial number)
    il_id bigint -- FK -> helios.il.id
)

helios.il (  -- şehir, il
    id bigint -- PK
    adi varchar (il adı, şehir adı)
)

=== ZİNCİRLEME JOIN YOLLARI ===
  helios.e_sayac.il_id → helios.il.id

Kullanıcı Sorusu: "Ankara'daki sayaçları listele"
SQL:
```

---

### 4. **Auto-Fix System**

**Dosya**: `Text2SQL_Agent.py` (auto_fix_sql_identifiers, SQLErrorAnalyzer)

**Görev**: LLM'in ürettiği SQL'deki hataları otomatik düzeltmek

**Kontroller**:
1. **Tablo ismi kontrolü**:
   ```python
   # LLM yazdı: "e_sayaclar"
   # Gerçek: "e_sayac"
   # Auto-fix: Fuzzy matching (RapidFuzz)
   if table_name not in schema_pool:
       best_match = max(schema_pool.keys(), 
                       key=lambda t: fuzz.ratio(table_name, t))
       if score > 80:
           sql = sql.replace(table_name, best_match)
   ```

2. **Kolon ismi kontrolü**:
   ```python
   # LLM yazdı: "seri_numarasi"
   # Gerçek: "seri_no"
   # Auto-fix: Kolon listesinde ara
   if column not in table_columns:
       best_match = find_closest_column(column, table_columns)
       sql = sql.replace(f"{table}.{column}", 
                        f"{table}.{best_match}")
   ```

3. **Syntax validation**:
   ```python
   # sqlglot ile parse et
   try:
       parsed = sqlglot.parse_one(sql)
   except Exception as e:
       # Hata mesajını analiz et
       fix_suggestion = analyze_error(e)
       sql = apply_fix(sql, fix_suggestion)
   ```

**Hata Tipleri**:
- Missing JOIN
- Wrong table alias
- Typo in column name
- Missing WHERE clause
- Syntax errors

---

### 5. **GPU Acceleration**

**Dosya**: `Text2SQL_Agent.py`, `build_vectorDB.py` (detect_gpu)

**Görev**: Embedding ve LLM işlemlerini GPU'da hızlandırmak

**Akış**:
```python
def detect_gpu_availability():
    try:
        import torch
        if torch.cuda.is_available():
            return {
                'available': True,
                'device': 'cuda',
                'device_name': torch.cuda.get_device_name(0),
                'count': torch.cuda.device_count()
            }
    except:
        pass
    
    return {'available': False, 'device': 'cpu'}

# Model yükleme
DEVICE = 'cuda' if gpu_available else 'cpu'
EMBEDDING_MODEL = SentenceTransformer(model_name, device=DEVICE)

# LLM GPU layers
llm = Llama(
    model_path="./models/model.gguf",
    n_gpu_layers=-1,  # Tüm layerlar GPU'da
    n_ctx=4096
)
```

**Performans Kazancı**:
- Embedding: 3-4x hızlı
- LLM inference: 2-3x hızlı
- Batch processing: 5-6x hızlı

---

## 🗄️ Veritabanı Yapısı

### PostgreSQL Schema

**Ana Tablolar**:
```sql
-- Sayaç bilgileri
helios.e_sayac (
    id BIGINT PRIMARY KEY,
    seri_no BIGINT,
    meter_id BIGINT,
    il_id BIGINT REFERENCES helios.il(id),
    meter_status_id BIGINT REFERENCES helios.m_meter_status(id),
    ...
)

-- Şehir bilgileri
helios.il (
    id BIGINT PRIMARY KEY,
    adi VARCHAR,
    ...
)

-- Yük profil verileri
helios.m_load_profile (
    id BIGINT PRIMARY KEY,
    meter_id BIGINT REFERENCES helios.e_sayac(id),
    datetime TIMESTAMP,
    value DOUBLE PRECISION,
    ...
)

-- Sayaç durumu
helios.m_meter_status (
    id BIGINT PRIMARY KEY,
    adi VARCHAR,
    ...
)
```

**İlişkiler**:
- 200+ tablo
- 300+ foreign key
- 2000+ kolon

### Qdrant Collections

**1. schema_embeddings**
```python
{
    "id": 1,
    "vector": [0.123, -0.456, ...],  # 768 dim
    "payload": {
        "table_name": "e_sayac",
        "column_name": "seri_no",
        "data_type": "bigint",
        "full_text": "e_sayac.seri_no bigint"
    }
}
```

**2. schema_keywords**
```python
{
    "id": 1,
    "vector": [0.234, -0.567, ...],  # 768 dim
    "payload": {
        "table_name": "e_sayac",
        "column_name": "seri_no",
        "keyword": "seri numarası",
        "language": "tr"
    }
}
```

**3. lexical_embeddings**
```python
{
    "id": 1,
    "vector": [0.1, 0.2, ...],  # 1000 dim (TF-IDF)
    "payload": {
        "table_name": "e_sayac",
        "column_name": "seri_no",
        "tokens": ["seri", "no"]
    }
}
```

**4. data_samples**
```python
{
    "id": 1,
    "vector": [0.345, -0.678, ...],  # 768 dim
    "payload": {
        "table_name": "il",
        "column_name": "adi",
        "value": "Ankara",
        "data_type": "varchar"
    }
}
```

---

## 🔬 Algoritmalar

### 1. Hybrid Search Fusion

**Formül**:
```
final_score = α * semantic_score + β * lexical_score + γ * keyword_score

Varsayılan: α=0.5, β=0.3, γ=0.2
```

**Normalizasyon**:
```python
def normalize_score(score, min_score, max_score):
    if max_score == min_score:
        return 0.5
    return (score - min_score) / (max_score - min_score)
```

**Threshold Filtering**:
```python
def filter_by_threshold(results, threshold=0.4):
    return [r for r in results if r['score'] >= threshold]
```

---

### 2. BFS for JOIN Paths

**Pseudocode**:
```python
def bfs_shortest_path(graph, start, end, max_depth=2):
    queue = [(start, [start], 0)]
    visited = set()
    
    while queue:
        current, path, depth = queue.pop(0)
        
        if current == end:
            return path  # Yol bulundu
        
        if depth >= max_depth:
            continue  # Max derinliğe ulaşıldı
        
        if current in visited:
            continue
        
        visited.add(current)
        
        # Komşu tabloları ekle
        for neighbor in graph.adjacency[current]:
            if neighbor not in visited:
                queue.append((neighbor, path + [neighbor], depth + 1))
    
    return None  # Yol bulunamadı
```

**Karmaşıklık**: O(V + E) burada V=tablo sayısı, E=FK sayısı

---

### 3. Column Relevance Scoring

**Formül**:
```python
relevance_score = (
    0.4 * semantic_similarity +
    0.3 * keyword_match_bonus +
    0.2 * data_value_match_bonus +
    0.1 * column_usage_frequency
)
```

**Örnek**:
```python
# Soru: "Ankara'daki sayaçlar"
# Kolon: il.adi

semantic_similarity = 0.82  # "şehir adı" embedding'i sorguya yakın
keyword_match_bonus = 1.0   # "Ankara" değeri bulundu
data_value_match_bonus = 1.0  # "Ankara" bu kolonda var
usage_frequency = 0.9       # Bu kolon sık kullanılıyor

final_score = 0.4*0.82 + 0.3*1.0 + 0.2*1.0 + 0.1*0.9 = 0.918
```

---

## 📊 Performans Optimizasyonları

### 1. **Caching**
- LRU cache for FK graph loading
- Session-based LLM instance reuse
- Static prompt pre-loading

### 2. **Batch Processing**
```python
# Embedding batch size: 128
vectors = EMBEDDING_MODEL.encode(texts, batch_size=128)

# Qdrant batch upload
points = [PointStruct(...) for _ in range(batch_size)]
client.upsert(collection_name, points)
```

### 3. **Lazy Loading**
- LLM only loaded when needed
- FastText model optional (SKIP_LEXICAL=1)

### 4. **Connection Pooling**
- PostgreSQL connection reuse
- Qdrant client singleton

---

## 🔒 Güvenlik

### SQL Injection Prevention
- ✅ Parameterized queries (psycopg3)
- ✅ SQL parsing validation (sqlglot)
- ✅ Whitelist table/column names

### Access Control
- ⚠️ Şu an yok (local deployment için)
- 🔮 Gelecek: Role-based access

---

## 🧪 Test & Debugging

### Test Dosyaları
- `test_gpu.py`: GPU testi
- `test_keywords_prompt.py`: Keyword sistemini test
- `test_working_queries.py`: Bilinen working SQL'leri test
- `check_*.py`: Veritabanı data exploration

### Debug Modları
```python
# LLM verbose mode
LLM_VERBOSE=True

# SQL generation debug
print(f"Generated SQL: {sql}")
print(f"Auto-fix applied: {fixes}")
```

---

## 📚 Referanslar

### Kullanılan Modeller
- **Embedding**: `emrecan/bert-base-turkish-cased-mean-nli-stsb-tr`
- **LLM**: `OpenR1-Qwen-7B-Turkish-Q4_K_M`
- **FastText**: Custom trained (lexical similarity)

### Kütüphaneler
- FastAPI: Web framework
- Qdrant: Vector database
- llama-cpp-python: LLM inference
- SentenceTransformers: Embeddings
- sqlglot: SQL parsing
- RapidFuzz: Fuzzy string matching

---

Bu dokümantasyon, sistem mimarisinin tüm teknik detaylarını içerir. Daha fazla bilgi için kaynak kodları inceleyin.
