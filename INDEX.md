# 📚 Dokümantasyon İndeksi

Bu dokümantasyon paketi, **Text2SQL** projesini iş yerinde sunum yapmanız için hazırlanmıştır.

---

## 📖 Dokümantasyon Dosyaları

### 1. **README.md** - Ana Giriş Dokümanı
**Ne zaman kullanılır?**: İlk başvuru kaynağı, genel bakış  
**İçeriği**:
- Projeye hızlı giriş
- Kurulum adımları (özet)
- Temel özellikler
- Tüm dokümantasyonlara linkler

**Kitle**: Teknik ve teknik olmayan herkes

---

### 2. **SUNUM.md** - Sunum Dokümanı 🎯
**Ne zaman kullanılır?**: İş yerinde sunum yaparken  
**İçeriği**:
- Proje özeti (elevator pitch)
- Çözdüğü problemler
- Sistem mimarisi (basit diyagramlar)
- Nasıl çalışır? (adım adım)
- Güçlü yönler
- Demo senaryosu
- SSS
- İş değeri

**Kitle**: Yöneticiler, iş birimi, karar vericiler  
**Süre**: 15-20 dakikalık sunum için hazır

**💡 İpucu**: Bu dosyayı PowerPoint slaytlarına dönüştürebilirsiniz!

---

### 3. **DEMO_SENARYOLARI.md** - Canlı Demo Kılavuzu 🎬
**Ne zaman kullanılır?**: Sunum sırasında canlı demo yapacaksanız  
**İçeriği**:
- Hazır demo senaryoları (basit → kompleks)
- Beklenen SQL ve sonuçlar
- Hata düzeltme örnekleri
- Sunum sırası önerisi
- Demo ipuçları ve püf noktaları
- Yedek senaryolar

**Kitle**: Sunumu yapan kişi (sizin için)  
**Kullanım**: Demo öncesi bu dosyayı okuyun ve hazırlanın

**💡 İpucu**: Demo öncesi tüm senaryoları bir kere deneyin!

---

### 4. **MIMARI.md** - Teknik Mimari Dokümantasyonu 🏗️
**Ne zaman kullanılır?**: Teknik sorular geldiğinde  
**İçeriği**:
- Detaylı sistem mimarisi
- Veri akışı (diyagramlar)
- Bileşen detayları (kod örnekleriyle)
- Algoritmalar (BFS, hybrid search, vb.)
- Veritabanı yapısı
- Performans optimizasyonları

**Kitle**: Yazılım geliştiriciler, teknik ekip, mimarlar  
**Derinlik**: Çok detaylı, kod snippet'leri var

**💡 İpucu**: Sunum sırasında teknik soru gelirse buraya bakın!

---

### 5. **KURULUM_KILAVUZU.md** - Kurulum Adımları 🚀
**Ne zaman kullanılır?**: Projeyi kurmak isteyen biri olduğunda  
**İçeriği**:
- Sistem gereksinimleri
- Adım adım kurulum (3 seçenek: GPU/CPU/Otomatik)
- Veritabanı konfigürasyonu
- Model indirme
- Detaylı sorun giderme (7 yaygın problem)

**Kitle**: Kurulum yapacak teknik kişi  
**Süre**: Takip ederek 30-60 dakikada kurulum tamamlanır

**💡 İpucu**: Sorun yaşanırsa "Sorun Giderme" bölümüne bakın!

---

### 6. **CHEAT_SHEET.md** - Hızlı Referans Kılavuzu ⚡
**Ne zaman kullanılır?**: Günlük çalışırken, hızlı komut arama  
**İçeriği**:
- Sık kullanılan komutlar
- Konfigürasyon örnekleri
- Port bilgileri
- Test komutları
- Production deployment
- Kısayollar

**Kitle**: Proje üzerinde çalışan herkes  
**Format**: Kompakt, aranabilir, hızlı referans

**💡 İpucu**: Yazdırıp masanızda bulundurun!

---

### 7. **DOSYA_YAPISI.md** - Klasör Yapısı 📁
**Ne zaman kullanılır?**: Proje yapısını anlamak için  
**İçeriği**:
- Klasör organizasyonu
- Her klasörün görevi
- Önemli dosyalar
- Ortam değişkenleri

**Kitle**: Projeyi yeni keşfedenler

---

### 8. **SORGU_ANALIZI.md** - Sorgu Debug Notları 🔍
**Ne zaman kullanılır?**: Mevcut dosya (proje geliştirme sırasında tutulmuş)  
**İçeriği**:
- Örnek sorgu analizi
- Schema keywords nasıl çalışır
- Veri sorunları

**Kitle**: Geliştirici

---

## 🎯 Sunum için Hangi Dosyayı Kullanmalıyım?

### Senaryo 1: "Yöneticilere sunum yapacağım" (15-20 dakika)
**Kullan**: 
1. **SUNUM.md** - Ana içerik (slaytlara dönüştür)
2. **DEMO_SENARYOLARI.md** - Canlı demo için (not olarak yanında)

**Akış**:
- SUNUM.md'deki sırayı takip et
- Demo yaparken DEMO_SENARYOLARI.md'ye bak
- Teknik soru gelirse MIMARI.md'ye hızlıca göz at

---

### Senaryo 2: "Teknik ekibe teknik detay anlatacağım" (30-45 dakika)
**Kullan**:
1. **MIMARI.md** - Ana içerik
2. **README.md** - Giriş için
3. **DEMO_SENARYOLARI.md** - Demo için

