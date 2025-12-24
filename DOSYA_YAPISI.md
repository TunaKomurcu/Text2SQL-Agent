# 📁 Proje Dosya Yapısı

> **Modern Modular Architecture** - Clean Architecture prensipleri ile 6 katmanlı yapı  
> **Toplam:** 25 modül, ~4,000 satır kod  
> **Mimari:** Tek yönlü bağımlılık, sıfır döngüsel bağımlılık

## **Klasör Organizasyonu**

```
test/
├── 📂 utils/                           # 🆕 Infrastructure Layer
│   ├── __init__.py                     # Package exports
│   ├── gpu.py                          # GPU detection (CUDA)
│   ├── db.py                           # PostgreSQL connections
│   ├── qdrant.py                       # Qdrant client (singleton)
│   └── models.py                       # Model manager (BERT, FastText, TF-IDF)
│
├── 📂 search/                          # 🆕 External Search Layer
│   ├── __init__.py                     # Package exports
│   ├── semantic.py                     # BERT semantic search
│   ├── lexical.py                      # FastText lexical search
│   ├── keyword.py                      # TF-IDF keyword search
│   ├── data_values.py                  # Data sample search
│   └── hybrid.py                       # Hybrid search aggregation
│
├── 📂 schema/                          # 🆕 Domain Schema Layer
│   ├── __init__.py                     # Package exports
│   ├── loader.py                       # FK graph loading
│   ├── column_scorer.py                # Column relevance scoring
│   ├── path_finder.py                  # FK-PK path finding
│   └── builder.py                      # Schema pool building
│
├── 📂 sql/                             # 🆕 Domain SQL Layer
│   ├── __init__.py                     # Package exports
│   ├── parser.py                       # SQL extraction from LLM
│   ├── fixer.py                        # Auto-fix SQL identifiers (419 lines)
│   └── executor.py                     # SQL execution + HTML formatting
│
├── 📂 core/                            # 🆕 Business Logic Layer
│   ├── __init__.py                     # Package exports
│   ├── llm_manager.py                  # LLM instance management
│   ├── prompt_builder.py               # Prompt generation (300+ lines)
│   ├── error_analyzer.py               # Error categorization
│   └── sql_generator.py                # Interactive SQL generation (900+ lines)
│
├── 📂 api/                             # 🆕 Presentation Layer
│   ├── __init__.py                     # Package exports
│   ├── main.py                         # FastAPI app initialization
│   └── routes.py                       # REST + WebSocket endpoints
│
├── 📂 models/                          # Model dosyaları
│   ├── fasttext_lexical_model.model   # Lexical benzerlik modeli
│   ├── *.npy                           # FastText vektörleri
│   ├── tfidf_vectorizer.joblib         # TF-IDF vektörleştirici
│   └── openr1-qwen-7b-turkish*.gguf   # LLM modeli
│
├── 📂 static/                          # Statik dosyalar (frontend)
│   └── chat.html                       # Web arayüzü
│
├── 📂 docker/                          # Docker yapılandırmaları
│   ├── init_db.sql                     # PostgreSQL başlangıç şeması
│   ├── docker-compose.yml              # Production Docker compose
│   ├── docker-compose.local.yml        # Local Docker compose
│   ├── Dockerfile                      # Container image tanımı
│   └── entrypoint.sh                   # Container başlangıç scripti
│
├── 📂 scripts/                         # Yardımcı scriptler
│   └── setup_env.ps1                   # Virtual environment kurulum
│
├── 📂 .venv/                           # Python virtual environment
│
├── 🐍 Text2SQL_Agent.py               # Main entry point
├── 🐍 build_vectorDB.py               # Veritabanı ve embedding oluşturma
├── 🐍 config.py                       # Konfigürasyon yönetimi
├── 🐍 test_system.py                  # Comprehensive system tests
│
├── 📄 .env                             # Ortam değişkenleri
├── 📄 fk_graph.json                    # Foreign key ilişkileri grafiği
├── 📄 requirements.txt                 # Python bağımlılıkları
│
├── 📋 README.md                        # Ana dokümantasyon
├── 📋 MIMARI.md                        # Teknik mimari (Türkçe)
├── 📋 KURULUM_KILAVUZU.md             # Kurulum kılavuzu
├── 📋 DOSYA_YAPISI.md                 # Bu dosya
├── 📋 CHEAT_SHEET.md                  # Hızlı referans kılavuzu
│
└── 📋 .gitignore                       # Git ignore dosyası
```

---

## **🆕 Yeni Modular Yapı (v2.0)**

Sistem artık **6 modüler katman**dan oluşuyor:

### **📂 utils/** (Infrastructure Layer)
**Görev:** External service connections, GPU detection, model management

| File | Lines | Description |
|------|-------|-------------|
| `gpu.py` | 60 | GPU detection with CUDA support |
| `db.py` | 30 | PostgreSQL connection pooling |
| `qdrant.py` | 20 | Qdrant client singleton |
| `models.py` | 120 | Model manager (BERT, FastText, TF-IDF) |

**Key Classes:** `ModelManager` (singleton)

---

### **📂 search/** (External Search Layer)
**Görev:** Multi-strategy search across vector databases

| File | Lines | Description |
|------|-------|-------------|
| `semantic.py` | 80 | BERT-based semantic search (768-dim) |
| `lexical.py` | 90 | FastText lexical search (1000-dim) |
| `keyword.py` | 100 | TF-IDF keyword search |
| `data_values.py` | 80 | Data sample value search |
| `hybrid.py` | 150 | Hybrid search with balanced aggregation |

