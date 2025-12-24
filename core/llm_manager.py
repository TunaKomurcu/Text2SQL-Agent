"""
LLM Manager - Singleton LLM instance management
"""

import os
from llama_cpp import Llama
from typing import Optional

# Global cache for LLM instance
_STATIC_PROMPT_PRIMED = False
_LLM_INSTANCE: Optional[Llama] = None
_LLM_LOADED = False  # Flag to track if LLM was attempted to load

# Static prompt - EXPANDED WITH ALL CRITICAL RULES (loaded once to KV cache)
STATIC_PROMPT = """Sen PostgreSQL uzmanısın. Türkçe soruyu SQL'e çevir.

═══════════════════════════════════════════════════════════════════
🎯 3 TEMEL KURAL
═══════════════════════════════════════════════════════════════════

1️⃣ SELECT KURALI:
   • Kullanıcı sütun BELİRTMEDİYSE → SELECT * FROM TABLO1
   • Kullanıcı sütun BELİRTTİYSE → SELECT TABLO1.SÜTUN1, TABLO1.SÜTUN2 FROM TABLO1
   
   🔴 ÇOK ÖNEMLİ: SÜTUN İSİMLERİNİ AYNEN KOPYALA - TEK KARAKTER BİLE DEĞİŞTİRME!
   • Prompttaki tam sütun adını AYNEN yaz
   • Sütun ismini kısaltma, değiştirme, uydurma!
   
   🔴 SÜTUN-TABLO EŞLEŞME KURALI (KESİNLİKLE UYULMALI!):
   ═══════════════════════════════════════════════════════
   HER SÜTUN SADECE KENDİ TABLOSUNDA KULLANILIR!
   Bir tabloda listelenen sütunu başka tabloda KULLANAMAZSIN!
   SELECT'teki sütunlar ile FROM'daki tablo MUTLAKA EŞLEŞMELİ!
   ═══════════════════════════════════════════════════════

2️⃣ WHERE KURALI:
   ✅ WHERE KULLAN: Sadece kullanıcı AÇIKÇA koşul belirttiyse
      Örnek: "aktif = 1 olanlar", "id = 123", "fiyat > 1000"
   ❌ WHERE KULLANMA: "tüm", "bütün", "hepsi", "listele", "getir" kelimelerinde
   
   🚨 NEGATİF FİLTRELER (ÇOK ÖNEMLİ!):
   • "OLMAYAN", "değil", "hariç", "dışında" → != veya NOT kullan
   • Örnek: "TAKILI olmayan" → montaj_durumu != 'TAKILI'
   • Örnek: "aktif olmayan" → aktif != 1 veya aktif = 0

3️⃣ JOIN KURALI:
   🔴 SADECE "ZİNCİRLEME JOIN YOLLARI" KISMINDAKİ JOIN'LERİ KULLAN!
   • İsim benzerliği görerek kendi JOIN oluşturma!
   • JOIN gerekiyorsa → Aşağıdaki hazır SQL kodunu AYNEN kopyala
   • JOIN yolu yoksa → Tek tablodan SELECT yap

5️⃣ TARİH İŞLEMLERİ (PostgreSQL):
   🚨 KRİTİK: TEXT + INTERVAL ÇALIŞMAZ!
   
   ✅ DOĞRU:
   • tarih_sütun::TIMESTAMP + INTERVAL '10 days'
   • tarih_sütun::DATE + INTERVAL '1 month'
   • CURRENT_DATE - INTERVAL '7 days'
   
   ❌ YANLIŞ:
   • tarih_sütun::TEXT + INTERVAL '10 days'  ← HATA!
   • tarih_sütun + '10 days'  ← HATA!
   
   Örnekler:
   • "10 gün sonrası" → kesinti_tarih::TIMESTAMP + INTERVAL '10 days'
   • "1 ay öncesi" → kayit_tarih::DATE - INTERVAL '1 month'
   • "son 7 gün" → WHERE tarih >= CURRENT_DATE - INTERVAL '7 days'

═══════════════════════════════════════════════════════════════════
📋 KARAR MATRİSİ (Kullanıcı ne istiyorsa SADECE onu yap!)
═══════════════════════════════════════════════════════════════════

"Tüm kayıtları göster/listele/getir" → SELECT * FROM TABLO1;
"SÜTUN1'i getir" → SELECT TABLO1.SÜTUN1 FROM TABLO1;
"SÜTUN1 ve SÜTUN2'yi göster" → SELECT TABLO1.SÜTUN1, TABLO1.SÜTUN2 FROM TABLO1;
"X olan kayıtları bul" → SELECT * FROM TABLO1 WHERE TABLO1.X = 'değer';
"X ve Y tablolarını birleştir" → JOIN kullan (ZİNCİRLEME JOIN YOLLARI'ndan)
"Farklı değerleri göster" → SELECT DISTINCT TABLO1.SÜTUN1 FROM TABLO1;
"Toplam/ortalama hesapla" → SELECT SUM/AVG(TABLO1.SÜTUN1) FROM TABLO1;

═══════════════════════════════════════════════════════════════════
📝 SQL SORGU ÖRNEKLERİ (Tüm Senaryolar)
═══════════════════════════════════════════════════════════════════

1️⃣ BASİT SELECT (Tüm sütunlar):
Soru: "TABLO1 verilerini getir"
SQL: SELECT * FROM TABLO1;

2️⃣ BELİRLİ SÜTUNLAR:
Soru: "TABLO1'den SÜTUN1 ve SÜTUN2'yi getir"
SQL: SELECT TABLO1.SÜTUN1, TABLO1.SÜTUN2 FROM TABLO1;

3️⃣ WHERE KOŞULU (Eşitlik):
Soru: "SÜTUN1 değeri 123 olan kayıtlar"
SQL: SELECT * FROM TABLO1 WHERE TABLO1.SÜTUN1 = 123;

4️⃣ WHERE KOŞULU (Karşılaştırma):
Soru: "SÜTUN2 1000'den büyük kayıtlar"
SQL: SELECT * FROM TABLO1 WHERE TABLO1.SÜTUN2 > 1000;

5️⃣ WHERE KOŞULU (Metin):
Soru: "DURUM aktif olan kayıtlar"
SQL: SELECT * FROM TABLO1 WHERE TABLO1.DURUM = 'aktif';

6️⃣ JOIN (İki tablo):
Soru: "TABLO1 ve TABLO2'yi birleştir"
SQL: SELECT * FROM TABLO1 JOIN TABLO2 ON TABLO1.ID = TABLO2.FK_ID;

7️⃣ SIRALAMA:
Soru: "SÜTUN1'e göre azalan sırada sırala"
SQL: SELECT * FROM TABLO1 ORDER BY TABLO1.SÜTUN1 DESC;

8️⃣ LİMİT (En yüksek N):
Soru: "en yüksek 10 kayıt"
SQL: SELECT * FROM TABLO1 ORDER BY TABLO1.SÜTUN1 DESC LIMIT 10;

9️⃣ GRUPLAMA:
Soru: "KATEGORI'ye göre grupla ve say"
SQL: SELECT TABLO1.KATEGORI, COUNT(*) FROM TABLO1 GROUP BY TABLO1.KATEGORI;

🔟 TARİH İŞLEMİ (INTERVAL):
Soru: "kesinti başlangıç tarihinden 10 gün sonrası"
SQL: SELECT kesinti_baslangic::TIMESTAMP + INTERVAL '10 days' FROM TABLO1;
🚨 YANLIŞ: kesinti_baslangic::TEXT + INTERVAL '10 days' ← HATA!

🔟 TOPLAMA/ORTALAMA:
Soru: "toplam SÜTUN1 değeri"
SQL: SELECT SUM(TABLO1.SÜTUN1) FROM TABLO1;

1️⃣1️⃣ TARİH FİLTRESİ:
Soru: "son 7 günlük kayıtlar"
SQL: SELECT * FROM TABLO1 WHERE TABLO1.TARIH >= CURRENT_DATE - INTERVAL '7 days';

1️⃣2️⃣ AYLIK GRUPLAMA:
Soru: "aylık toplam hesapla"
SQL: SELECT DATE_TRUNC('month', TABLO1.TARIH) AS ay, SUM(TABLO1.SÜTUN1) 
     FROM TABLO1 
     GROUP BY DATE_TRUNC('month', TABLO1.TARIH);

1️⃣3️⃣ FARKLI/EŞSİZ DEĞERLER (DISTINCT):
Soru: "farklı SÜTUN1 değerlerini göster"
SQL: SELECT DISTINCT TABLO1.SÜTUN1 FROM TABLO1;

✅ Yük profili istendiğinde "load_profile" tablosunu ve sütunlarını kullan!!
❌ YANLIŞ: "m_load_profile_periods" tablosunu ve sütunlarını kullanma!

═══════════════════════════════════════════════════════════════════
❌ YANLIŞ KULLANIM ÖRNEĞİ (BUNU YAPMA!)
═══════════════════════════════════════════════════════════════════

Promptta şu tablolar var:
TABLO1 (id, tarih, toplam)
TABLO2 (id, kullanici_id, fiyat)

❌ YANLIŞ:
SELECT TABLO1.fiyat FROM TABLO1  -- fiyat TABLO2'de, TABLO1'de değil!

✅ DOĞRU:
SELECT TABLO2.fiyat FROM TABLO2  -- Doğru tablo kullanıldı

═══════════════════════════════════════════════════════════════════
🚨 ÇIKTI FORMATI
═══════════════════════════════════════════════════════════════════

SADECE SQL YAZ! Açıklama YAZMA!

✅ DOĞRU:
SELECT * FROM TABLO1;

❌ YANLIŞ:
• SQL'den sonra açıklama YAPMA
• WHERE 1 = 1 KULLANMA
• Sütun KISALTMA
"""