**Akış**:
- README.md ile başla (5 dk)
- MIMARI.md detaylarını anlat (25 dk)
- DEMO_SENARYOLARI.md ile canlı göster (10 dk)

---

### Senaryo 3: "Birisi projeyi kurmak istiyor"
**Kullan**:
1. **KURULUM_KILAVUZU.md** - Takip edilecek adımlar
2. **CHEAT_SHEET.md** - Hızlı referans için

**Akış**:
- KURULUM_KILAVUZU.md'yi adım adım takip et
- Sorun çıkarsa CHEAT_SHEET.md'ye bak
- Hala çözülmezse KURULUM_KILAVUZU.md → Sorun Giderme

---

### Senaryo 4: "Genel tanıtım yapacağım" (5-10 dakika)
**Kullan**:
1. **README.md** - Özet bilgi
2. **DEMO_SENARYOLARI.md** - Hızlı bir demo

**Akış**:
- README.md'deki "Kullanım Örneği" bölümünü göster
- DEMO_SENARYOLARI.md'den Demo 1.2 veya Demo 5.1 yap
- "Detaylı bilgi için dokümantasyona bakın" de

---

## 📋 Sunum Öncesi Checklist

### 1 Gün Önce
- [ ] Tüm servisleri başlat (Docker, uvicorn)
- [ ] DEMO_SENARYOLARI.md'deki tüm senaryoları test et
- [ ] GPU/CPU durumunu kontrol et
- [ ] Sunum dosyalarını (SUNUM.md, DEMO_SENARYOLARI.md) yazdır/aç

### Sunum Günü (1 Saat Önce)
- [ ] Servisleri başlat
- [ ] http://localhost:8000/static/chat.html açık olsun
- [ ] DEMO_SENARYOLARI.md'yi yan monitörde aç
- [ ] İnternet bağlantısını kontrol et
- [ ] Yedek sorguları not al

### Sunum Sırasında
- [ ] SUNUM.md akışını takip et
- [ ] Demo yaparken sistem düşüncesini açıkla
- [ ] Hata çıkarsa sakin kal, "Gerçek hayat!" de

---

## 💡 Dokümantasyon Kullanım İpuçları

### 1. PowerPoint Slayt Hazırlama
SUNUM.md içeriğini kopyala yapıştır:
- Her `##` başlık → Yeni slayt
- `###` alt başlıklar → Bullet points
- Code block'lar → Syntax highlighted text
- Diyagramları elle çiz veya draw.io kullan

### 2. Yazdırma
Yazdırılabilir versiyonlar:
- **CHEAT_SHEET.md** → A4, 2 sayfa (masada dursun)
- **DEMO_SENARYOLARI.md** → A4, demo sırasında yan taraf

### 3. Dijital Sunum
- SUNUM.md → VS Code'da Preview modu ile göster
- DEMO_SENARYOLARI.md → Yan monitörde aç
- Chat arayüzü → Ana ekranda göster

---

## 🔗 Dosya Bağlantıları

Tüm dosyalar birbirine link verir:

```
README.md
    ├─► SUNUM.md
    ├─► MIMARI.md
    ├─► KURULUM_KILAVUZU.md
    ├─► DEMO_SENARYOLARI.md
    ├─► CHEAT_SHEET.md
    └─► DOSYA_YAPISI.md
```

Her dosyanın içinde diğer dosyalara linkler var. İhtiyacınıza göre gezinin!

---

## ⭐ En Önemli 3 Dosya

Zamanınız kısıtlıysa sadece bunları okuyun:

1. **SUNUM.md** - Sunum için her şey burada
2. **DEMO_SENARYOLARI.md** - Canlı demo için zorunlu
3. **CHEAT_SHEET.md** - Hızlı komutlar

---

## 📞 Yardım

Bir dosyada bulamadığınız bilgi varsa:

1. **INDEX.md** (bu dosya) → Hangi dosyada ne var?
2. **README.md** → Tüm dosyalara link var
3. **CHEAT_SHEET.md** → Hızlı arama için

---

## 📝 Dosya Boyutları (Yaklaşık)

| Dosya | Satır | Okuma Süresi |
|-------|-------|--------------|
| README.md | ~400 | 10 dakika |
| SUNUM.md | ~500 | 15 dakika |
| DEMO_SENARYOLARI.md | ~450 | 12 dakika |
| MIMARI.md | ~650 | 25 dakika |
| KURULUM_KILAVUZU.md | ~600 | 20 dakika |
| CHEAT_SHEET.md | ~450 | 10 dakika |
| DOSYA_YAPISI.md | ~135 | 5 dakika |

**Toplam**: ~3000 satır, ~90 dakika okuma

---

## 🎓 Son Notlar

Bu dokümantasyon paketi, projenizi her açıdan anlatabilmeniz için hazırlanmıştır:

- **İş değeri** → SUNUM.md
- **Teknik detay** → MIMARI.md
- **Pratik kullanım** → KURULUM_KILAVUZU.md + CHEAT_SHEET.md
- **Canlı gösteri** → DEMO_SENARYOLARI.md

**Başarılar! 🚀**

---

**Oluşturulma Tarihi**: 18 Aralık 2024  
**Proje**: Text2SQL Türkçe AI Sistemi  
**Versiyon**: 1.0
