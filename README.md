# 🤖 Text2SQL Ajanı

**Türkçe doğal dil sorgularını otomatik olarak SQL'e çeviren yapay zeka destekli sistem.**

> SQL bilmeden veritabanınızdan veri çekin! Sadece sorunuzu sorun, sistem gerisini halleder.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.118-green)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📚 Dokümantasyon

Projeyi detaylı şekilde anlamak için:

- 📖 **[SUNUM.md](SUNUM.md)** - Sunum için hazır içerik, demo senaryoları
- 🏗️ **[MIMARI.md](MIMARI.md)** - Teknik mimari ve algoritma detayları
- 🚀 **[KURULUM_KILAVUZU.md](KURULUM_KILAVUZU.md)** - Detaylı kurulum adımları
- 🎬 **[DEMO_SENARYOLARI.md](DEMO_SENARYOLARI.md)** - Canlı demo örnekleri
- 📁 **[DOSYA_YAPISI.md](DOSYA_YAPISI.md)** - Proje klasör yapısı

---

## ✨ Özellikler

- ✅ **Tam Türkçe Destek**: Türkçe embedding modeli ve LLM
- ✅ **Akıllı Tablo Seçimi**: 200+ tablo arasından sadece gerekli olanları seçer
- ✅ **Otomatik JOIN**: Foreign key ilişkilerini otomatik keşfeder ve kullanır
- ✅ **GPU Hızlandırma**: CUDA desteği ile 3-4x daha hızlı işlem
- ✅ **Hata Toleransı**: Yanlış yazılan tablo/kolon isimlerini otomatik düzeltir
- ✅ **Hybrid Search**: Semantic + Lexical + Keyword arama birleşimi
- ✅ **Lokal LLM**: Tüm işlemler lokal, veri güvenliği maksimum

---

## 🎯 Kullanım Örneği

```
👤 Kullanıcı: "Ankara'daki aktif sayaçların son 2 saatlik yük profil verilerini getir"

🤖 Sistem:    SELECT es.seri_no, lp.datetime, lp.value 
             FROM m_load_profile lp 
             JOIN e_sayac es ON lp.meter_id = es.id
             JOIN il ON es.il_id = il.id
             WHERE il.adi = 'Ankara' 
             AND lp.datetime >= NOW() - INTERVAL '2 hours'
             ORDER BY lp.datetime DESC;

📊 Sonuç:     [Tablo formatında veriler]
```

**Tüm bunlar otomatik!** JOIN'ler, filtreler, sıralama... Her şey AI tarafından eklendi.

---

## 🚀 Hızlı Başlangıç

> Detaylı kurulum için: [KURULUM_KILAVUZU.md](KURULUM_KILAVUZU.md)

### **1. Virtual Environment Kurulumu**

#### **GPU Kurulumu (Önerilen - 3-4x daha hızlı)** 🎮
```powershell
# Virtual environment oluştur
python -m venv .venv
.venv\Scripts\Activate.ps1

# PyTorch CUDA ile yükle
pip install torch==2.8.0+cu118 --index-url https://download.pytorch.org/whl/cu118

# Diğer paketleri yükle
pip install -r requirements.txt

# GPU'yu test et
python test_gpu.py
```

#### **CPU Kurulumu (GPU yoksa)** 💻
```powershell
# Virtual environment oluştur
python -m venv .venv
.venv\Scripts\Activate.ps1

# CPU-only paketleri yükle
pip install -r requirements-cpu.txt
```

**Alternatif:** Otomatik kurulum scripti
```powershell
.\scripts\setup_env.ps1
.venv\Scripts\Activate.ps1
```

### **2. Örnek DB ile Çalıştırma**
```powershell
# Docker servisleri başlat (PostgreSQL + Qdrant)
docker-compose -f docker/docker-compose.local.yml up -d

# Veritabanı şemasını Qdrant'a yükle
python build_vectorDB.py

# Sunucuyu başlat
uvicorn Text2SQL_Agent:app --reload
```

### **3. Tarayıcıda Aç**
```
http://localhost:8000/static/chat.html
```

> **Not**: Detaylı kurulum için [KURULUM_KILAVUZU.md](KURULUM_KILAVUZU.md) dosyasına bakın.

---

## 📁 Proje Yapısı

```
test/
├── 📂 models/               # ML modelleri
│   ├── fasttext_lexical_model.model
│   ├── tfidf_vectorizer.joblib
│   └── openr1-qwen-7b-turkish*.gguf
├── 📂 static/               # Web arayüzü
│   └── chat.html
├── 📂 docker/               # Docker configs
│   ├── docker-compose.local.yml    # Test ortamı
│   ├── docker-compose.yml          # Production
│   └── init_db.sql                 # Örnek DB
├── 📂 scripts/              # Yardımcı scriptler
│   └── setup_env.ps1
├── Text2SQL_Agent.py        # 🎯 Ana uygulama (4200+ satır)
├── build_vectorDB.py        # Veritabanı indexleme
├── config.py                # Konfigürasyon
├── fk_graph.json            # FK ilişkileri (200+ edge)
├── .env                     # Ortam değişkenleri
│
├── 📖 SUNUM.md              # Sunum dokümanı
├── 🏗️ MIMARI.md             # Teknik mimari
├── 🚀 KURULUM_KILAVUZU.md   # Detaylı kurulum
├── 🎬 DEMO_SENARYOLARI.md   # Demo örnekleri
└── 📁 DOSYA_YAPISI.md       # Klasör yapısı
```

