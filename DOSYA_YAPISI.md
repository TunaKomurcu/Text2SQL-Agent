# 📁 Proje Dosya Yapısı

## **Klasör Organizasyonu**

```
test/
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
├── 🐍 Text2SQL_Agent.py               # Ana FastAPI uygulaması
├── 🐍 build_db.py                     # Veritabanı ve embedding oluşturma
├── 🐍 config.py                       # Konfigürasyon yönetimi
│
├── 📄 .env                             # Ortam değişkenleri
├── 📄 fk_graph.json                    # Foreign key ilişkileri grafiği
├── 📄 requirements.txt                 # Python bağımlılıkları
│
└── 📋 .gitignore                       # Git ignore dosyası
```

---

## **Klasörlerin Görevleri**

### **📂 models/**
- Tüm machine learning model dosyaları burada
- Embedding modelleri, vektörleştiriciler, LLM
- `.gitignore` ile Git'ten çıkarılmıştır (büyük dosyalar)

### **📂 static/**
- Web arayüzü ve statik dosyalar
- `chat.html` - Ana kullanıcı arayüzü
- Gelecekte CSS, JS dosyaları buraya eklenebilir

### **📂 docker/**
- Tüm Docker ile ilgili dosyalar
- `docker-compose.yml` - Production ortam (Orjinal DB)
- `docker-compose.local.yml` - Local geliştirme (Örnek DB)
- `Dockerfile` - Container image tanımı
- `entrypoint.sh` - Container başlangıç scripti
- `init_db.sql` - PostgreSQL başlangıç şeması (örnek defaultdb)

### **📂 scripts/**
- Yardımcı scriptler ve araçlar
- `setup_env.ps1` - Virtual environment kurulum scripti

---

## **Önemli Dosyalar**

| Dosya | Açıklama |
|-------|----------|
| **Text2SQL_Agent.py** | FastAPI sunucusu, SQL üretimi, chat endpoint'leri |
| **build_db.py** | Qdrant'a embedding yükleme, schema indexleme |
| **config.py** | Tüm ayarlar (.env'den okunur) |
| **fk_graph.json** | Foreign key ilişkileri (otomatik JOIN için) |
| **.env** | Ortam değişkenleri (DB, model path'leri) |

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