**Key Functions:** `hybrid_search_with_separate_results()`, `select_top_tables_balanced()`

---

### **📂 schema/** (Domain Schema Layer)
**Görev:** Schema intelligence, FK-PK relationships, column scoring

| File | Lines | Description |
|------|-------|-------------|
| `loader.py` | 40 | Load FK graph from JSON |
| `column_scorer.py` | 150 | Score columns by relevance (separate strategies) |
| `path_finder.py` | 120 | Find minimal FK-PK connecting paths |
| `builder.py` | 200 | Build compact schema pools for LLM |

**Key Functions:** `build_compact_schema_pool()`, `find_minimal_connecting_paths()`

---

### **📂 sql/** (Domain SQL Layer)
**Görev:** SQL parsing, auto-fixing, execution

| File | Lines | Description |
|------|-------|-------------|
| `parser.py` | 100 | Extract SQL from LLM responses |
| `fixer.py` | 419 | Auto-fix SQL identifiers (fuzzy matching) |
| `executor.py` | 100 | Execute SQL + format HTML results |

**Key Functions:** `auto_fix_sql_identifiers()` (largest function - 419 lines)

---

### **📂 core/** (Business Logic Layer)
**Görev:** SQL generation, error handling, conversation management

| File | Lines | Description |
|------|-------|-------------|
| `llm_manager.py` | 100 | LLM instance management (singleton) |
| `prompt_builder.py` | 300+ | Static and dynamic prompt generation |
| `error_analyzer.py` | 170 | SQL error categorization + suggestions |
| `sql_generator.py` | 900+ | Interactive SQL generation (largest file) |

**Key Classes:**
- `InteractiveSQLGenerator` - Main SQL generation orchestrator
- `SQLErrorAnalyzer` - Error categorization and suggestion

---

### **📂 api/** (Presentation Layer)
**Görev:** HTTP/WebSocket endpoints, request handling

| File | Lines | Description |
|------|-------|-------------|
| `main.py` | 45 | FastAPI app initialization, CORS, static files |
| `routes.py` | 240 | REST endpoints + WebSocket handlers |

**Key Endpoints:**
- `POST /chat` - Process natural language query
- `WebSocket /ws/chat` - Streaming responses
- `GET /` - Serve chat.html
- `DELETE /session/{session_id}` - Clear session
- `GET /health` - Health check

---

## **Önemli Dosyalar**

| Dosya | Açıklama |
|-------|----------|
| **Text2SQL_Agent.py** | Ana giriş noktası (FastAPI app) |
| **build_vectorDB.py** | Qdrant'a embedding yükleme, schema indexleme |
| **config.py** | Tüm ayarlar (.env'den okunur) |
| **test_system.py** | 🆕 Comprehensive system tests (all modules) |
| **fk_graph.json** | Foreign key ilişkileri (otomatik JOIN için) |
| **.env** | Ortam değişkenleri (DB, model path'leri) |

---

## **🆕 Modular Architecture Benefits**

- ✅ **Clean Architecture**: 6 layers with clear separation of concerns
- ✅ **Small Files**: 25 files (50-900 lines each) vs 1 file (4550 lines)
- ✅ **Testable**: Each module independently testable
- ✅ **Maintainable**: Easy to locate and modify code
- ✅ **Backwards Compatible**: Old imports still work via wrapper
- ✅ **Scalable**: Add features without touching existing code

---

## **Ortam Değişkenleri**

`.env` dosyasında tanımlı path'ler:

```bash
# Model dosyaları (models/ klasöründe)
LEXICAL_FASTTEXT_PATH=./models/fasttext_lexical_model.model
TFIDF_VECTORIZER_PATH=./models/tfidf_vectorizer.joblib
LLM_MODEL_PATH=./models/OpenR1-Qwen-7B-Turkish-Q4_K_M.gguf
```

---

## **Dosya Taşıma Notları**

✅ **Yapılan değişiklikler:**
- `chat.html` → `static/` klasörüne taşındı
- Model dosyaları → `models/` klasöründe (duplikeler silindi)
- Docker dosyaları → `docker/` klasöründe toplandı
- Yardımcı scriptler → `scripts/` klasöründe
- Gereksiz `.env.local`, `set_environment.*` dosyaları silindi
- Config dosyalarında path'ler güncellendi

⚠️ **Dikkat:**
- `.env` dosyası değiştirilirse sunucuyu **yeniden başlatın**
- Model dosyaları `models/` klasöründe olmalı
- `chat.html` artık `static/` içinde
- Docker compose çalıştırırken: `docker-compose -f docker/docker-compose.yml up`

---

## **🚀 Hızlı Başlatma Komutları**

### **Local Development (Örnek DB - defaultdb):**
```powershell
# Docker servisleri başlat (Port 55432, Qdrant 6333)
docker-compose -f docker/docker-compose.local.yml up -d

# Virtual environment kur (ilk seferde)
.\scripts\setup_env.ps1

# Sunucuyu başlat
uvicorn Text2SQL_Agent:app --reload
```

### **Production (Orjinal DB):**
```powershell
# .env dosyasında SEÇENEK 2'yi aktif et ve kendi DB bilgilerinizi yazın!
# DB_HOST=<host>, DB_PORT=5432, DB_NAME=<dbname>, QDRANT_PORT=6334

# Docker servisleri başlat
docker-compose -f docker/docker-compose.yml up -d

# Sunucuyu başlat
uvicorn Text2SQL_Agent:app --reload
```
