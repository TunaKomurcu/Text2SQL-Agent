# 🚀 Text2SQL - Hızlı Referans Kılavuzu

## ⚡ Hızlı Başlangıç (2 Dakika)

```powershell
# 1. Virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. GPU varsa
pip install torch==2.8.0+cu118 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt

# GPU yoksa
pip install -r requirements-cpu.txt

# 3. Docker başlat
docker-compose -f docker/docker-compose.local.yml up -d

# 4. Veritabanını indexle
python build_vectorDB.py

# 5. Sunucuyu başlat
uvicorn Text2SQL_Agent:app --reload

# 6. Aç: http://localhost:8000/static/chat.html
```

---

## 📋 Sık Kullanılan Komutlar

### Docker İşlemleri
```powershell
# Başlat (local)
docker-compose -f docker/docker-compose.local.yml up -d

# Durdur
docker-compose -f docker/docker-compose.local.yml down

# Logları görüntüle
docker-compose -f docker/docker-compose.local.yml logs -f

# Container'ları listele
docker ps

# PostgreSQL'e bağlan
docker exec -it [container-name] psql -U postgres -d defaultdb
```

### Python Komutları
```powershell
# Virtual environment aktif et
.venv\Scripts\Activate.ps1

# Paket yükle
pip install -r requirements.txt

# GPU test
python test_gpu.py

# Veritabanını yeniden indexle
python build_vectorDB.py

# Sunucuyu başlat (development)
uvicorn Text2SQL_Agent:app --reload

# Sunucuyu başlat (production)
uvicorn Text2SQL_Agent:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 🔧 Konfigürasyon (.env)

### Minimum Gerekli
```bash
DB_HOST=localhost
DB_PORT=55432
DB_NAME=defaultdb
DB_SCHEMA=defaultschema
DB_USER=postgres
DB_PASSWORD=postgres

QDRANT_HOST=localhost
QDRANT_PORT=6333

LLM_MODEL_PATH=./models/OpenR1-Qwen-7B-Turkish-Q4_K_M.gguf
```

### İsteğe Bağlı
```bash
# GPU
USE_GPU=                      # boş=auto, true=force GPU, false=force CPU
LLM_N_GPU_LAYERS=-1           # -1=all layers on GPU

# Performance
MAX_PATH_HOPS=2
MAX_INITIAL_RESULTS=15
LLM_N_CTX=4096

# Debug
SKIP_LLM=False
LLM_VERBOSE=False
```

---

## 🐛 Sorun Giderme

### "ModuleNotFoundError"
```powershell
# Virtual environment aktif mi?
# (.venv) prompt'ta görünmeli

pip install -r requirements.txt
```

### "CUDA out of memory"
```bash
# .env dosyasında
LLM_N_GPU_LAYERS=20    # Veya daha az
# veya
USE_GPU=False
```

### "Docker port çakışması"
```bash
# .env dosyasında
DB_PORT=55433          # Farklı port
QDRANT_PORT=6334
```

### "Model bulunamadı"
```bash
# Model dosyasının varlığını kontrol et
ls ./models/

# .env'de doğru path
LLM_MODEL_PATH=./models/[dosya-adı].gguf
```

### "Qdrant bağlantı hatası"
```powershell
# Qdrant çalışıyor mu?
docker ps | findstr qdrant

# Çalışmıyorsa başlat
docker-compose -f docker/docker-compose.local.yml up -d qdrant

# Test et
python -c "from qdrant_client import QdrantClient; client = QdrantClient('localhost', port=6333); print(client.get_collections())"
```

---

## 📊 Dosya Yolları

### Model Dosyaları
```
./models/
├── openr1-qwen-7b-turkish-q4_k_m.gguf    # LLM
├── fasttext_lexical_model.model          # Lexical
└── tfidf_vectorizer.joblib               # TF-IDF
```

### Config Dosyaları
```
./
├── .env                    # Ortam değişkenleri
├── config.py               # Python config
├── fk_graph.json           # FK ilişkileri
└── schema_keywords.py      # Türkçe keywords
```

### Docker Dosyaları
```
./docker/
├── docker-compose.local.yml    # Local test
├── docker-compose.yml          # Production
└── init_db.sql                 # Örnek DB şeması
```

---

## 🔍 Port Bilgileri

| Servis | Port | URL |
|--------|------|-----|
| FastAPI | 8000 | http://localhost:8000 |
| Chat UI | 8000 | http://localhost:8000/static/chat.html |
| PostgreSQL (local) | 55432 | postgresql://localhost:55432/defaultdb |
| PostgreSQL (prod) | 5432 | - |
| Qdrant (local) | 6333 | http://localhost:6333/dashboard |
| Qdrant (prod) | 6334 | - |

---

## 🧪 Test Komutları

```powershell
# GPU kontrolü
python test_gpu.py

