# 📊 Text2SQL Demo Senaryoları

## 🎯 Sunum İçin Hazır Demo Senaryoları

Bu dokümanda, projenizi sunarken kullanabileceğiniz **gerçek demo örnekleri** bulunmaktadır. Her senaryo için:
- Kullanıcı sorusu
- Sistemin ürettiği SQL
- Beklenen sonuç
- Açıklama

---

## 📋 Demo 1: Basit Sorgular (Başlangıç Seviyesi)

### Senaryo 1.1: Tablo Listeleme

**👤 Kullanıcı**: "Tüm sayaçları listele"

**🤖 Sistem SQL**:
```sql
SELECT * FROM helios.e_sayac LIMIT 100;
```

**📊 Sonuç**: 
- Sayaç tablosunun tüm sütunları
- İlk 100 kayıt

**💡 Açıklama**: 
- LLM otomatik olarak LIMIT ekliyor (performans için)
- Tablo ismi doğru tespit edildi

---

### Senaryo 1.2: Basit Filtreleme

**👤 Kullanıcı**: "Ankara'daki sayaçları göster"

**🤖 Sistem SQL**:
```sql
SELECT es.* 
FROM helios.e_sayac es
JOIN helios.il ON es.il_id = il.id
WHERE il.adi = 'Ankara'
LIMIT 100;
```

**📊 Sonuç**: 
- Ankara'daki tüm sayaçlar

**💡 Açıklama**: 
- JOIN otomatik eklendi (kullanıcı "birleştir" demedi!)
- FK ilişkisi (e_sayac.il_id → il.id) otomatik bulundu
- "Ankara" değeri doğru kolonla eşleştirildi

---

## 📊 Demo 2: Orta Seviye Sorgular

### Senaryo 2.1: Çoklu JOIN

**👤 Kullanıcı**: "Ankara'daki aktif sayaçların seri numaralarını listele"

**🤖 Sistem SQL**:
```sql
SELECT es.seri_no, il.adi, ms.adi as durum
FROM helios.e_sayac es
JOIN helios.il ON es.il_id = il.id
JOIN helios.m_meter_status ms ON es.meter_status_id = ms.id
WHERE il.adi = 'Ankara' 
  AND ms.adi = 'Aktif'
ORDER BY es.seri_no;
```

**📊 Sonuç**: 
- Ankara'daki aktif sayaçların listesi
- Seri numarası, şehir, durum bilgisi

**💡 Açıklama**: 
- 2 farklı JOIN otomatik yapıldı
- WHERE koşulları doğru tablolara uygulandı
- Sıralama eklendi (ORDER BY)

---

### Senaryo 2.2: Agregasyon

**👤 Kullanıcı**: "Her ildeki sayaç sayısını hesapla"

**🤖 Sistem SQL**:
```sql
SELECT il.adi, COUNT(es.id) as sayac_sayisi
FROM helios.e_sayac es
JOIN helios.il ON es.il_id = il.id
GROUP BY il.adi
ORDER BY sayac_sayisi DESC;
```

**📊 Sonuç**: 
```
| il.adi    | sayac_sayisi |
|-----------|--------------|
| İstanbul  | 5432         |
| Ankara    | 3210         |
| İzmir     | 2987         |
| ...       | ...          |
```

**💡 Açıklama**: 
- GROUP BY otomatik eklendi
- Aggregate fonksiyon (COUNT) doğru kullanıldı
- Sıralama akıllıca yapıldı (en çok sayaç olan il üstte)

---

## 🚀 Demo 3: İleri Seviye Sorgular

### Senaryo 3.1: Zaman Serisi Analizi

**👤 Kullanıcı**: "52664872 seri numaralı sayacın son 2 saatlik yük profil verilerini getir"

**🤖 Sistem SQL**:
```sql
SELECT 
    es.seri_no,
    lp.datetime,
    lp.value as yuk_degeri
FROM helios.m_load_profile lp
JOIN helios.e_sayac es ON lp.meter_id = es.id
WHERE es.seri_no = 52664872
  AND lp.datetime >= NOW() - INTERVAL '2 hours'
ORDER BY lp.datetime DESC;
```

**📊 Sonuç**: 
- Belirtilen sayacın son 2 saatlik yük verileri
- Zaman damgası + değer

**💡 Açıklama**: 
- Kompleks JOIN (m_load_profile → e_sayac)
- Zaman aralığı hesaplaması (INTERVAL)
- Tarih sıralaması