Detaylar: [DOSYA_YAPISI.md](DOSYA_YAPISI.md)

---

## ⚙️ Ortam Değişkenleri

`.env` dosyasını düzenleyerek:

**Örnek DB (Local - Test Amaçlı):**
```bash
DB_HOST=localhost
DB_PORT=55432
DB_NAME=defaultdb
DB_SCHEMA=defaultschema
QDRANT_PORT=6333
```

---

## 🎓 Nasıl Çalışır?

### 1️⃣ **Semantic Search** (Qdrant Vector DB)
Kullanıcı sorusu embedding'e çevrilerek en alakalı tablolar bulunur.

### 2️⃣ **Schema Intelligence** (FK Graph)
Tablolar arası ilişkiler BFS algoritması ile tespit edilir ve JOIN yolları oluşturulur.

### 3️⃣ **SQL Generation** (Local LLM)
Türkçe LLM modeli, sadece gerekli tablolar ve ilişkilerle beslenerek SQL üretir.

### 4️⃣ **Auto-Fix & Validation**
Üretilen SQL syntax ve semantik olarak kontrol edilir, hatalar otomatik düzeltilir.

### 5️⃣ **Execution**
SQL PostgreSQL'de çalıştırılır ve sonuçlar kullanıcıya döner.

**Detaylı akış**: [MIMARI.md](MIMARI.md)

---

## 💪 Güçlü Yanları

| Özellik | Açıklama |
|---------|----------|
| **Akıllı Tablo Seçimi** | 200+ tablo arasından sadece gerekli olanları seçer → LLM daha iyi çalışır |
| **Otomatik JOIN** | FK ilişkilerini keşfeder, kullanıcı "birleştir" demese bile JOIN yapar |
| **Türkçe Destek** | Tam Türkçe embedding + LLM + schema açıklamaları |
| **GPU Hızlandırma** | CUDA ile 3-4x hızlı işlem |
| **Hata Toleransı** | Fuzzy matching ile yanlış tablo/kolon isimlerini düzeltir |

---

## 📊 Performans

| Metrik | Değer |
|--------|-------|
| Basit sorgular yanıt süresi | ~2-5 saniye |
| Kompleks JOIN'li sorgular | ~5-10 saniye |
| GPU hızlanma | %70-80 daha hızlı |
| Doğruluk oranı (basit) | ~95%+ |
| Doğruluk oranı (orta) | ~80-85% |
| Desteklenen tablo sayısı | Sınırsız (teorik) |

---

## 🎬 Demo & Sunum

Projeyi sunum yapacaksanız:

1. **[SUNUM.md](SUNUM.md)** - Sunum için hazır içerik
2. **[DEMO_SENARYOLARI.md](DEMO_SENARYOLARI.md)** - Canlı demo örnekleri
3. **[MIMARI.md](MIMARI.md)** - Teknik sorular için

**Demo Örnekleri**:
- "Ankara'daki sayaçları listele" → Basit JOIN
- "Her ildeki sayaç sayısını hesapla" → Aggregation
- "Son 2 saatlik yük profil verilerini getir" → Zaman serisi + kompleks JOIN

---

## 🔧 Kullanılan Teknolojiler

### Backend & AI
- **FastAPI**: Modern async web framework
- **Qdrant**: Vector database (semantic search)
- **Llama-cpp-python**: LLM inference (GPU destekli)
- **SentenceTransformers**: Turkish BERT embeddings
- **PyTorch**: Deep learning (CUDA support)

### Database
- **PostgreSQL**: Ana veritabanı
- **psycopg3**: Async DB driver

### Frontend
- **HTML + JavaScript**: Chat arayüzü
- **WebSocket**: Real-time communication

### Araçlar
- **Docker**: Container orchestration
- **sqlglot**: SQL parsing & validation
- **RapidFuzz**: Fuzzy string matching

---

## 🔮 Gelecek Planları

- [ ] Multi-database desteği (MySQL, MSSQL)
- [ ] Chat geçmişi kaydetme
- [ ] SQL açıklama modu ("Bu sorgu ne yapıyor?")
- [ ] Görselleştirme (grafik çizme)
- [ ] Excel export
- [ ] Fine-tuned domain-specific LLM
- [ ] Role-based access control

---

## 🐛 Sorun Giderme

### En Sık Karşılaşılan Sorunlar

**1. "CUDA out of memory"**
```bash
# .env'de GPU layer sayısını azalt
LLM_N_GPU_LAYERS=20
```