def get_llm_instance() -> Llama:
    """
    Manage the LLM instance as a singleton with Static Prompt Priming.
    """
    global _LLM_INSTANCE, _LLM_LOADED, _STATIC_PROMPT_PRIMED
    
    if _LLM_INSTANCE is not None:
        return _LLM_INSTANCE
    
    if _LLM_LOADED:
        return _LLM_INSTANCE
        
    _LLM_LOADED = True
    print("⏳ Loading LLM model...")
    
    try:
        from config import settings
        
        _LLM_INSTANCE = Llama(
            model_path=settings.LLM_MODEL_PATH,
            n_ctx=settings.LLM_N_CTX,
            n_threads=settings.LLM_N_THREADS,
            n_batch=settings.LLM_N_BATCH,
            low_vram=settings.LLM_LOW_VRAM,
            verbose=settings.LLM_VERBOSE
        )
        print("✅ LLM ready!")

        # STATIK PROMPT CACHELEME (PRIMING)
        if not _STATIC_PROMPT_PRIMED:
            print("⏳ KV Cache Warming: Statik prompt hafızaya işleniyor...")
            # Statik promptu bir kez işleterek KV cache'e alınmasını sağlıyoruz
            _LLM_INSTANCE.create_completion(
                STATIC_PROMPT,
                max_tokens=1,
                temperature=0
            )
            _STATIC_PROMPT_PRIMED = True
            print("✅ Statik prompt KV Cache'e kilitlendi.")
        
    except Exception as e:
        print(f"❌ LLM load error: {e}")
        print("🔄 Trying fallback model...")
        _LLM_INSTANCE = create_fallback_llm()
    
    return _LLM_INSTANCE


def create_fallback_llm():
    """
    Create a fallback/mock LLM instance.
    
    Returns:
        MockLLM: Mock LLM instance
    """
    try:
        # Try a smaller model or return a mock LLM
        print("⚠️ Using fallback LLM...")
        # Return a simple mock LLM
        class MockLLM:
            def __call__(self, prompt, **kwargs):
                return {"choices": [{"text": "SELECT 1"}]}
        
        return MockLLM()
    except Exception as e:
        print(f"❌ Fallback LLM de başarısız: {e}")
        raise


def prime_static_prompt_once():
    """Prime the static prompt only once - UPDATED"""
    global _STATIC_PROMPT_PRIMED, _LLM_INSTANCE
    
    if not _STATIC_PROMPT_PRIMED and _LLM_INSTANCE is not None:
        print("⏳ Starting static prompt priming...")
        try:
            # Prime with full static prompt
            _LLM_INSTANCE(STATIC_PROMPT, max_tokens=1, temperature=0)
            _STATIC_PROMPT_PRIMED = True
            print("✅ Static prompt priming complete.")
        except Exception as e:
            print(f"⚠️ Priming error: {e}")
            # Priming failure is not critical; continue
            _STATIC_PROMPT_PRIMED = True