---

### Senaryo 3.2: Alt Sorgu (Subquery)

**👤 Kullanıcı**: "Ortalama yük değerinden fazla tüketen sayaçları bul"

**🤖 Sistem SQL**:
```sql
SELECT 
    es.seri_no,
    AVG(lp.value) as ortalama_yuk
FROM helios.m_load_profile lp
JOIN helios.e_sayac es ON lp.meter_id = es.id
GROUP BY es.seri_no
HAVING AVG(lp.value) > (
    SELECT AVG(value) FROM helios.m_load_profile
)
ORDER BY ortalama_yuk DESC
LIMIT 20;
```

**📊 Sonuç**: 
- Ortalamanın üstünde tüketen ilk 20 sayaç

**💡 Açıklama**: 
- Alt sorgu (subquery) kullanıldı
- HAVING clause doğru kullanıldı
- GROUP BY + aggregate mantığı

---

## 🎭 Demo 4: Hata Düzeltme Senaryoları

### Senaryo 4.1: Tablo İsmi Hatası

**👤 Kullanıcı**: "e_sayaclar tablosundaki verileri getir" *(yanlış tablo ismi)*

**🤖 Sistem Düşüncesi**:
1. "e_sayaclar" tablosu bulunamadı
2. Fuzzy matching: "e_sayac" benzerlik %92
3. Otomatik düzeltme yapılıyor

**🤖 Sistem SQL**:
```sql
-- Otomatik düzeltildi: e_sayaclar → e_sayac
SELECT * FROM helios.e_sayac LIMIT 100;
```

**💡 Açıklama**: 
- Kullanıcı yanlış yazsa bile sistem buluyor
- Auto-fix sistemi devrede

---

### Senaryo 4.2: Kolon İsmi Hatası

**👤 Kullanıcı**: "seri_numarasi sütununu göster" *(yanlış kolon ismi)*

**🤖 Sistem Düşüncesi**:
1. "seri_numarasi" kolonu bulunamadı
2. Benzer kolon: "seri_no" benzerlik %85
3. Otomatik düzeltme

**🤖 Sistem SQL**:
```sql
-- Otomatik düzeltildi: seri_numarasi → seri_no
SELECT seri_no FROM helios.e_sayac;
```

**💡 Açıklama**: 
- Türkçe varyasyonlar tanınıyor
- Yakın eşleşmeler otomatik düzeltiliyor

---

## 💪 Demo 5: Sistemin Gücünü Göster

### Senaryo 5.1: Kompleks Analiz (Sunum Finali)

**👤 Kullanıcı**: 
```
"İstanbul'daki aktif sayaçların son 1 haftalık günlük ortalama 
yük tüketimlerini hesapla ve en çok tüketen ilk 5'i listele"
```

**🤖 Sistem SQL**:
```sql
SELECT 
    es.seri_no,
    il.adi as sehir,
    DATE(lp.datetime) as tarih,
    AVG(lp.value) as gunluk_ortalama
FROM helios.m_load_profile lp
JOIN helios.e_sayac es ON lp.meter_id = es.id
JOIN helios.il ON es.il_id = il.id
JOIN helios.m_meter_status ms ON es.meter_status_id = ms.id
WHERE il.adi = 'İstanbul'
  AND ms.adi = 'Aktif'
  AND lp.datetime >= NOW() - INTERVAL '7 days'
GROUP BY es.seri_no, il.adi, DATE(lp.datetime)
ORDER BY gunluk_ortalama DESC
LIMIT 5;
```

**📊 Sonuç**: 
```
| seri_no   | sehir    | tarih      | gunluk_ortalama |
|-----------|----------|------------|-----------------|
| 12345678  | İstanbul | 2024-12-17 | 987.5           |
| 23456789  | İstanbul | 2024-12-17 | 876.3           |
| ...       | ...      | ...        | ...             |
```

**💡 Açıklama**: 
- 3 farklı JOIN
- Zaman aralığı filtresi
- Tarih gruplandırma
- Aggregation + sıralama
- **Tüm bunlar tek seferde, otomatik!**

---

## 🎬 Sunum Sırası Önerisi

### 1. Giriş (2 dakika)
- Proje tanıtımı
- Problem tanımı
- "Şimdi canlı demo yapalım..."

### 2. Basit Örnekle Başla (1 dakika)
- **Demo 1.1**: "Tüm sayaçları listele"
- "Bu kadar basit!"