# Keyword sistemi
python test_keywords_prompt.py

# Bilinen çalışan sorgular
python test_working_queries.py

# Veritabanı veri kontrolü
python check_ankara_data.py
python check_meter_id.py
python check_columns.py
```

---

## 📝 Örnek API Çağrıları

### REST Endpoint
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Ankara daki sayaçları listele"}'
```

### WebSocket (JavaScript)
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat');

ws.onopen = () => {
  ws.send(JSON.stringify({
    message: "Ankara'daki sayaçları listele",
    session_id: "unique-session-id"
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

---

## 🎯 Örnek Sorgular (Demo için)

### Basit
- "Tüm tabloları listele"
- "Sayaçları göster"
- "İlk 10 kaydı getir"

### Orta
- "Ankara'daki sayaçları listele"
- "Her ildeki sayaç sayısını hesapla"
- "Aktif sayaçları göster"

### İleri
- "Son 2 saatlik yük profil verilerini getir"
- "Ortalamadan fazla tüketen sayaçları bul"
- "İstanbul'daki aktif sayaçların günlük ortalama tüketimini hesapla"

---

## 🚀 Production Deployment

### Sunucu Gereksinimleri
- **RAM**: 16GB minimum (32GB önerilen)
- **CPU**: 4 core minimum (8 core önerilen)
- **GPU**: NVIDIA 4GB+ VRAM (opsiyonel ama önerilen)
- **Disk**: 50GB SSD

### Docker Production
```bash
# .env dosyasını production için ayarla
DB_HOST=production-db-host
QDRANT_HOST=production-qdrant-host

# Docker başlat
docker-compose -f docker/docker-compose.yml up -d

# Sunucu başlat (çoklu worker)
uvicorn Text2SQL_Agent:app --host 0.0.0.0 --port 8000 --workers 4
```

### Systemd Service (Linux)
```ini
# /etc/systemd/system/text2sql.service
[Unit]
Description=Text2SQL API Server
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/text2sql
Environment="PATH=/path/to/.venv/bin"
ExecStart=/path/to/.venv/bin/uvicorn Text2SQL_Agent:app --host 0.0.0.0 --port 8000

[Install]
WantedBy=multi-user.target
```

```bash
# Servisi etkinleştir
sudo systemctl enable text2sql
sudo systemctl start text2sql
sudo systemctl status text2sql
```

---

## 📈 Performans Optimizasyonu

### GPU Kullanımı
```bash
# Tüm katmanlar GPU'da (en hızlı)
LLM_N_GPU_LAYERS=-1

# Bazı katmanlar GPU'da (VRAM sınırlıysa)
LLM_N_GPU_LAYERS=20
```

### Batch Size
```python
# build_vectorDB.py içinde
BATCH_SIZE = 256  # Daha fazla RAM ama daha hızlı
```

### Context Window
```bash
# .env içinde
LLM_N_CTX=4096     # Varsayılan
LLM_N_CTX=8192     # Daha uzun sorgular için
```

---

## 🔐 Güvenlik Notları

### Production için:
- [ ] `.env` dosyasını `.gitignore`'a ekle
- [ ] Güçlü PostgreSQL şifresi kullan
- [ ] Qdrant için authentication aktif et
- [ ] HTTPS kullan (reverse proxy ile)
- [ ] CORS ayarlarını sıkılaştır
- [ ] Rate limiting ekle

---

## 📞 Yardım Kaynakları

| Sorun | Kaynak |
|-------|--------|
| Kurulum sorunları | [KURULUM_KILAVUZU.md](KURULUM_KILAVUZU.md) |
| Mimari soruları | [MIMARI.md](MIMARI.md) |
| Demo hazırlığı | [DEMO_SENARYOLARI.md](DEMO_SENARYOLARI.md) |
| Sunum | [SUNUM.md](SUNUM.md) |
| Genel bakış | [README.md](README.md) |

---

## ⚡ Kısayollar

```powershell
# Hızlı restart
docker-compose -f docker/docker-compose.local.yml restart && uvicorn Text2SQL_Agent:app --reload

# Logları temizle
docker-compose -f docker/docker-compose.local.yml down -v

# Model tekrar yükle
rm -rf models/.cache && python build_vectorDB.py

# Tek komutla setup
.\scripts\setup_env.ps1 && .venv\Scripts\Activate.ps1
```

---

**Son Güncelleme**: 18 Aralık 2024

**Sürüm**: 1.0

**Dil**: Türkçe

---

Bu cheat sheet'i yazdır ve masanızda bulundur! 📌
