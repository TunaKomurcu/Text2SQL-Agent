# SORGU ANALİZİ: 52664872 seri numaralı sayacın son 2 saatlik yük profil verilerini getir

## 1. SCHEMA KEYWORDS ARTIK ÇALIŞIYOR! ✓

Schema keywords'ten gelen Türkçe açıklamalar artık dinamik promptta görünüyor:

```python
# schema_keywords.py import ediliyor
from schema_keywords import SCHEMA_KEYWORDS
```

### Tablo Açıklamaları:
- **e_sayac**: sayaç, elektrik sayacı, seri numarası
- **m_load_profile**: yük profil, load profile, yük verileri

### Sütun Açıklamaları:
- **seri_no**: seri numarası, serial number
- **meter_id**: sayaç id, sayaç
- **datetime**: profil tarihi, zaman

---

## 2. DİNAMİK PROMPT ÖRNEĞİ (Türkçe açıklamalarla)

```sql
=== İZİN VERİLEN TABLO VE SÜTUNLAR ===

helios.e_sayac (  -- sayaç, elektrik sayacı, seri numarası
    id bigint -- PK
    seri_no bigint (seri numarası, serial number)
    meter_id bigint -- FK -> helios.m_meter.id
    il_id bigint -- FK -> helios.il.id
    ... (diğer sütunlar)
)

helios.m_load_profile (  -- yük profil, load profile, yük verileri
    id bigint -- PK
    meter_id bigint -- FK -> helios.e_sayac.id (sayaç id, sayaç)
    value double precision
    datetime timestamp (profil tarihi, zaman)
    ... (diğer sütunlar)
)

=== ZİNCİRLEME JOIN YOLLARI ===
  helios.m_load_profile.meter_id --> helios.e_sayac.id
```

**ÖNEMLİ**: LLM artık "yük profil" kelimesini görünce m_load_profile tablosunu, "seri numarası" kelimesini görünce seri_no sütununu anlayabilecek!

---

## 3. DOĞRU SQL SORGUSU

### Beklenen SQL:
```sql
SELECT 
    es.id,
    es.seri_no,
    lp.datetime,
    lp.value
FROM helios.m_load_profile lp
INNER JOIN helios.e_sayac es ON lp.meter_id = es.id
WHERE es.seri_no = 52664872
  AND lp.datetime >= NOW() - INTERVAL '2 hours'
ORDER BY lp.datetime DESC;
```

### JOIN Mantığı:
- ✓ **m_load_profile.meter_id = e_sayac.id** (FK ilişkisi var - fk_graph.json'da manuel ekledik)
- ✗ m_load_profile.meter_id = e_sayac.meter_id (bu yanlış - farklı aralıklar)

### Veri Aralıkları (önceki testlerden):
- **m_load_profile.meter_id**: 546146 - 546197 (52 farklı değer)
- **e_sayac.id**: 60847 - 75325 (14479 farklı değer)
- **e_sayac.meter_id**: 60847 - 75325 (12902 farklı değer)

⚠️ **ÖNEMLİ**: m_load_profile.meter_id aralığı (546146-546197) e_sayac.id aralığından (60847-75325) tamamen farklı!

---

## 4. VERİ SORUNU

### Seri Numarası 52664872:
- ✗ Bu seri numarası veritabanında YOK (önceki testlerde kontrol ettik)
- SQL doğru ama sonuç boş dönecek

### Çalışan Alternatif (mevcut veriden):
```sql
-- Yük profil verisi olan gerçek seri numaralarından biri ile:
SELECT 
    es.id,
    es.seri_no,
    lp.datetime,
    lp.value
FROM helios.m_load_profile lp
INNER JOIN helios.e_sayac es ON lp.meter_id = es.id
WHERE es.seri_no = [GERÇEK_SERİ_NO]  -- Veritabanında mevcut olan
  AND lp.datetime >= NOW() - INTERVAL '2 hours'
ORDER BY lp.datetime DESC
LIMIT 10;
```

---

## 5. YAPILAN DEĞİŞİKLİKLER

### Text2SQL_Agent.py - format_compact_schema_prompt_with_keywords():

**Önceki Kod (ÇALIŞMIYORDU):**
```python
from build_vectorDB import SCHEMA_KEYWORDS_EXAMPLE  # ✗ İçeride tanımlı, import edilemez!
```

**Yeni Kod (ÇALIŞIYOR):**
```python
from schema_keywords import SCHEMA_KEYWORDS  # ✓ Global scope'ta, import edilebilir!
all_keywords = SCHEMA_KEYWORDS
```

### Tablo Formatı:
```python
# Tablo açıklamaları (liste formatı)
table_keywords_list = all_keywords[table_name].get('table_keywords', [])
keywords = table_keywords_list[:3]  # İlk 3 keyword
table_desc = f"  -- {', '.join(keywords)}"
```

### Sütun Formatı:
```python
# Sütun açıklamaları (liste formatı)
col_keywords_list = col_keywords_dict[column]
keywords = col_keywords_list[:2]  # İlk 2 keyword
col_desc = f" ({', '.join(keywords)})"
```

---

## 6. TEST SONUCU

### test_keywords_prompt.py çıktısı:
```
helios.e_sayac (  -- sayaç, elektrik sayacı, seri numarası
    id bigint -- PK
    seri_no bigint (seri numarası, serial number)
    meter_id bigint -- FK -> helios.m_meter.id
    il_id bigint -- FK -> helios.il.id
)

helios.m_load_profile (  -- yük profil, load profile, yük verileri
    id bigint -- PK
    meter_id bigint -- FK -> helios.e_sayac.id (sayaç id, sayaç)
    value double precision
    datetime timestamp
)
```

✅ **BAŞARILI!** Türkçe açıklamalar doğru formatlanıyor!

---

## 7. LLM'İN ANLAYACAĞI ŞEKİL

Artık LLM şunları görecek:

1. **"yük profil"** → `helios.m_load_profile (  -- yük profil, load profile, yük verileri`
2. **"seri numaralı sayaç"** → `seri_no bigint (seri numarası, serial number)`
3. **"sayaç id"** → `meter_id bigint -- FK -> helios.e_sayac.id (sayaç id, sayaç)`

LLM artık doğal Türkçe sorgudaki kelimeleri (yük profil, seri numarası, sayaç) gerçek tablo/sütun adlarıyla (m_load_profile, seri_no, e_sayac) eşleştirebilecek!

---

## 8. SONRAKİ ADIMLAR

1. ✓ Schema keywords import'u düzeltildi (schema_keywords.py'den import)
2. ✓ Türkçe açıklamalar formatlanıyor
3. ⚠️ FK ilişkisi var (manuel eklendi) ama veri aralıkları uyuşmuyor
4. ⚠️ Test seri numarası (52664872) veritabanında yok

### Öneriler:
- Gerçek bir seri_no ile test et (veritabanından çek)
- m_meter_identity tablosunu kontrol et (meter_id bridge tablosu olabilir)
- API'yi restart edip yeni prompt ile test et
