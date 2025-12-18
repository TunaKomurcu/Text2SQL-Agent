# 🐳 Docker Yapılandırma Kılavuzu

## **📁 Docker Klasörü İçeriği**

```
docker/
├── Dockerfile                  # Python app container tanımı
├── entrypoint.sh              # Container başlangıç scripti
├── docker-compose.yml         # Production ortam (3 container)
├── docker-compose.local.yml   # Local development (2 container)
└── init_db.sql                # PostgreSQL başlangıç şeması
```

---

## **🎯 HANGI DOSYA HANGİ İŞE YARIYOR?**

### **1️⃣ Dockerfile**
- **Amaç:** Python uygulamasını containerize etmek
- **İçerik:** Python 3.11, dependencies, FastAPI app
- **Kullanım:** `docker build` komutu ile image oluşturur
- **Ne zaman gerekli:** Production deployment'ta

### **2️⃣ entrypoint.sh**
- **Amaç:** Container başladığında çalışan script
- **İçerik:** Model dosyalarını kontrol eder, uvicorn başlatır
- **Neden docker/ altında:** Dockerfile ile birlikte tutmak için (organizasyon)
- **Özellik:** Model eksikse uyarı verir ama yine de başlatır

### **3️⃣ docker-compose.yml** (Production - Orjinal DB)
- **Amaç:** 3 servisi birlikte çalıştırmak
- **Containerlar:**
  1. `text2sql` → FastAPI uygulaması (Port 8000)
  2. `db` → PostgreSQL (Port 5432)
  3. `qdrant` → Vektör DB (Port 6334)
- **Kullanım:** Production/deployment ortamı (Kendi DB'nizi bağlamak için)

### **4️⃣ docker-compose.local.yml** (Local - Örnek DB)
- **Amaç:** Sadece DB servislerini çalıştırmak
- **Containerlar:**
  1. `db_local` → PostgreSQL + init_db.sql (Port 55432)
  2. `qdrant_local` → Vektör DB (Port 6333)
- **Kullanım:** Local development (Python host'ta çalışır, örnek DB kullanılır)
- **Fark:** Örnek DB (defaultdb) otomatik yüklenir (init_db.sql)

### **5️⃣ init_db.sql**
- **Amaç:** PostgreSQL ilk başladığında örnek DB oluşturmak
- **İçerik:** defaultdb schema, 8 tablo, örnek veriler
- **Kullanım:** Sadece docker-compose.local.yml'de kullanılır
- **Tetikleme:** PostgreSQL container ilk kez başladığında otomatik çalışır

---

## **🚀 KULLANIM SENARYOları**

### **📘 SENARYO 1: Local Development - Örnek DB (ÖNERİLEN)**

**Ne yapıyorsun:**
- Python kodunu host'ta çalıştırıyorsun (VSCode'da debug yapabilirsin)
- Sadece DB'leri Docker'da çalıştırıyorsun
- **Örnek DB (defaultdb)** kullanıyorsun (init_db.sql ile otomatik yüklenir)

**Komutlar:**
```powershell
# docker/ klasöründeyken:
cd docker
docker-compose -f docker-compose.local.yml up -d

# Veya root'tan:
docker-compose -f docker/docker-compose.local.yml up -d

# Python uygulamasını host'ta çalıştır:
uvicorn Text2SQL_Agent:app --reload
```

**Çalışan containerlar:**
- ✅ `text2sql_db_local` (PostgreSQL, Port 55432)
- ✅ `text2sql_qdrant_local` (Qdrant, Port 6333)

**Avantajlar:**
- Kod değişikliği anında yansır
- Debug kolay
- Hızlı geliştirme
- Örnek veri ile test etmek kolay

**Orjinal DB'ye geçiş yapmak için:**
- `.env` dosyasında SEÇENEK 2'yi aktif yap (kendi DB bilgilerinizi girin)
- Qdrant port'unu 6334 yap

---

### **📕 SENARYO 2: Full Production - Orjinal DB (Docker'da Her Şey)**

**Ne yapıyorsun:**
- Hem Python uygulamasını hem DB'leri Docker'da çalıştırıyorsun
- Gerçek deployment senaryosu
- **Kendi production DB'niz** varsa bunu kullan (.env'de ayarlarınızı yapın)

**Komutlar:**
```powershell
# docker/ klasöründeyken:
cd docker
docker-compose -f docker-compose.yml up -d

# Veya root'tan:
docker-compose -f docker/docker-compose.yml up -d
```

**Çalışan containerlar:**
- ✅ `text2sql_app` (FastAPI, Port 8000)
- ✅ `text2sql_db` (PostgreSQL, Port 5432)
- ✅ `text2sql_qdrant` (Qdrant, Port 6334)