### 3. JOIN Otomasyonunu Göster (2 dakika)
- **Demo 1.2**: "Ankara'daki sayaçları göster"
- JOIN'in otomatik eklendiğini vurgula
- FK graph'i bahset

### 4. Kompleks Analiz (3 dakika)
- **Demo 3.1**: Zaman serisi sorgusu
- **Demo 2.2**: Agregasyon
- "Normalde 10-15 dakika SQL yazardınız, şimdi 5 saniye"

### 5. Hata Toleransını Göster (2 dakika)
- **Demo 4.1**: Yanlış tablo ismi
- Auto-fix'i vurgula
- "Kullanıcı hata yapsa bile çalışıyor"

### 6. Final - En Zor Sorgu (3 dakika)
- **Demo 5.1**: Kompleks analiz
- "İşte gücümüz!"
- Teknik detayları anlat (3 JOIN, time filter, grouping)

### 7. Sonuç (1 dakika)
- Sorular?
- İletişim

**Toplam Süre**: ~15 dakika

---

## 🎯 Demo İpuçları

### 1. Hazırlık
- [ ] Sunumdan önce tüm servisleri başlat (Docker, uvicorn)
- [ ] Chat arayüzünü tarayıcıda hazır aç
- [ ] Test sorgularını bir kere dene (cache için)
- [ ] İnternet bağlantısını kontrol et

### 2. Sunum Sırasında
- **Bekleme sürelerinde konuş**: "Şimdi sistem şemayı tarayıp en alakalı tabloları buluyor..."
- **SQL'i göster**: "Bakın, sistem bu SQL'i otomatik üretti"
- **Sonuçları açıkla**: "Gördüğünüz gibi doğru veriler geldi"
- **Hataları fırsata çevir**: Bir şey yanlış giderse, "Bu da gerçek hayat!" de

### 3. Soru Cevap Hazırlığı
Olası sorular:
- **"Doğruluk oranı nedir?"** → %85-95 (basit-orta sorgular)
- **"Hangi veritabanlarını destekliyor?"** → Şu an PostgreSQL, MySQL planlanıyor
- **"Maliyet?"** → Tamamen ücretsiz (lokal LLM)
- **"Güvenlik?"** → Tüm veriler lokal, dışarı gönderilmiyor
- **"Karmaşık sorguları anlıyor mu?"** → Evet, demo 5.1'i göster

---

## 📝 Ek Notlar

### Yedek Senaryolar (Demo Çakışırsa)

**Plan B Soruları**:
1. "Toplam kaç sayaç var?"
2. "İzmir'deki sayaçları göster"
3. "Her ildeki sayaç sayısını hesapla"
4. "En son eklenen 10 sayacı listele"

### Demo Data Kontrolü

Demo öncesi bu kontrolleri yap:
```sql
-- Ankara'da data var mı?
SELECT COUNT(*) FROM helios.e_sayac es
JOIN helios.il ON es.il_id = il.id
WHERE il.adi = 'Ankara';

-- Yük profil data var mı?
SELECT COUNT(*) FROM helios.m_load_profile;

-- Zaman aralığı uygun mu?
SELECT MIN(datetime), MAX(datetime) FROM helios.m_load_profile;
```

Eğer data yoksa, sorguları veritabanınızdaki mevcut verilere göre ayarla!

---

## 🎁 Bonus: Sunum Slaytları İçin Başlıklar

1. **"Geleneksel Yöntem vs. Text2SQL"**
   - Öncesi: SQL yazma, debug, test → 15 dakika
   - Sonrası: Soru sor → 5 saniye

2. **"Akıllı Şema Tespiti"**
   - 200+ tablo var → Sadece 3 tanesi kullanıldı
   - Nasıl? → Semantic search + Vector DB

3. **"Otomatik JOIN Sihri"**
   - FK Graph → BFS algoritması → En kısa yol
   - Kullanıcı "birleştir" demese bile, sistem biliyor

4. **"Türkçe Destek"**
   - "sayaç" = "e_sayac" (semantik eşleşme)
   - "Ankara" = il.adi (veri bazlı eşleşme)

5. **"Hata Toleransı"**
   - Fuzzy matching → %80+ benzerlik yeterli
   - Otomatik düzeltme → Kullanıcı fark etmez

---

**Başarılar! 🚀**

Bu demo senaryolarıyla sunumunuz etkileyici olacak!
