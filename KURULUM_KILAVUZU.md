# 🚀 Text2SQL - Detaylı Kurulum Kılavuzu

## 📋 İçindekiler
1. [Sistem Gereksinimleri](#sistem-gereksinimleri)
2. [Ön Hazırlık](#ön-hazırlık)
3. [Adım Adım Kurulum](#adım-adım-kurulum)
4. [Veritabanı Konfigürasyonu](#veritabanı-konfigürasyonu)
5. [Sorun Giderme](#sorun-giderme)

---

## 💻 Sistem Gereksinimleri

### Minimum Gereksinimler
- **İşletim Sistemi**: Windows 10/11, Linux, macOS
- **RAM**: 8 GB
- **Disk**: 20 GB boş alan
- **Python**: 3.9 veya üzeri
- **Internet**: İlk kurulum için (model indirme)

### Önerilen Gereksinimler
- **RAM**: 16 GB
- **GPU**: NVIDIA GPU (4GB+ VRAM, CUDA 11.8 destekli)
- **Disk**: 50 GB boş alan (SSD önerilir)
- **Python**: 3.10+

### İdeal Gereksinimler (En İyi Performans)
- **RAM**: 32 GB
- **GPU**: NVIDIA RTX 3060 veya üzeri (8GB+ VRAM)
- **CPU**: 8+ core
- **Disk**: 100 GB SSD

---

## 🔧 Ön Hazırlık

### 1. Python Kurulumu

**Windows**:
```powershell
# Python'un kurulu olup olmadığını kontrol et
python --version

# Kurulu değilse: https://www.python.org/downloads/
# ⚠️ "Add Python to PATH" seçeneğini işaretle!
```

**Linux/macOS**:
```bash
# Python versiyonu kontrol
python3 --version

# Kurulu değilse:
# Ubuntu/Debian:
sudo apt update
sudo apt install python3 python3-pip python3-venv

# macOS:
brew install python@3.10
```

### 2. Docker Kurulumu

**Windows**:
1. [Docker Desktop](https://www.docker.com/products/docker-desktop/) indir
2. Kur ve başlat
3. WSL 2 backend'i etkinleştir (önerilir)

**Linux**:
```bash
# Docker kurulumu
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Docker Compose kurulumu
sudo apt install docker-compose

# Kullanıcıyı docker grubuna ekle (sudo'suz kullanım için)
sudo usermod -aG docker $USER
newgrp docker
```

**macOS**:
1. [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) indir ve kur

### 3. NVIDIA GPU Kurulumu (Opsiyonel ama Önerilen)

**Windows**:
```powershell
# NVIDIA Driver kontrol
nvidia-smi

# Kurulu değilse: GeForce Experience veya
# https://www.nvidia.com/Download/index.aspx

# CUDA Toolkit 11.8
# İndir: https://developer.nvidia.com/cuda-11-8-0-download-archive
```

**Linux**:
```bash
# NVIDIA Driver
sudo ubuntu-drivers autoinstall
# veya
sudo apt install nvidia-driver-535

# CUDA Toolkit 11.8
wget https://developer.download.nvidia.com/compute/cuda/11.8.0/local_installers/cuda_11.8.0_520.61.05_linux.run
sudo sh cuda_11.8.0_520.61.05_linux.run

# GPU kontrol
nvidia-smi
```

---

## 📦 Adım Adım Kurulum

### SEÇENEK A: GPU ile Kurulum (Önerilen)

#### 1️⃣ Projeyi İndir

```powershell
# GitHub'dan indir (eğer repo varsa)
git clone https://github.com/[username]/text2sql.git
cd text2sql

# veya ZIP olarak indir ve çıkart
```

#### 2️⃣ Virtual Environment Oluştur

```powershell
# Virtual environment oluştur
python -m venv .venv

# Aktif et (Windows)
.venv\Scripts\Activate.ps1

# Aktif et (Linux/macOS)
source .venv/bin/activate

# Aktif olduğunu kontrol et (prompt'ta (.venv) görünmeli)
```

⚠️ **PowerShell Execution Policy Hatası?**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### 3️⃣ PyTorch GPU Kurulumu

```powershell
# PyTorch CUDA 11.8 versiyonu
pip install torch==2.8.0+cu118 --index-url https://download.pytorch.org/whl/cu118

# GPU'nun algılandığını test et
python -c "import torch; print(torch.cuda.is_available())"
# True çıkmalı!
```

#### 4️⃣ Diğer Paketleri Yükle

```powershell
pip install -r requirements.txt

# Yükleme süresi: ~5-10 dakika (internet hızına bağlı)
```

#### 5️⃣ GPU Testini Çalıştır

```powershell
python test_gpu.py

# Beklenen çıktı:
# 🔧 GPU Testi Başlatılıyor...
# ✅ PyTorch yüklü
# ✅ CUDA kullanılabilir: True
# 🎮 GPU: NVIDIA GeForce RTX 3060
# ...
```

---

### SEÇENEK B: CPU ile Kurulum (GPU Yoksa)

#### 1️⃣ - 2️⃣ Aynı (Yukarıdaki adımlar)

#### 3️⃣ CPU-Only Paketleri Yükle

```powershell
# Tek komutla tüm paketler
pip install -r requirements-cpu.txt

# Yükleme süresi: ~5-10 dakika
```

#### 4️⃣ Test Et

```powershell
python test_gpu.py

# Beklenen çıktı:
# ⚠️ CUDA kullanılamıyor - CPU modunda çalışılacak
```

---

### SEÇENEK C: Otomatik Kurulum (Kolay Yol)

```powershell
# Tek komutla kurulum (Windows)
.\scripts\setup_env.ps1

# Script ne yapar:
# 1. Virtual environment oluşturur
# 2. GPU varsa PyTorch CUDA kurulumu
# 3. Yoksa CPU versiyonu kurulumu
# 4. requirements.txt paketlerini yükler
# 5. GPU testini çalıştırır

# Tamamlandıktan sonra:
.venv\Scripts\Activate.ps1
```

---

## 🗄️ Veritabanı Konfigürasyonu

### Docker ile Lokal Test Veritabanı (Önerilen - Başlangıç)

#### 1️⃣ Docker Servislerini Başlat

```powershell
# PostgreSQL + Qdrant başlat
docker-compose -f docker/docker-compose.local.yml up -d

# Kontrol et
docker ps

# Beklenen çıktı:
# CONTAINER ID   IMAGE                  STATUS
# xxxxx          postgres:15            Up
# xxxxx          qdrant/qdrant:latest   Up
```

**Ne Oluşturuldu?**:
- PostgreSQL: `localhost:55432` (varsayılan şifre: postgres)
- Qdrant: `localhost:6333`
- Örnek veritabanı: `defaultdb` (schema: `defaultschema`)

#### 2️⃣ Veritabanı İçeriğini Kontrol Et

```powershell
# Docker içinde psql'e bağlan
docker exec -it [postgres-container-name] psql -U postgres -d defaultdb

# SQL ile kontrol
\dt defaultschema.*

# Çıkış
\q
```

#### 3️⃣ .env Dosyasını Ayarla

```bash
# .env dosyasını oluştur (veya düzenle)
DB_HOST=localhost
DB_PORT=55432
DB_NAME=defaultdb
DB_USER=postgres
DB_PASSWORD=postgres
DB_SCHEMA=defaultschema

QDRANT_HOST=localhost
QDRANT_PORT=6333
```

#### 4️⃣ Veritabanını Qdrant'a Yükle

```powershell
# Schema'yı Qdrant'a indexle
python build_vectorDB.py

# Beklenen çıktı:
# 🔧 build_vectorDB GPU üzerinde çalışacak (veya CPU)
# ⏳ Loading embedding model...
# ✅ Embedding model ready!
# Building schema embeddings (semantic)
# Building lexical embeddings (TF-IDF + char n-grams)
# Schema keywords built: 150 vectors
# ...

# Süre: ~2-5 dakika (GPU'da), ~10-20 dakika (CPU'da)
```

#### 5️⃣ Sunucuyu Başlat

```powershell
# FastAPI sunucusunu başlat
uvicorn Text2SQL_Agent:app --reload

# Beklenen çıktı:
# 🔧 Kullanılacak cihaz: GPU (veya CPU)
# ⏳ Loading embedding model on GPU...
# ✅ Embedding models ready on GPU!
# ⏳ Loading LLM model...
# ✅ LLM ready!
# INFO:     Uvicorn running on http://127.0.0.1:8000
```

#### 6️⃣ Tarayıcıda Aç

```
http://localhost:8000/static/chat.html
```

**İlk Test Sorusu**: "Tüm tabloları listele"

---

### Kendi Veritabanınızı Kullanma (Production)

#### 1️⃣ .env Dosyasını Güncelle

```bash
# Kendi PostgreSQL bilgileriniz
DB_HOST=your-db-host.com
DB_PORT=5432
DB_NAME=your_database
DB_USER=your_username
DB_PASSWORD=your_password
DB_SCHEMA=public  # veya kendi schema adınız

# Qdrant (production)
QDRANT_HOST=localhost
QDRANT_PORT=6334  # Lokal test ile çakışmasın
```

#### 2️⃣ FK İlişkilerini Güncelle

```powershell
# Kendi veritabanınızın FK ilişkilerini çıkart
python check_real_fk_constraints.py > my_fk_graph.json

# fk_graph.json'u güncelle veya yeni dosya kullan
# (Text2SQL_Agent.py içinde FK_GRAPH_PATH değiştir)
```

#### 3️⃣ Schema Keywords Ekle

`schema_keywords.py` dosyasını düzenle:
```python
SCHEMA_KEYWORDS = {
    "your_table_name": {
        "table_keywords": ["tablo açıklaması", "anahtar kelimeler"],
        "column_keywords": {
            "column_name": ["sütun açıklaması", "türkçe karşılık"]
        }
    },
    # ...
}
```

#### 4️⃣ Indexleme ve Başlatma

```powershell
# Kendi veritabanınızı indexle
python build_vectorDB.py

# Sunucuyu başlat
uvicorn Text2SQL_Agent:app --reload --host 0.0.0.0 --port 8000
```

---

## 🎯 Model Dosyalarını İndirme

### LLM Modeli (Zorunlu)

Model boyutu: ~4.5 GB

**İndirme Seçenekleri**:

1. **Hugging Face** (Önerilen):
```bash
# Hugging Face CLI ile
pip install huggingface-hub
huggingface-cli download [model-repo-name] --local-dir ./models/
```

2. **Manuel İndirme**:
- Model linkini edinin
- `models/` klasörüne indirin
- `.env` dosyasında path'i ayarlayın:
```bash
LLM_MODEL_PATH=./models/OpenR1-Qwen-7B-Turkish-Q4_K_M.gguf
```

### Embedding Modeli (Otomatik)

İlk çalıştırmada otomatik indirilir:
```python
# Otomatik cache: ~/.cache/huggingface/
EMBEDDING_MODEL_NAME=emrecan/bert-base-turkish-cased-mean-nli-stsb-tr
```

Boyut: ~500 MB

---

## 🔍 Sorun Giderme

### Problem 1: "ModuleNotFoundError: No module named 'X'"

**Çözüm**:
```powershell
# Virtual environment aktif mi kontrol et
# Prompt'ta (.venv) görünmeli

# Paketi tekrar yükle
pip install -r requirements.txt

# Belirli paketi yükle
pip install [paket-adi]
```

---

### Problem 2: "CUDA out of memory"

**Çözüm**:
```bash
# .env dosyasında GPU layer sayısını azalt
LLM_N_GPU_LAYERS=20  # -1 yerine (tüm layerlar yerine 20)

# veya CPU'ya geç
USE_GPU=False
```

---

### Problem 3: Docker servisleri başlamıyor

**Çözüm**:
```powershell
# Port çakışması var mı kontrol et
netstat -ano | findstr :55432
netstat -ano | findstr :6333

# Çakışma varsa .env'de port değiştir
DB_PORT=55433
QDRANT_PORT=6334

# Docker'ı yeniden başlat
docker-compose -f docker/docker-compose.local.yml down
docker-compose -f docker/docker-compose.local.yml up -d
```

---

### Problem 4: "LLM model bulunamadı"

**Çözüm**:
```powershell
# Model path'ini kontrol et
ls ./models/

# .env'de doğru path olmalı
LLM_MODEL_PATH=./models/[model-dosya-adi].gguf

# Model varsa ama çalışmıyorsa, LLM'i geçici skip et
# .env:
SKIP_LLM=True

# Test et (LLM olmadan çalışır)
uvicorn Text2SQL_Agent:app --reload
```

---

### Problem 5: Qdrant bağlantı hatası

**Çözüm**:
```powershell
# Qdrant çalışıyor mu?
docker ps | findstr qdrant

# Çalışmıyorsa başlat
docker-compose -f docker/docker-compose.local.yml up -d qdrant

# Qdrant web UI kontrol
# Tarayıcı: http://localhost:6333/dashboard

# Bağlantı test et
python -c "from qdrant_client import QdrantClient; client = QdrantClient('localhost', port=6333); print(client.get_collections())"
```

---

### Problem 6: build_vectorDB.py çok yavaş

**Çözüm**:
```powershell
# GPU kullanıyor mu kontrol et
# Log'da "GPU üzerinde çalışacak" görmeli

# Batch size artır (daha fazla RAM ama daha hızlı)
# build_vectorDB.py içinde:
BATCH_SIZE = 256  # Varsayılan 128

# Sadece schema'ları indexle (data samples skip)
# build_vectorDB.py main() fonksiyonunda:
# build_data_samples(client) satırını yorum yap
```

---

### Problem 7: Türkçe karakterler bozuk

**Çözüm**:
```powershell
# Python encoding kontrol
python -c "import sys; print(sys.getdefaultencoding())"
# "utf-8" çıkmalı

# Windows'ta konsol encoding ayarla
chcp 65001

# .env dosyasının encoding'i UTF-8 olmalı
# Notepad++ / VS Code ile aç, "UTF-8" kaydet
```

---

## ✅ Kurulum Başarı Kontrol Listesi

Aşağıdakilerin hepsi çalışmalı:

- [ ] `python --version` → Python 3.9+
- [ ] `docker --version` → Docker çalışıyor
- [ ] `docker ps` → PostgreSQL ve Qdrant container'ları UP
- [ ] `python test_gpu.py` → GPU/CPU tespiti başarılı
- [ ] `python build_vectorDB.py` → Hatasız tamamlandı
- [ ] `uvicorn Text2SQL_Agent:app` → Sunucu başladı
- [ ] `http://localhost:8000/static/chat.html` → Chat arayüzü açıldı
- [ ] Chat'te "test" yazınca → Cevap geliyor

---

## 📞 Yardım ve Destek

Sorun yaşıyorsanız:

**Logları kontrol edin**: Terminal'de hata mesajlarını okuyun
**Dokümantasyon**: README.md ve diğer MD dosyalarını okuyun

---