**Avantajlar:**
- Production'a yakın ortam
- Tüm sistem izole
- Deploy edilebilir

**Dezavantajlar:**
- Kod değişikliği için rebuild gerekir
- Debug daha zor

---

## **🔍 PORT FARKLILIKLARI**

| Servis | Örnek DB (Local) | Orjinal DB (Production) |
|--------|---------------------|------------------------|
| PostgreSQL | 55432 (docker-compose.local.yml) | 5432 (docker-compose.yml) |
| Qdrant | 6333 | 6334 |
| FastAPI | 8000 (host'ta) | 8000 (container'da) |

**Neden farklı portlar?**
- **Örnek DB (Local):** PostgreSQL 55432 kullanır (host'taki 5432 ile çakışmasın)
- **Orjinal DB (Production):** Standart portlar kullanılır
- **Qdrant:** İki ortam aynı anda çalışabilsin diye farklı portlar

---

## **❓ NEDEN ENTRYPOINT.SH DOCKER/ ALTINDA?**

### **Organizasyon Mantığı:**

```
docker/
├── Dockerfile          ← Container tanımı
├── entrypoint.sh       ← Container başlangıç scripti
├── docker-compose.yml  ← Container orchestration
└── init_db.sql         ← Container içindeki DB init
```

**Sebep:**
1. **İlişkili dosyalar bir arada:** Dockerfile, entrypoint, compose dosyaları hepsi "containerization" ile ilgili
2. **Temiz root klasör:** Root'ta sadece Python kodları olsun
3. **Docker bağımlılıkları bir yerde:** Docker ile ilgili her şey `docker/` altında

**Dockerfile nasıl buluyor?**
```dockerfile
COPY docker/entrypoint.sh /app/entrypoint.sh
```
- Build context root'ta olduğu için `docker/` yolunu kullanıyor

---

## **🛠️ YAYGN KOMUTLAR**

### **Container'ları Başlat:**
```powershell
# Local
docker-compose -f docker/docker-compose.local.yml up -d

# Production
docker-compose -f docker/docker-compose.yml up -d
```

### **Container'ları Durdur:**
```powershell
# Local
docker-compose -f docker/docker-compose.local.yml down

# Production
docker-compose -f docker/docker-compose.yml down
```

### **Logları Görüntüle:**
```powershell
# Local
docker-compose -f docker/docker-compose.local.yml logs -f

# Specific container
docker logs text2sql_db_local -f
```

### **Yeniden Başlat:**
```powershell
docker-compose -f docker/docker-compose.local.yml restart
```

### **Volume'leri de Sil (Dikkat! Veri kaybı):**
```powershell
docker-compose -f docker/docker-compose.local.yml down -v
```

---

## **🔄 ÖNEMLİ NOTLAR**

### **1. Build Context:**
- Dockerfile `docker/` içinde ama build context **root klasör**
- Bu yüzden `docker-compose.yml`'de:
  ```yaml
  build:
    context: ..          # Root klasöre git
    dockerfile: docker/Dockerfile  # Bu dosyayı kullan
  ```

### **2. .env Dosyası:**
- Örnek DB (Local) kullanırken: SEÇENEK 1 aktif, QDRANT_PORT=6333
- Orjinal DB (Production) kullanırken: SEÇENEK 2 aktif (kendi DB bilgilerinizi yazın), QDRANT_PORT=6334
- **Sadece .env'yi değiştirince otomatik geçiş yapar**
- Container içine kopyalanır

### **3. Models Klasörü:**
- Her iki senaryoda da `models/` klasörü mount edilir
- Model dosyaları container içinde `/app/models/` yolunda

### **4. init_db.sql:**
- **Sadece** `docker-compose.local.yml`'de kullanılır
- **İlk çalıştırmada** PostgreSQL otomatik yükler
- Tekrar yüklemek için: volume'ü sil ve restart

---

## **⚠️ TROUBLESHOOTING**

### **"Model not found" hatası:**
```bash
# entrypoint.sh kontrol eder ve uyarı verir
# Çözüm: models/ klasörüne model dosyalarını koy
```

### **Port already in use:**
```bash
# Çözüm: docker-compose.yml'deki portları değiştir
ports:
  - "5433:5432"  # Host port'u değiştir
```

### **Database connection refused:**
```bash
# .env dosyasını kontrol et:

# Örnek DB (Local) için:
DB_PORT=55432
DB_NAME=defaultdb
QDRANT_PORT=6333

# Orjinal DB (Production) için:
DB_PORT=5432
DB_NAME=<kendi_db_adınız>
QDRANT_PORT=6334
```

---

**Docker yapılandırması güncel ve hazır! 🎉**