**2. "Docker servisleri başlamıyor"**
```powershell
# Port çakışması kontrol et
netstat -ano | findstr :55432
# .env'de port değiştir
DB_PORT=55433
```

**3. "Model bulunamadı"**
```bash
# Model path'ini kontrol et
ls ./models/
# .env'de doğru path
LLM_MODEL_PATH=./models/[model-adı].gguf
```

**Detaylı sorun giderme**: [KURULUM_KILAVUZU.md#sorun-giderme](KURULUM_KILAVUZU.md#sorun-giderme)

---

## 📖 Ek Kaynaklar

- **Mimari Dokümantasyon**: [MIMARI.md](MIMARI.md)
- **Kurulum Kılavuzu**: [KURULUM_KILAVUZU.md](KURULUM_KILAVUZU.md)
- **Demo Senaryoları**: [DEMO_SENARYOLARI.md](DEMO_SENARYOLARI.md)
- **Dosya Yapısı**: [DOSYA_YAPISI.md](DOSYA_YAPISI.md)
- **Sorgu Analizi**: [SORGU_ANALIZI.md](SORGU_ANALIZI.md)bash
DB_HOST=localhost
DB_PORT=55432
DB_NAME=defaultdb
DB_SCHEMA=defaultschema
QDRANT_PORT=6333
```

**Orjinal DB (Production):**
```bash
DB_HOST=<kendi_db_host>
DB_PORT=5432
DB_NAME=<kendi_db_adı>
DB_SCHEMA=public
QDRANT_PORT=6334
```

**GPU Ayarları (Opsiyonel):**
```bash
# GPU kullanımı (otomatik tespit varsayılan)
USE_GPU=              # boş = otomatik, true = GPU zorla, false = CPU zorla

# LLM için GPU katman sayısı
LLM_N_GPU_LAYERS=-1   # -1 = tüm katmanlar GPU'da (önerilen)
```

> 💡 **Not**: Sistem GPU'yu otomatik tespit eder. GPU yoksa CPU'ya düşer, hata vermez.

---

## 🎮 GPU Hızlandırma

Sistem otomatik olarak GPU'yu tespit eder ve kullanır:

- **✅ GPU varsa**: Embedding ve LLM modelleri GPU'da çalışır (~4x hızlı)
- **💻 GPU yoksa**: Otomatik olarak CPU'ya düşer (hata vermez)

**Hız Karşılaştırması**:
- CPU: ~10-20 saniye
- GPU: ~2-5 saniye
- **🚀 Hız Artışı: 3-4x**

**Test etmek için**:
```powershell
python test_gpu.py
```

---

## 🧪 Test & Debugging

Proje içinde çeşitli test dosyaları bulunur:

```powershell
# GPU testi
python test_gpu.py

# Keyword sistemini test
python test_keywords_prompt.py

# Bilinen working SQL'leri test
python test_working_queries.py

# Veritabanı exploration
python check_ankara_data.py
python check_meter_id.py
```

---

## 🐳 Docker Komutları

### Local Development
```powershell
# Başlat
docker-compose -f docker/docker-compose.local.yml up -d

# Durdur
docker-compose -f docker/docker-compose.local.yml down

# Logları görüntüle
docker-compose -f docker/docker-compose.local.yml logs -f
```

### Production
```powershell
docker-compose -f docker/docker-compose.yml up -d
docker-compose -f docker/docker-compose.yml down
```

---

## 📝 Örnek Sorgular

Sistemde deneyebileceğiniz örnek sorgular:

- "Tüm tabloları listele"
- "Ankara'daki sayaçları göster"
- "Her ildeki sayaç sayısını hesapla"
- "Son 2 saatlik yük profil verilerini getir"
- "En çok elektrik tüketen 10 sayacı bul"

Daha fazlası için: [DEMO_SENARYOLARI.md](DEMO_SENARYOLARI.md)

---

## 🤝 Katkıda Bulunma

Projeye katkıda bulunmak isterseniz:

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Değişikliklerinizi commit edin (`git commit -m 'Add amazing feature'`)
4. Branch'inizi push edin (`git push origin feature/amazing-feature`)
5. Pull Request açın

---

## 📄 Lisans

Bu proje MIT lisansı altında lisanslanmıştır.

---

## 🙏 Teşekkürler

Bu projeyi mümkün kılan açık kaynak projelere teşekkürler:

- **SentenceTransformers** - Embedding modelleri
- **llama-cpp-python** - LLM inference
- **Qdrant** - Vector database
- **FastAPI** - Web framework
- **emrecan/bert-base-turkish-cased-mean-nli-stsb-tr** - Türkçe BERT modeli

---

<div align="center">

**Sorularınız mı var?** 

Dokümantasyonları kontrol edin veya issue açın!

**⭐ Projeyi beğendiyseniz yıldız vermeyi unutmayın! ⭐**

</div>- **DOSYA_YAPISI.md** - Detaylı proje yapısı
- **Teknik Rapor** - Sistem tasarımı ve algoritmaları

---

**Geliştirici:** Tuna Kömürcü  
**Tarih:** Aralık 2025
