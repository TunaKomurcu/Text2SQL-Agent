# 🏗️ Text2SQL - Teknik Mimari Dokümantasyonu

> **Modern Modular Architecture** - Clean Architecture prensipleri ile tasarlanmış 6 katmanlı mimari.

## 📋 İçindekiler
1. [Modüler Mimari](#modüler-mimari)
2. [Sistem Mimarisi](#sistem-mimarisi)
3. [Veri Akışı](#veri-akışı)
4. [Bileşenler](#bileşenler)
5. [Algoritmalar](#algoritmalar)
6. [Veritabanı Yapısı](#veritabanı-yapısı)

---

## 🏗️ Modüler Mimari

### Genel Bakış

Text2SQL sistemi **Clean Architecture** prensipleri ile tasarlanmış 6 katmanlı modüler bir yapıya sahiptir:

- **6 modüler katman**: `utils/`, `search/`, `schema/`, `sql/`, `core/`, `api/`
- **25 özelleşmiş modül**: Her biri tek bir sorumluluğa sahip (ortalama 160 satır)
- **Temiz bağımlılık yönü**: Üst katmanlar alt katmanlara bağımlı, tersi yok
- **Test edilebilir**: Her modül bağımsız unit test'e uygun
- **Ölçeklenebilir**: Yeni özellikler mevcut kodu bozmadan eklenebilir

### Avantajlar

- ✅ **SOLID Prensipleri**: Her modül tek sorumluluk prensibi ile tasarlandı
- ✅ **Bağımsız Test**: Her katman mock'lanabilir ve izole test edilebilir
- ✅ **Kolay Bakım**: Değişiklikler ilgili modülde lokalize kalır
- ✅ **Düşük Coupling**: Katmanlar arası gevşek bağlantı
- ✅ **Yüksek Cohesion**: İlgili fonksiyonalite aynı modülde
- ✅ **Döngüsel Bağımlılık Yok**: Tek yönlü bağımlılık grafiği

### Katman Yapısı

```
Presentation Layer (api/)     → FastAPI endpoints
        ↓
Business Logic (core/)        → SQL generation, LLM, prompts
        ↓
Domain Services (schema/, sql/, search/)  → Schema intelligence, SQL processing
        ↓
Infrastructure (utils/)       → GPU, DB, Qdrant, models
        ↓
External Services             → PostgreSQL, Qdrant, CUDA
```


---

## �🏛️ Sistem Mimarisi

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                            │
│  ┌──────────────┐         ┌──────────────┐                      │
│  │  Web Browser │◄────────│  WebSocket   │                      │
│  │  (chat.html) │         │  Connection  │                      │
│  └──────────────┘         └──────────────┘                      │
└────────────────────────────────┬────────────────────────────────┘
                                 │ HTTP/WS
┌────────────────────────────────▼────────────────────────────────┐
│                      APPLICATION LAYER                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              FastAPI Server (Text2SQL_Agent.py)          │   │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────────┐  │ │   │
│  │  │  Routing   │  │   Chat     │  │   Session Mgmt   │  │ │   │
│  │  │  Layer     │  │  Endpoint  │  │   (WebSocket)    │  │ │   │
│  │  └────────────┘  └────────────┘  └──────────────────┘  │ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           INTERACTIVE SQL GENERATOR                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐   │   │
│  │  │ Semantic │  │  Schema  │  │   SQL    │  │  Auto   │   │   │
│  │  │  Search  │→ │  Builder │→ │Generator │→ │  Fix    │   │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └─────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────┬───────────────────────────┬────────────────────┬───────┘
         │                           │                    │
┌────────▼────────┐      ┌───────────▼────────┐  ┌───────▼──────┐
│  VECTOR STORE   │      │     AI MODELS      │  │   DATABASE   │
│                 │      │                    │  │              │
│  ┌───────────┐  │      │  ┌──────────────┐  │  │ ┌──────────┐ │
│  │  Qdrant   │  │      │  │ Embedding    │  │  │ │PostgreSQL│ │
│  │           │  │      │  │ Model (GPU)  │  │  │ │          │ │
│  │ - Schema  │  │      │  └──────────────┘  │  │ │ - Tables │ │
│  │ - Keywords│  │      │  ┌──────────────┐  │  │ │ - FK     │ │
│  │ - Lexical │  │      │  │ LLM Model    │  │  │ │ - Data   │ │
│  │ - Data    │  │      │  │ (Qwen-7B)    │  │  │ └──────────┘ │
│  └───────────┘  │      │  └──────────────┘  │  │              │
└─────────────────┘      └────────────────────┘  └──────────────┘
```

---

## 🔄 Veri Akışı

### Complete Query Processing Flow

```
1. USER INPUT
   └─► "New York'taki aktif cihazları listele"

2. HYBRID SEARCH (3 parallel streams)
   ├─► Semantic Search (Qdrant)
   │   ├─ Query → Embedding Model → Vector
   │   ├─ Search: schema_embeddings collection
   │   ├─ Search: schema_keywords collection
   │   └─ Results: {devices: 0.89, regions: 0.82, device_status: 0.76}
   │
   ├─► Lexical Search (FastText/TF-IDF)
   │   ├─ Query → Character n-grams
   │   ├─ Search: lexical_embeddings collection
   │   └─ Results: {devices: 0.71, device_status: 0.65}
   │
   └─► Data Values Search (Qdrant)
       ├─ Query → Embedding Model → Vector
       ├─ Search: data_samples collection
       └─ Results: {regions.name='New York': 0.93}

3. RESULT FUSION & SCORING
   ├─ Normalize scores (min-max scaling)
   ├─ Apply weights: semantic(0.5) + lexical(0.3) + keyword(0.2)
   └─ Top tables: [devices, regions, device_status]

4. SCHEMA INTELLIGENCE
   ├─ Load FK Graph (fk_graph.json)
   ├─ BFS Algorithm: Find connecting paths
   │   devices.region_id → regions.id
   │   devices.status_id → device_status.id
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
      "table": "measurements",
      "column": "device_id",
      "ref_table": "devices",
      "ref_column": "id"
    }
  ],
  "adjacency": {
    "measurements": ["devices"],
    "devices": ["regions", "device_status", "..."]
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
  "measurements->devices": [
    {"from": "measurements.device_id", "to": "devices.id"}
  ],
  "devices->regions": [
    {"from": "devices.region_id", "to": "regions.id"}
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

mycompany.devices (  -- device, equipment
    id bigint -- PK
    serial_number varchar (serial number)
    region_id bigint -- FK -> mycompany.regions.id
)

mycompany.regions (  -- region, location
    id bigint -- PK
    name varchar (region name, location name)
)

=== ZİNCİRLEME JOIN YOLLARI ===
  mycompany.devices.region_id → mycompany.regions.id

Kullanıcı Sorusu: "New York'taki cihazları listele"
SQL:
```

---

### 4. **Auto-Fix System**

**Dosya**: `Text2SQL_Agent.py` (auto_fix_sql_identifiers, SQLErrorAnalyzer)

**Görev**: LLM'in ürettiği SQL'deki hataları otomatik düzeltmek

**Kontroller**:
1. **Tablo ismi kontrolü**:
   ```python
   # LLM yazdı: "device_list"
   # Gerçek: "devices"
   # Auto-fix: Fuzzy matching (RapidFuzz)
   if table_name not in schema_pool:
       best_match = max(schema_pool.keys(), 
                       key=lambda t: fuzz.ratio(table_name, t))
       if score > 80:
           sql = sql.replace(table_name, best_match)
   ```

2. **Kolon ismi kontrolü**:
   ```python
   # LLM yazdı: "serial_num"
   # Gerçek: "serial_number"
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
-- Device information
mycompany.devices (
    id BIGINT PRIMARY KEY,
    serial_number VARCHAR,
    device_id BIGINT,
    region_id BIGINT REFERENCES mycompany.regions(id),
    status_id BIGINT REFERENCES mycompany.device_status(id),
    ...
)

-- Region information
mycompany.regions (
    id BIGINT PRIMARY KEY,
    name VARCHAR,
    ...
)

-- Measurement data
mycompany.measurements (
    id BIGINT PRIMARY KEY,
    device_id BIGINT REFERENCES mycompany.devices(id),
    datetime TIMESTAMP,
    value DOUBLE PRECISION,
    ...
)

-- Device status
mycompany.device_status (
    id BIGINT PRIMARY KEY,
    name VARCHAR,
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
        "table_name": "devices",
        "column_name": "serial_number",
        "data_type": "varchar",
        "full_text": "devices.serial_number varchar"
    }
}
```

**2. schema_keywords**
```python
{
    "id": 1,
    "vector": [0.234, -0.567, ...],  # 768 dim
    "payload": {
        "table_name": "devices",
        "column_name": "serial_number",
        "keyword": "serial number",
        "language": "en"
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

### 1. Hybrid Search Strategy

**Gerçek İmplementasyon** (Formül-based scoring YOK):

```python
# Her aramadan ayrı ayrı top-3 tablo seç
top_semantic_tables = get_top_tables(semantic_results, top_k=3)
top_lexical_tables = get_top_tables(lexical_results, top_k=3)
top_keyword_tables = get_top_tables(keyword_results, top_k=3)
top_data_values_tables = get_top_tables(data_values_results, top_k=3)

# Tüm tabloları birleştir (unique set)
selected_tables = set(top_semantic + top_lexical + top_keyword + top_data)
```

**Tablo Seçim Mantığı**:
- Her kaynak (semantic/lexical/keyword/data) için **ayrı ayrı** en iyi 3 tablo seçilir
- Tablolar **birleştirilir** (unique set) → Maksimum 12 tablo (genellikle 5-8)
- **Ağırlıklı toplam YOK** → Her kaynak eşit önemde

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

**Gerçek İmplementasyon** (Priority-Based System):

```python
# Her kolon için source_priority ve similarity score
all_columns = [
    {"table": "regions", "column": "name", 
     "similarity": 0.92, "source_priority": 5, "type": "data_values"},
    {"table": "devices", "column": "serial_number", 
     "similarity": 0.88, "source_priority": 4, "type": "keyword"},
    {"table": "regions", "column": "id", 
     "similarity": 0.75, "source_priority": 3, "type": "semantic"},
    # ...
]

# Sıralama: source_priority > similarity
final_columns = sorted(
    unique_columns.values(), 
    key=lambda x: (x["source_priority"], x["similarity"]), 
    reverse=True
)[:top_n]
```

**Source Priority Değerleri**:
- **5**: Data Values (gerçek veri eşleşmesi) → En yüksek
- **4**: Keyword (Türkçe anahtar kelime eşleşmesi)
- **3**: Semantic (embedding benzerliği)
- **2**: Lexical (TF-IDF/FastText)

**Örnek**:
```python
# Soru: "New York'taki cihazlar"

# regions.name → priority=5 (data_values), similarity=0.92
# → "New York" değeri bu kolonda bulundu!

# devices.serial_number → priority=4 (keyword), similarity=0.88  
# → "cihaz" keyword'ü eşleşti

# devices.region_id → priority=3 (semantic), similarity=0.75
# → Semantic olarak alakalı

# Sonuç: regions.name önce seçilir (priority 5 > 4 > 3)
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