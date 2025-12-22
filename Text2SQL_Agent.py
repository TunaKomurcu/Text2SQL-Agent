"""
SMART TEXT-TO-SQL SERVER with STRICT SCHEMA ENFORCEMENT
- Find target tables via semantic search
- Auto-detect intermediate tables via graph traversal
- STRICT: LLM may only use real table/column names
- Auto-Fix: Automatically correct near-matches
"""


from functools import lru_cache

from config import settings, create_qdrant_client, get_db_conn_kwargs

# 🔍 DEBUG: Print threshold values on startup
print(f"🔍 [CONFIG] SEMANTIC_THRESHOLD: {settings.SEMANTIC_THRESHOLD}")
print(f"🔍 [CONFIG] LEXICAL_THRESHOLD: {settings.LEXICAL_THRESHOLD}")
print(f"🔍 [CONFIG] KEYWORD_THRESHOLD: {settings.KEYWORD_THRESHOLD}")
print(f"🔍 [CONFIG] DATA_VALUES_THRESHOLD: {settings.DATA_VALUES_THRESHOLD}")

import os
import re
import time
import json
import asyncio
from typing import List, Dict, Set, Tuple


# ==================== GPU DETECTION UTILITY ====================
def detect_gpu_availability():
    """
    Otomatik GPU tespiti. Torch varsa ve CUDA kullanılabilirse GPU'yu kullan.
    Yoksa CPU'ya düşer, hata vermez.
    
    Returns:
        dict: {'available': bool, 'device': str, 'device_name': str, 'count': int}
    """
    gpu_info = {
        'available': False,
        'device': 'cpu',
        'device_name': 'CPU',
        'count': 0
    }
    
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info['available'] = True
            gpu_info['device'] = 'cuda'
            gpu_info['count'] = torch.cuda.device_count()
            gpu_info['device_name'] = torch.cuda.get_device_name(0)
            print(f"🎮 GPU tespit edildi: {gpu_info['device_name']} ({gpu_info['count']} cihaz)")
        else:
            print("💻 CUDA uyumlu GPU bulunamadı, CPU kullanılacak")
    except ImportError:
        print("💻 PyTorch yüklü değil, CPU kullanılacak")
    except Exception as e:
        print(f"⚠️ GPU tespiti sırasında hata: {e}, CPU kullanılacak")
    
    return gpu_info


# GPU durumunu başlangıçta tespit et
GPU_INFO = detect_gpu_availability()

# SentenceTransformer için device seçimi
DEVICE = GPU_INFO['device'] if (settings.USE_GPU is None or settings.USE_GPU) else 'cpu'
if settings.USE_GPU is False:
    print("⚙️ Ayarlardan dolayı CPU zorlandı")
    DEVICE = 'cpu'
elif settings.USE_GPU is True and not GPU_INFO['available']:
    print("⚠️ GPU kullanımı istendi ama GPU bulunamadı, CPU kullanılacak")
    DEVICE = 'cpu'

print(f"🔧 Kullanılacak cihaz: {DEVICE.upper()}")
# ==================== GPU DETECTION END ====================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import psycopg2
from sentence_transformers import SentenceTransformer
from llama_cpp import Llama
import sqlparse
from typing import Optional

import numpy as np
from gensim.models import FastText
from rapidfuzz import fuzz


_QDRANT_CLIENT = None
def get_qdrant_client():
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is None:
        _QDRANT_CLIENT = create_qdrant_client()
    return _QDRANT_CLIENT


def _normalize_qdrant_hit(hit):
    """Return (payload_dict, score_float) for a qdrant hit.

    Accepts different return shapes from qdrant-client (object with .payload/.score,
    or tuple/list like (id, score, payload) or similar).
    """
    payload = {}
    score = None

    # tuple/list style: try to find dict and numeric score
    if isinstance(hit, (list, tuple)):
        for el in hit:
            if isinstance(el, dict):
                payload = el
            elif isinstance(el, (float, int)) and score is None:
                score = float(el)
        return payload or {}, score or 0.0

    # object style (PointStruct / QueryResult)
    if hasattr(hit, 'payload'):
        payload = getattr(hit, 'payload') or {}
    elif isinstance(hit, dict) and 'payload' in hit:
        payload = hit.get('payload') or {}

    if hasattr(hit, 'score') and getattr(hit, 'score') is not None:
        try:
            score = float(getattr(hit, 'score'))
        except Exception:
            score = None

    # fallback: try common dict keys
    if score is None and isinstance(hit, dict):
        for key in ('score', 'distance'):
            if key in hit:
                try:
                    score = float(hit[key])
                    break
                except Exception:
                    pass

    return payload or {}, score or 0.0



# LLM - GPU layer support için
llm = None
if not getattr(settings, "SKIP_LLM", False):
    try:
        print("⏳ Loading LLM model...")
        
        # GPU layer ayarı
        n_gpu_layers = 0  # Varsayılan CPU
        if GPU_INFO['available'] and (settings.USE_GPU is None or settings.USE_GPU):
            n_gpu_layers = settings.LLM_N_GPU_LAYERS
            print(f"🎮 LLM için {n_gpu_layers if n_gpu_layers > 0 else 'tüm'} katmanlar GPU'da çalışacak")
        
        llm = Llama(
            model_path=settings.LLM_MODEL_PATH,
            n_ctx=settings.LLM_N_CTX,
            n_threads=settings.LLM_N_THREADS,
            n_batch=settings.LLM_N_BATCH,
            n_gpu_layers=n_gpu_layers,  # GPU desteği
            low_vram=settings.LLM_LOW_VRAM,
            verbose=settings.LLM_VERBOSE,
        )
        print("✅ LLM ready!")
    except Exception as e:
        print(f"⚠️ Could not load LLM: {e}. Continuing with SKIP_LLM=True")
        llm = None
        # If loading failed, set env flag so other code paths skip LLM usage
        os.environ["SKIP_LLM"] = "1"
else:
    print("⚠️ SKIP_LLM enabled; skipping LLM load")

# Embed model - GPU desteğiyle
print(f"⏳ Loading embedding model on {DEVICE.upper()}...")
EMBEDDING_MODEL = SentenceTransformer(settings.EMBEDDING_MODEL_NAME, device=DEVICE)
SEMANTIC_MODEL = SentenceTransformer(settings.SEMANTIC_MODEL_NAME or settings.EMBEDDING_MODEL_NAME, device=DEVICE)
print(f"✅ Embedding models ready on {DEVICE.upper()}!")

# FastText (lexical) - load safely (allow missing model for containerized runs)
LEXICAL_MODEL = None
if not (os.environ.get('SKIP_LEXICAL') == '1'):
    try:
        lexical_path = settings.LEXICAL_FASTTEXT_PATH or "fasttext_lexical_model.model"
        if os.path.exists(lexical_path):
            LEXICAL_MODEL = FastText.load(lexical_path)
            print(f"✅ FastText lexical model loaded from {lexical_path}")
        elif os.path.exists(os.path.join(os.path.dirname(__file__), 'models', os.path.basename(lexical_path))):
            alt_path = os.path.join(os.path.dirname(__file__), 'models', os.path.basename(lexical_path))
            LEXICAL_MODEL = FastText.load(alt_path)
            print(f"✅ FastText lexical model loaded from {alt_path}")
        else:
            print(f"⚠️ FastText lexical model not found at {lexical_path}; lexical features disabled.")
            LEXICAL_MODEL = None
    except Exception as e:
        print(f"⚠️ Error loading FastText lexical model: {e}. Lexical features disabled.")
        LEXICAL_MODEL = None

# Qdrant client (global)
QDRANT_CLIENT = get_qdrant_client()
print("✅ Qdrant client ready!")

# 2) Static prompt - EXPANDED WITH ALL CRITICAL RULES (loaded once to KV cache)
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
   
   � SÜTUN-TABLO EŞLEŞME KURALI (KESİNLİKLE UYULMALI!):
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
�️ KARAR MATRİSİ (Kullanıcı ne istiyorsa SADECE onu yap!)
═══════════════════════════════════════════════════════════════════

"Tüm kayıtları göster/listele/getir" → SELECT * FROM TABLO1;
"SÜTUN1'i getir" → SELECT TABLO1.SÜTUN1 FROM TABLO1;
"SÜTUN1 ve SÜTUN2'yi göster" → SELECT TABLO1.SÜTUN1, TABLO1.SÜTUN2 FROM TABLO1;
"X olan kayıtları bul" → SELECT * FROM TABLO1 WHERE TABLO1.X = 'değer';
"X ve Y tablolarını birleştir" → JOIN kullan (ZİNCİRLEME JOIN YOLLARI'ndan)
"Farklı değerleri göster" → SELECT DISTINCT TABLO1.SÜTUN1 FROM TABLO1;
"Toplam/ortalama hesapla" → SELECT SUM/AVG(TABLO1.SÜTUN1) FROM TABLO1;

═══════════════════════════════════════════════════════════════════
�📝 SQL SORGU ÖRNEKLERİ (Tüm Senaryolar)
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



# ================ STATIC PROMPT PRIMING =================
def ensure_static_session():
    """
    Load the static prompt into the model's KV cache.
    Uses in-memory caching when no session file is available.
    """
    # If LLM explicitly disabled, skip priming
    if os.environ.get('SKIP_LLM') == '1':
        print("⚠️ SKIP_LLM=1: skipping static prompt priming")
        return

    # Ensure we have an LLM instance (lazy load)
    llm_inst = None
    try:
        llm_inst = get_llm_instance()
    except Exception as e:
        print(f"⚠️ Could not get LLM instance for priming: {e}")
        return

    if getattr(llm_inst, "_static_prompt_primed", False):
        return

    print("⏳ Starting static prompt priming...")
    try:
        # Method 1: Minimal token generation priming
        llm_inst(STATIC_PROMPT, max_tokens=1, temperature=0)

        # Method 2: Alternatively tokenize + eval
        # tokens = llm_inst.tokenize(STATIC_PROMPT.encode('utf-8'))
        # if tokens:
        #     llm_inst.eval(tokens)
        #     llm_inst.eval([llm_inst.token_eos()])  # End of sequence

    except Exception as e:
        print(f"⚠️ Priming error: {e}")
        # Continue even if priming fails
        print("⚠️ Continuing without cache...")

    # Mark so priming is not repeated
    setattr(llm_inst, "_static_prompt_primed", True)
    print("✅ Static prompt priming complete (in-memory cache).")

def generate_strict_prompt_dynamic_only(
    natural_query: str,
    schema_text: str,
    schema_pool: dict,
    value_context: dict,
    extended_context: str = ""
) -> str:

    # Minimal reinforcement - main rules now in static prompt (KV cached)
    reinforce_rules = """
🚨 3 KRİTİK KURAL:
1️⃣ Sütun belirtilmedi mi? → SELECT *
2️⃣ Filtre/koşul yok mu? → WHERE KULLANMA!
3️⃣ İstenen sütunlar tek tabloda mı? → JOIN KULLANMA!

⚠️ JOIN gerekliyse: "ZİNCİRLEME JOIN YOLLARI"ndaki SQL: satırını AYNEN kopyala
"""

    # Make value hints more controlled
    value_hints = ""
    if value_context and _needs_explicit_filtering(natural_query):
        value_hints = "\n=== MEVCUT VERİ DEĞERLERİ (SADCE FİLTRE GEREKİYORSA KULLAN) ===\n"
        value_hints += "⚠️ DİKKAT: Bu değerleri SADECE kullanıcı belirli bir değer filtrelemesi isterse kullan!\n\n"
        
        for key, values in value_context.items():
            if values:
                # Show only the first 2 values to avoid overly long output
                value_hints += f"• {key}: {', '.join(repr(v) for v in values[:2])}"
                if len(values) > 2:
                    value_hints += f" ... (toplam {len(values)} değer)"
                value_hints += "\n"
        value_hints += "\n"


    # Compact dynamic prompt - heavy rules now in static prompt (KV cached)
    dynamic_prompt = f"""
{extended_context}
{schema_text}

{reinforce_rules}

**KULLANICI SORUSU:** "{natural_query}"

🚨 ÇOK ÖNEMLİ: Sadece SQL yaz! Açıklama, yorum veya başka metin yazma!

**SQL SORGUSU:**
```sql
"""

    return dynamic_prompt


def _needs_explicit_filtering(natural_query: str) -> bool:
    """Return True if the user's query contains explicit filtering indicators."""
    query_lower = natural_query.lower()
    
    # Explicit filtering indicators
    filter_indicators = [
        'olan', 'filtrele', 'bul', 'göster', 'getir', 'listele', 
        'hangi', 'nerede', 'kaç', 'kim', 'ne zaman',
        'aktif', 'pasif', 'büyük', 'küçük', 'eşit', 'arası', 'içinde','musun','misin', 'mu','mü','var mı','yok mu','var'
    ]
    
    # Explicit value indicators (numbers, proper names)
    has_explicit_value = any([
        any(word.isdigit() for word in natural_query.split()),
        any(indicator in query_lower for indicator in ['"', "'", "=", ">", "<"])
    ])
    
    return (any(indicator in query_lower for indicator in filter_indicators) 
            or has_explicit_value)




# ================ DB CONNECTION =================
def get_connection():
    kwargs = get_db_conn_kwargs()
    return psycopg2.connect(**kwargs)

# ================ FK GRAPH LOADER =================
_FK_GRAPH_CACHE = None

@lru_cache(maxsize=1)
def load_fk_graph(json_path: str = "fk_graph.json") -> Dict:
    """
    Load the FK (foreign-key) graph, preferring a local JSON at `json_path`.
    If the JSON file does not exist, attempt to read the latest entry from
    the Postgres `fk_graph_metadata` table. Raise an error only if neither
    source provides the graph. The result is cached for subsequent calls.
    """
    global _FK_GRAPH_CACHE
    if _FK_GRAPH_CACHE is not None:
        return _FK_GRAPH_CACHE

    print("\n" + "="*80)
    print("🔗 FK GRAPH YÜKLENİYOR")
    print("="*80)

    # 1) Local JSON preference
    try:
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                _FK_GRAPH_CACHE = json.load(f)
            print(f"✅ FK graph yüklendi ({json_path}): {len(_FK_GRAPH_CACHE.get('edges',[]))} edge, {len(_FK_GRAPH_CACHE.get('adjacency',{}))} tablo")
            return _FK_GRAPH_CACHE
    except Exception as e:
        print("⚠️ Lokal fk_graph.json okunurken hata:", e)

    # 2) Fallback: read from Postgres (legacy behavior)
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT graph_data FROM fk_graph_metadata ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()

        if not row:
            raise ValueError("❌ Postgres'te fk_graph_metadata bulunamadı ve lokal fk_graph.json yok. Önce build işlemini çalıştırın.")

        graph_data = row[0]
        _FK_GRAPH_CACHE = json.loads(graph_data) if isinstance(graph_data, str) else graph_data

        print(f"✅ FK graph yüklendi (Postgres): {len(_FK_GRAPH_CACHE.get('edges',[]))} edge, {len(_FK_GRAPH_CACHE.get('adjacency',{}))} tablo")
        return _FK_GRAPH_CACHE

    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


# ================ CONFIG =================
MAX_PATH_HOPS = settings.MAX_PATH_HOPS
MAX_INITIAL_RESULTS = settings.MAX_INITIAL_RESULTS

TOP_COLUMNS_IN_CONTEXT = 7


# ================ UTILITIES =================
def fetch_all_columns_for_table(conn, table_name, schema_name=None):
    """
    Return real table columns from information_schema.
    Returns: [(column_name, data_type, is_nullable, column_default), ...]
    """
    cur = conn.cursor()
    try:
        if schema_name:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = %s
                ORDER BY ordinal_position
            """, (table_name, schema_name))
        else:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
        rows = cur.fetchall()
        # normalize to (name, type, desc)
        return [(r[0], r[1], f"nullable={r[2]}, default={r[3]}") for r in rows]
    finally:
        cur.close()

def semantic_search(query: str, top_k: int = 10):
    """Semantic similarity search against Qdrant."""
    query_vector = SEMANTIC_MODEL.encode([query])[0].tolist()
    
    results = QDRANT_CLIENT.query_points(
        collection_name=settings.QDRANT_SCHEMA_COLLECTION,
        query=query_vector,
        limit=top_k
    )

    # qdrant-client may return a QueryResponse object or a list; normalize to iterable
    if hasattr(results, 'points') and results.points is not None:
        hits = results.points
    else:
        hits = results
    
    formatted_results = []
    for i, hit in enumerate(hits):
        payload, score = _normalize_qdrant_hit(hit)
        formatted_results.append({
            "table": payload.get("table_name", ""),
            "column": payload.get("column_name", ""),
            "similarity": float(score),
            "type": "semantic",
            "rank": i + 1
        })
    
    return formatted_results

def lexical_search(query: str, top_k: int = 10):
    try:
        print(f"🔍 [LEXICAL] Query: {query}")
        
        # Load TF-IDF vectorizer
        try:
            import joblib
            tfidf_vectorizer = joblib.load(settings.TFIDF_VECTORIZER_PATH)

            print(f"✅ TF-IDF vectorizer loaded. Feature count: {len(tfidf_vectorizer.get_feature_names_out())}")
        except Exception as e:
            print(f"❌ TF-IDF vectorizer failed to load: {e}")
            return []

        if not query:
            return []

        # Preprocess query
        q_clean = query.replace('_', ' ').lower()
        print(f"🔍 [LEXICAL] Cleaned query: {q_clean}")

        # Build TF-IDF vector
        query_vec = tfidf_vectorizer.transform([q_clean])
        query_vec_dense = query_vec.toarray().ravel()
        
        print(f"🔍 [LEXICAL] Vector dimension: {query_vec_dense.shape[0]}")
        
        # Normalize
        norm = np.linalg.norm(query_vec_dense)
        if norm > 0:
            query_vec_dense = query_vec_dense / norm

        # Search in Qdrant
        results = QDRANT_CLIENT.query_points(
            collection_name=settings.QDRANT_LEXICAL_COLLECTION,
            query=query_vec_dense.astype("float32").tolist(),
            limit=top_k
        )

        if hasattr(results, 'points') and results.points is not None:
            hits = results.points
        else:
            hits = results

        formatted = []
        for i, hit in enumerate(hits):
            p, score = _normalize_qdrant_hit(hit)
            if not p.get("table_name") or not p.get("column_name"):
                continue
            formatted.append({
                "table": p["table_name"],
                "column": p["column_name"],
                "similarity": float(score),
                "type": "lexical",
                "rank": i + 1,
                "debug_text": p.get("combined_text", ""),
                "embedding_type": p.get("embedding_type", "tfidf_ngram")
            })
        
        print(f"🔍 [LEXICAL] Found {len(formatted)} results")
        
        # DEBUG: Show top 3 results
        for i, result in enumerate(formatted[:3]):
            print(f"   {i+1}. {result['table']}.{result['column']} (score: {result['similarity']:.4f})")
        
        return formatted

    except Exception as e:
        print(f"❌ Lexical search error: {e}")
        import traceback
        traceback.print_exc()
        return []

def keyword_search(natural_query: str, top_k: int = 10) -> List[Dict]:
    """Search keyword matches in the `schema_keywords` collection in Qdrant (vector-based)."""
    print(f"🔑 [KEYWORD] Query: '{natural_query}'")
    
    try:
        client = get_qdrant_client()
        
        # Encode query with semantic model
        query_vector = SEMANTIC_MODEL.encode([natural_query])[0].tolist()
        
        # Search the `schema_keywords` collection in Qdrant
        if hasattr(client, 'query_points'):
            results = client.query_points(collection_name=settings.QDRANT_KEYWORDS_COLLECTION, query=query_vector, limit=top_k)
        elif hasattr(client, 'search'):
            results = client.search(collection_name=settings.QDRANT_KEYWORDS_COLLECTION, query_vector=query_vector, limit=top_k)
        else:
            raise RuntimeError('Qdrant client does not support search/query_points')
        
        # Extract points from QueryResponse
        if hasattr(results, 'points'):
            hits = results.points
        else:
            hits = results
        
        formatted_results = []
        for i, hit in enumerate(hits):
            payload, score = _normalize_qdrant_hit(hit)
            formatted_results.append({
                "table": payload.get("table_name", ""),
                "column": payload.get("column_name", ""),
                "similarity": float(score),
                "keyword": payload.get("keyword", ""),
                "keyword_type": payload.get("keyword_type", ""),
                "type": "keyword",
                "rank": i + 1
            })
        
        print(f"🔑 [KEYWORD] Found {len(formatted_results)} matches (vector-based from schema_keywords)")
        
        # DEBUG: Show first 5 results
        for i, result in enumerate(formatted_results[:5]):
            column_display = result['column'] if result['column'] else "table"
            print(f"   {i+1}. {result['table']}.{column_display} -> '{result['keyword']}' (score: {result['similarity']:.4f}, type: {result['keyword_type']})")
        
        return formatted_results
        
    except Exception as e:
        print(f"❌ Keyword search failed: {e}")
        return []
    
def get_top_tables_from_search_results(search_results: List[Dict], search_type: str, top_k: int = 3) -> List[Tuple[str, float]]:
    """Extract the top-scoring tables from search results."""
    table_scores = {}

    for result in search_results:
        table = result.get("table", "")
        similarity = result.get("similarity", 0.0)

        if not table:
            continue

        # Keep the highest score for each table
        if table not in table_scores or similarity > table_scores[table]:
            table_scores[table] = similarity
        
        # Sort by score and take the top_k tables
        sorted_tables = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        print(f"🏆 [TOP_TABLES_{search_type.upper()}] Top {len(sorted_tables)} tables:")
        for i, (table, score) in enumerate(sorted_tables, 1):
            print(f"   {i}. {table} (score: {score:.4f})")
        
        return sorted_tables

def enhanced_semantic_lexical_search(natural_query: str):
        
        """
        NEW: No combined hybrid scoring here — return the top 3 tables
        separately from semantic and lexical searches.
        """
        print(f"\n🎯 ENHANCED SEMANTIC + LEXICAL SEARCH | Query: '{natural_query}'")
        
        # 1. Run semantic and lexical searches
        semantic_results = semantic_search(natural_query, top_k=20)
        lexical_results = lexical_search(natural_query, top_k=20)
        
        print(f"🔍 [ENHANCED_SEARCH] Raw semantic results: {len(semantic_results)}")
        print(f"🔍 [ENHANCED_SEARCH] Raw lexical results: {len(lexical_results)}")
        
        # 2. Her iki aramadan da en iyi 3 tabloyu al
        top_semantic_tables = get_top_tables_from_search_results(semantic_results, "semantic", 3)
        top_lexical_tables = get_top_tables_from_search_results(lexical_results, "lexical", 3)
        
        # 3. Combine all tables (unique)
        all_tables_set = set()
        
        for table, score in top_semantic_tables:
            all_tables_set.add(table)
        
        for table, score in top_lexical_tables:
            all_tables_set.add(table)
        
        all_tables = list(all_tables_set)
        print(f"🔍 [ENHANCED_SEARCH] Combined unique tables: {len(all_tables)}")
        
        # 4. Print table selection
        print(f"\n🎯 FINAL TABLE SELECTION:")
        print(f"   Semantic tables: {[table for table, score in top_semantic_tables]}")
        print(f"   Lexical tables: {[table for table, score in top_lexical_tables]}")
        print(f"   All tables: {all_tables}")
        
        return {
            "selected_tables": all_tables,
            "top_semantic_tables": top_semantic_tables,
            "top_lexical_tables": top_lexical_tables,
            "all_semantic": semantic_results,
            "all_lexical": lexical_results,
            "schema": [],  # For backward compatibility with the old format
            "keywords": [],
            "values": []
        }

def hybrid_search_with_separate_results(natural_query: str, top_k: int = 15, similarity_threshold: float = None):
        """
        FIXED: Semantic search added and all search types are now active.
        """
        # Use config threshold if not specified
        if similarity_threshold is None:
            similarity_threshold = min(settings.SEMANTIC_THRESHOLD, settings.LEXICAL_THRESHOLD)
        
        print(f"\n🎯 SEPARATE RESULTS SEARCH | Query: '{natural_query}' | Threshold: {similarity_threshold}")
        
        # QUERY ENRICHMENT: Add domain-specific keywords to improve table discovery
        enriched_query = natural_query
        query_lower = natural_query.lower()
        
        # 🔥 EXACT TABLE NAME MATCH: Boost score if query contains exact table name
        exact_table_boost = []
        query_words = query_lower.replace("_", " ").split()
        
        # Check if query contains table-like patterns (a_il, e_sayac, m_load_profile, etc.)
        for word in query_words:
            if "_" in word or (len(word) > 2 and word.startswith(('a_', 'e_', 'm_', 'l_', 'c_'))):
                exact_table_boost.append(word)
                print(f"🎯 [EXACT_MATCH_BOOST] Detected table name: '{word}'")
        
        # Map common phrases to specific table/column names
        if "tüketim verisi" in query_lower or "tedaş" in query_lower or "tedas" in query_lower:
            enriched_query += " l_integs_tedas_tesisat tedas_update_date sayac_seri_no"
            print(f"💡 [QUERY_ENRICHMENT] TEDAŞ/Tüketim → l_integs_tedas_tesisat eklendi")
        
        if "sayaç" in query_lower or "seri" in query_lower:
            enriched_query += " e_sayac seri_no"
            print(f"💡 [QUERY_ENRICHMENT] Sayaç → e_sayac eklendi")
        
        print(f"🔍 [ENRICHED_QUERY] Original: '{natural_query}'")
        print(f"🔍 [ENRICHED_QUERY] Enhanced: '{enriched_query}'")
        
        # 1. Run all search types with enriched query
        semantic_results = semantic_search(enriched_query, top_k=20)
        lexical_results = lexical_search(enriched_query, top_k=20)
        keyword_results = keyword_search(natural_query, top_k=20)  # Use original for keywords
        data_values_results = data_values_search(natural_query, top_k=20)  # Use original for values

        print(f"🔍 [SEPARATE_SEARCH] Raw semantic results: {len(semantic_results)}")  # this line was added
        print(f"🔍 [SEPARATE_SEARCH] Raw lexical results: {len(lexical_results)}")
        print(f"🔑 [SEPARATE_SEARCH] Raw keyword results: {len(keyword_results)}")
        print(f"📊 [SEPARATE_SEARCH] Raw data values results: {len(data_values_results)}")

        # DEBUG: Show semantic results
        print(f"🧠 [SEMANTIC_DEBUG] Top 5 semantic results:")
        for i, result in enumerate(semantic_results[:5], 1):
            print(f"   {i}. {result['table']}.{result['column']} (score: {result.get('similarity', 0):.3f})")

        # 2. Collect all tables for the interactive table
        all_table_scores = {}
        
        # Collect tables from all results - without applying thresholds
        for result in semantic_results + lexical_results + keyword_results + data_values_results:  # semantic_results eklendi
            table = result.get("table", "")
            similarity = result.get("similarity", 0)
            if table:
                # 🔥 BOOST: If table name exactly matches query, give max score
                table_lower = table.lower().replace("helios.", "")
                if exact_table_boost and any(boost in table_lower for boost in exact_table_boost):
                    similarity = max(similarity, 0.95)  # Boost to very high score
                    print(f"🚀 [EXACT_MATCH_BOOST] Table '{table}' boosted to {similarity:.3f}")
                
                if table not in all_table_scores or similarity > all_table_scores[table]:
                    all_table_scores[table] = similarity
        
        # Sort the most similar tables (for interactive table)
        similar_tables = sorted(all_table_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Filter tables above threshold (informational only)
        above_threshold_tables = [(table, score) for table, score in similar_tables if score >= similarity_threshold]
        
        print(f"🏆 [INTERACTIVE_TABLES] Tüm tablolar: {len(similar_tables)}, Eşik üstü: {len(above_threshold_tables)} (threshold: {similarity_threshold})")
        
        # Show top 6 tables (regardless of threshold)
        top_similar_tables = similar_tables[:6]
        for i, (table, score) in enumerate(top_similar_tables, 1):
            status = "✓" if score >= similarity_threshold else "⚠"
            print(f"   {i}. {table} (score: {score:.3f}) {status}")

        # 3. Select a fixed number of results from each group
        # Semantic: top 3 above threshold
        semantic_threshold = settings.SEMANTIC_THRESHOLD
        filtered_semantic = [r for r in semantic_results if r.get("similarity", 0) >= semantic_threshold]
        top_semantic = sorted(filtered_semantic, key=lambda x: x.get("similarity", 0), reverse=True)[:3]
        
        # Lexical: top 3 above threshold
        lexical_threshold = settings.LEXICAL_THRESHOLD
        filtered_lexical = [r for r in lexical_results if r.get("similarity", 0) >= lexical_threshold]
        top_lexical = sorted(filtered_lexical, key=lambda x: x.get("similarity", 0), reverse=True)[:3]
        
        # Keyword: top 3 above threshold
        keyword_threshold = settings.KEYWORD_THRESHOLD
        filtered_keywords = [r for r in keyword_results if r.get("similarity", 0) >= keyword_threshold]
        top_keyword = sorted(filtered_keywords, key=lambda x: x.get("similarity", 0), reverse=True)[:3]
        
        # Data values: top 3 above threshold
        data_values_threshold = settings.DATA_VALUES_THRESHOLD
        filtered_data_values = [r for r in data_values_results if r.get("similarity", 0) >= data_values_threshold]
        top_data_values = sorted(filtered_data_values, key=lambda x: x.get("similarity", 0), reverse=True)[:3]

        print(f"🔍 [SEPARATE_SEARCH] Top 3 semantic (threshold {semantic_threshold}): {len(top_semantic)}")
        print(f"🔍 [SEPARATE_SEARCH] Top 3 lexical (threshold {lexical_threshold}): {len(top_lexical)}")
        print(f"🔑 [SEPARATE_SEARCH] Top 3 keyword (threshold {keyword_threshold}): {len(top_keyword)}")
        print(f"📊 [SEPARATE_SEARCH] Top 3 data values (threshold {data_values_threshold}): {len(top_data_values)}")

        # 4. Merge all results (unique table-column pairs)
        combined_results = []
        seen_keys = set()
        
        # Priority order: data values -> keyword -> semantic -> lexical
        all_results_in_priority = top_data_values + top_keyword + top_semantic + top_lexical  # top_semantic eklendi
        
        for result in all_results_in_priority:
            table = result.get("table", "")
            column = result.get("column", "")
            if not table or not column:
                continue
                
            key = (table, column)
            if key not in seen_keys:
                seen_keys.add(key)
                combined_results.append(result)

        print(f"🔍 [SEPARATE_SEARCH] Combined unique results: {len(combined_results)}")

        # 5. DEBUG: Show selected results from each group
        print(f"\n🎯 SELECTED RESULTS FROM EACH GROUP:")
        
        print(f"🧠 SEMANTIC (Top 3):")  # this line was added
        for i, r in enumerate(top_semantic, 1):
            print(f"   {i}. {r['table']}.{r['column']} (score: {r.get('similarity', 0):.3f})")
        
        print(f"🔤 LEXICAL (Top 3):")
        for i, r in enumerate(top_lexical, 1):
            print(f"   {i}. {r['table']}.{r['column']} (score: {r.get('similarity', 0):.3f})")
        
        print(f"🔑 KEYWORD (Top 3, threshold {keyword_threshold}):")
        for i, r in enumerate(top_keyword, 1):
            keyword_info = f" -> '{r.get('keyword', '')}'" if r.get('keyword') else ""
            print(f"   {i}. {r['table']}.{r['column']} (score: {r.get('similarity', 0):.3f}{keyword_info})")
        
        print(f"📊 DATA VALUES (Top 3, threshold {data_values_threshold}):")
        for i, r in enumerate(top_data_values, 1):
            value_info = f" -> '{r.get('value_text', '')}'" if r.get('value_text') else ""
            print(f"   {i}. {r['table']}.{r['column']} (score: {r.get('similarity', 0):.3f}{value_info})")

        # 6. Derive top results at the table level
        top_semantic_tables = []  # added
        for r in top_semantic:
            table = r.get("table")
            if table:
                top_semantic_tables.append((table, r.get("similarity", 0)))

        top_lexical_tables = []
        for r in top_lexical:
            table = r.get("table")
            if table:
                top_lexical_tables.append((table, r.get("similarity", 0)))

        top_keyword_tables = []
        for r in top_keyword:
            table = r.get("table")
            if table:
                top_keyword_tables.append((table, r.get("similarity", 0)))

        top_data_values_tables = []
        for r in top_data_values:
            table = r.get("table")
            if table:
                top_data_values_tables.append((table, r.get("similarity", 0)))

        return {
            "top_results": combined_results[:top_k],
            "all_semantic": semantic_results,  # this line was added
            "all_lexical": lexical_results,
            "all_keywords": keyword_results,
            "all_data_values": data_values_results,
            "schema": combined_results,
            "keywords": keyword_results,
            "values": data_values_results,
            "top_semantic_tables": top_semantic_tables,  # this line was added
            "top_lexical_tables": top_lexical_tables,
            "top_keyword_tables": top_keyword_tables,
            "top_data_values_tables": top_data_values_tables,
            "selected_tables": list(set([table for table, score in top_semantic_tables + top_lexical_tables + top_keyword_tables + top_data_values_tables])),
            "similar_tables": top_similar_tables,
            "similarity_threshold": similarity_threshold,
            "above_threshold_count": len(above_threshold_tables)
        }


def score_columns_by_relevance_separate(semantic_results: dict, value_context: dict, top_n: int = 10) -> list:
    """NEW: Score columns coming from separate groups - UPDATED implementation."""
    print(f"\n🎯 [COLUMN_SCORING_SEPARATE] Selecting columns from separate groups")
    
    # Collect results from each group
    top_semantic_tables = semantic_results.get("top_semantic_tables", [])
    top_lexical_tables = semantic_results.get("top_lexical_tables", [])
    top_keyword_tables = semantic_results.get("top_keyword_tables", [])
    top_data_values_tables = semantic_results.get("top_data_values_tables", [])
    
    # Selected tables
    selected_tables = set(semantic_results.get("selected_tables", []))
    print(f"🔍 [COLUMN_SCORING] Selected tables: {selected_tables}")
    
    # Gather columns from each group
    all_columns = []
    
    # Semantic columns - process all semantic results
    for result in semantic_results.get("all_semantic", []):
        table = result.get("table", "")
        column = result.get("column", "")
        similarity = result.get("similarity", 0)
        
        if table in selected_tables and table and column:
            all_columns.append({
                "table": table,
                "column": column,
                "similarity": similarity,
                "type": "semantic",
                "source_priority": 3
            })
    
    # Lexical columns - process all lexical results
    for result in semantic_results.get("all_lexical", []):
        table = result.get("table", "")
        column = result.get("column", "")
        similarity = result.get("similarity", 0)
        
        if table in selected_tables and table and column:
            all_columns.append({
                "table": table,
                "column": column,
                "similarity": similarity,
                "type": "lexical",
                "source_priority": 2
            })
    
    # Keyword columns - process all keyword results
    for result in semantic_results.get("all_keywords", []):
        table = result.get("table", "")
        column = result.get("column", "")
        similarity = result.get("similarity", 0)
        
        if table in selected_tables and table and column:
            all_columns.append({
                "table": table,
                "column": column,
                "similarity": similarity,
                "type": "keyword",
                "source_priority": 4,
                "keyword": result.get("keyword", "")
            })
    
    # Data values columns - process all data values results
    for result in semantic_results.get("all_data_values", []):
        table = result.get("table", "")
        column = result.get("column", "")
        similarity = result.get("similarity", 0)
        
        if table in selected_tables and table and column:
            all_columns.append({
                "table": table,
                "column": column,
                "similarity": similarity,
                "type": "data_values",
                "source_priority": 5,
                "value_text": result.get("value_text", "")
            })
    
    print(f"📊 [COLUMN_SCORING] Total column candidates: {len(all_columns)}")
    
    # Find unique columns (keep the one with highest priority)
    unique_columns = {}
    for col_info in all_columns:
        key = (col_info["table"], col_info["column"])
        current_priority = col_info["source_priority"]
        current_score = col_info["similarity"]
        
        if key not in unique_columns:
            unique_columns[key] = col_info
        else:
            # For the same column, choose the entry with the higher priority
            existing_priority = unique_columns[key]["source_priority"]
            if current_priority > existing_priority:
                unique_columns[key] = col_info
            elif current_priority == existing_priority and current_score > unique_columns[key]["similarity"]:
                # If same priority, pick the one with higher similarity score
                unique_columns[key] = col_info
    
    print(f"📊 [COLUMN_SCORING] Unique columns: {len(unique_columns)}")
    
    # Sort by priority and score
    final_columns = sorted(
        unique_columns.values(), 
        key=lambda x: (x["source_priority"], x["similarity"]), 
        reverse=True
    )[:top_n]
    
    # Normalize format
    formatted_columns = []
    for col_info in final_columns:
        formatted_columns.append((
            col_info["table"],
            col_info["column"], 
            col_info["similarity"],
            col_info["type"],
            {
                "keyword": col_info.get("keyword"),
                "value_text": col_info.get("value_text")
            } if col_info.get("keyword") or col_info.get("value_text") else None
        ))
    
    print(f"\n📊 FINAL TOP COLUMNS (SEPARATE GROUPS): {len(formatted_columns)} columns")
    for i, (t, c, s, src, extra) in enumerate(formatted_columns, 1):
        icon = "🧠" if src == "semantic" else "🔤" if src == "lexical" else "🔑" if src == "keyword" else "📊"
        extra_info = ""
        if extra:
            if extra.get("keyword"):
                extra_info = f" [keyword: '{extra['keyword']}']"
            elif extra.get("value_text"):
                extra_info = f" [value: '{extra['value_text']}']"
        print(f"  {i:2d}. {t}.{c} (score={s:.3f}, source={icon} {src}{extra_info})")
    
    return formatted_columns
    

def data_values_search(natural_query: str, top_k: int = 10) -> List[Dict]:
    """
    Data values search - from the data_samples collection in Qdrant.
    """
    print(f"📊 [DATA_VALUES] Query: '{natural_query}'")
    
    try:
        client = get_qdrant_client()
        
        # Query'yi semantic model ile encode et
        query_vector = SEMANTIC_MODEL.encode([natural_query])[0].tolist()
        
        # Search the data_samples collection in Qdrant
        if hasattr(client, 'query_points'):
            results = client.query_points(collection_name=settings.QDRANT_DATA_SAMPLES_COLLECTION, query=query_vector, limit=top_k)
        elif hasattr(client, 'search'):
            results = client.search(collection_name=settings.QDRANT_DATA_SAMPLES_COLLECTION, query_vector=query_vector, limit=top_k)
        else:
            raise RuntimeError('Qdrant client does not support search/query_points')
        
        # Extract points from QueryResponse
        if hasattr(results, 'points'):
            hits = results.points
        else:
            hits = results
        
        formatted_results = []
        for i, hit in enumerate(hits):
            payload, score = _normalize_qdrant_hit(hit)
            formatted_results.append({
                "table": payload.get("table_name", ""),
                "column": payload.get("column_name", ""),
                "similarity": float(score),
                "value_text": payload.get("value_text", ""),
                "data_type": payload.get("data_type", ""),
                "type": "data_values",
                "rank": i + 1
            })
        
        print(f"📊 [DATA_VALUES] Found {len(formatted_results)} value matches")
        
        # DEBUG: Show first 5 results
        for i, result in enumerate(formatted_results[:5]):
            value_preview = result['value_text'][:50] + "..." if len(result['value_text']) > 50 else result['value_text']
            print(f"   {i+1}. {result['table']}.{result['column']} -> '{value_preview}' (score: {result['similarity']:.4f})")
        
        return formatted_results
        
    except Exception as e:
        print(f"❌ Data values search failed: {e}")
        return []
    

def build_compact_schema_pool(
    semantic_results: Dict[str, List[Dict]],
    selected_tables: Set[str],
    fk_graph: Dict,
    top_columns: list = None # type: ignore
) -> Tuple[Dict, Dict, Dict]:
    from collections import defaultdict

    print(f"\n{'='*80}")
    print(f"🏗️  NEW: COMPACT SCHEMA POOL BUILDER (PK/FK PRIORITIZED)")
    print(f"{'='*80}")

    # === SCHEMA NORMALIZATION ===
    DEFAULT_SCHEMA = settings.DB_SCHEMA

    def normalize_table_name(name: str) -> str:
        if not name:
            return ""
        if "." not in name:
            return f"{DEFAULT_SCHEMA}.{name}"
        return name

    def split_table_name(normalized_table: str) -> Tuple[str, str]:
        if '.' in normalized_table:
            parts = normalized_table.split('.', 1)
            return parts[0], parts[1]
        return DEFAULT_SCHEMA, normalized_table

    # Normalize selected table names
    selected_tables = {normalize_table_name(t) for t in selected_tables if t}

    # Find FK connecting paths
    paths = find_minimal_connecting_paths(fk_graph, selected_tables, MAX_PATH_HOPS)
    intermediate_tables = extract_all_tables_from_paths(paths)
    all_tables = set(selected_tables) | set(intermediate_tables)

    schema_pool = {}
    value_context = {}

    # === DETECT PK/FK COLUMNS ===
    print(f"🔍 Detecting PK/FK columns...")
    pk_columns = set()
    fk_columns = set()
    
    # 1. Get actual PRIMARY KEY constraints from database
    conn = get_connection()
    cursor = conn.cursor()
    
    for table in all_tables:
        if not table:
            continue
        schema_name, table_name = split_table_name(table)
        
        # Get PK columns from database
        cursor.execute("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = (%s || '.' || %s)::regclass
              AND i.indisprimary
        """, (schema_name, table_name))
        
        pk_cols_from_db = [col_name for (col_name,) in cursor.fetchall()]
        
        # If no PK found in DB, use 'id' column as PK (common convention)
        if not pk_cols_from_db:
            # Check if 'id' column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s AND column_name = 'id'
            """, (schema_name, table_name))
            
            if cursor.fetchone():
                pk_columns.add((table, 'id'))
                print(f"  ⚠️ No PK constraint in DB for {table}, using 'id' as PK")
        else:
            for col_name in pk_cols_from_db:
                pk_columns.add((table, col_name))
    
    cursor.close()
    conn.close()
    
    # 2. Extract FK columns from the FK graph edges
    edges = fk_graph.get('edges', []) if isinstance(fk_graph, dict) else []
    for edge in edges:
        from_table = normalize_table_name(edge.get('from', ''))
        fk_col = edge.get('fk_column', '')
        
        # If FK table is in our selected tables, mark the column as FK
        if from_table in all_tables and fk_col:
            fk_columns.add((from_table, fk_col))

    print(f"✅ Detected {len(pk_columns)} PK columns, {len(fk_columns)} FK columns")

    # === AGGREGATE SIMILARITY SCORES ===
    print(f"🔍 Aggregating similarity scores...")
    column_scores = defaultdict(float)
    
    for result in (semantic_results.get("all_semantic", []) + 
                   semantic_results.get("all_lexical", []) + 
                   semantic_results.get("all_keywords", []) + 
                   semantic_results.get("all_data_values", [])):
        table = normalize_table_name(result.get("table", ""))
        column = result.get("column", "")
        similarity = result.get("similarity", 0)
        
        if table in all_tables and column:
            key = (table, column)
            if similarity > column_scores[key]:
                column_scores[key] = similarity

    # === NEW: Fetch table columns and sort with PK/FK priority ===
    print(f"🔍 Fetching table columns and sorting with PK/FK priority...")
    # Reuse connection from PK detection
    conn = get_connection()
    
    for table in all_tables:
        if not table:
            continue
            
        schema, table_name = split_table_name(table)
        all_db_columns = fetch_all_columns_for_table(conn, table_name, schema)
        
        # Add table to schema_pool
        if table not in schema_pool:
            schema_pool[table] = {'columns': [], 'column_details': {}}
        
        # Group columns into PK, FK, high/medium/low similarity
        pk_columns_list = []
        fk_columns_list = []
        high_similarity_columns = []  # High similarity > 0.4
        medium_similarity_columns = []  # Medium similarity 0.2-0.4
        low_similarity_columns = []  # Low similarity < 0.2
        
        for col_name, data_type, description in all_db_columns:
            score = column_scores.get((table, col_name), 0)
            is_pk = (table, col_name) in pk_columns
            is_fk = (table, col_name) in fk_columns
            
            # Normalize data type strings
            if data_type.startswith('character varying'):
                data_type = data_type.replace('character varying', 'VARCHAR')
            elif data_type.startswith('timestamp without time zone'):
                data_type = data_type.replace('timestamp without time zone', 'TIMESTAMP')
            elif data_type == 'numeric':
                data_type = "NUMERIC"
            
            col_info = {
                'name': col_name,
                'data_type': data_type,
                'score': score,
                'is_pk': is_pk,
                'is_fk': is_fk,
                'fk_ref': None  # Will be populated for FK columns
            }
            
            # If FK, find the referenced table from fk_graph
            if is_fk and table in fk_graph:
                for edge in fk_graph[table]:
                    if edge['from_column'] == col_name:
                        col_info['fk_ref'] = {
                            'table': edge['to_table'],
                            'column': edge['to_column']
                        }
                        break
            
            if is_pk:
                pk_columns_list.append(col_info)
            elif is_fk:
                fk_columns_list.append(col_info)
            elif score > 0.4:
                high_similarity_columns.append(col_info)
            elif score > 0.2:
                medium_similarity_columns.append(col_info)
            else:
                low_similarity_columns.append(col_info)
        
        # Sort each group internally
        # PK columns: sort by name
        pk_columns_list.sort(key=lambda x: x['name'])
        # FK columns: sort by name
        fk_columns_list.sort(key=lambda x: x['name'])
        # Similarity columns: sort by score (DESCENDING - highest first)
        high_similarity_columns.sort(key=lambda x: x['score'], reverse=True)
        medium_similarity_columns.sort(key=lambda x: x['score'], reverse=True)
        low_similarity_columns.sort(key=lambda x: x['score'], reverse=True)
        
        # NEW LOGIC: PK + FK + TOP 7 SIMILARITY
        # 1. Always include ALL PK and FK columns
        priority_columns = pk_columns_list + fk_columns_list
        
        # 2. Merge all similarity columns and sort by score
        all_similarity_columns = (high_similarity_columns + 
                                 medium_similarity_columns + 
                                 low_similarity_columns)
        all_similarity_columns.sort(key=lambda x: x['score'], reverse=True)
        
        # 3. Take top 7 similarity columns (exclude already added PK/FK)
        pk_fk_names = {c['name'] for c in priority_columns}
        additional_columns = []
        for col in all_similarity_columns:
            if col['name'] not in pk_fk_names:
                additional_columns.append(col)
                if len(additional_columns) >= 7:
                    break
        
        # 4. Final columns: PK + FK + top 7 similarity
        final_columns = priority_columns + additional_columns
        
        # Add to schema_pool
        for col_info in final_columns:
            col_name = col_info['name']
            if col_name not in schema_pool[table]['columns']:
                schema_pool[table]['columns'].append(col_name)
                schema_pool[table]['column_details'][col_name] = {
                    'data_type': col_info['data_type'],
                    'similarity_score': col_info['score'],
                    'is_pk': col_info['is_pk'],
                    'is_fk': col_info['is_fk'],
                    'fk_ref': col_info.get('fk_ref')  # FK path info
                }
        
        pk_count = len(pk_columns_list)
        fk_count = len(fk_columns_list)
        similar_count = len(additional_columns)
        print(f"📊 Table {table}: {len(final_columns)} columns (PK:{pk_count}, FK:{fk_count}, top_similar:{similar_count})")
    
    conn.close()

    # Add value context
    for v in semantic_results.get("values", []) or []:
        t = normalize_table_name(v.get('table', ''))
        c = v.get('column', '')
        if t and c and f"{t}.{c}" not in value_context:
            value_text = v.get('value_text')
            if value_text:
                value_context.setdefault(f"{t}.{c}", []).append(value_text)

    print(f"\n✅ NEW Schema pool: {len(schema_pool)} tables, PK/FK prioritized")
    
    # DEBUG: Print sample of schema pool contents
    print(f"🔍 DEBUG Schema pool sample:")
    for table, info in list(schema_pool.items())[:2]:
        if not table:
            continue
        print(f"  {table}:")
        for i, col in enumerate(info.get('columns', [])[:6]):
            details = info.get('column_details', {}).get(col, {})
            data_type = details.get('data_type', 'N/A')
            is_pk = details.get('is_pk', False)
            is_fk = details.get('is_fk', False)
            label = "PK" if is_pk else "FK" if is_fk else ""
            print(f"    {i+1}. {col} {data_type} {label}")

    return schema_pool, paths, value_context


def format_compact_schema_prompt_with_keywords(
    schema_pool: Dict, 
    paths: Dict,
    fk_graph: Dict,
    top_columns: List,
    natural_query: str
) -> str:
    """
    UPDATED: Include Turkish descriptions from schema keywords to help LLM understand semantic meaning.
    """
    # Load schema keywords for Turkish descriptions
    try:
        from schema_keywords import SCHEMA_KEYWORDS
        all_keywords = SCHEMA_KEYWORDS
    except:
        all_keywords = {}
    
    prompt_parts = []
    
    prompt_parts.append("=== İZİN VERİLEN TABLO VE SÜTUNLAR SADECE BU TABLO.SÜTUN'LARI KULLANABİLİRSİN ===")
    prompt_parts.append("=== AŞAĞIDAKİ TABLOLARIN YAPISI CREATE TABLE BENZERİ FORMATTA VERİLMİŞTİR ===")
    prompt_parts.append("=== FROM KULLANIP ÇEKTİĞİN SÜTUNLAR KESİNLİKLE AŞAĞIDA AİT OLDUĞU TABLOSUYLA EŞLEŞMELİ!!! ===")
    prompt_parts.append("")
    
    for table, info in schema_pool.items():
        if not table:
            continue
        
        # Extract table name without schema
        table_name = table.split('.')[-1] if '.' in table else table
        
        # Get Turkish description for table
        table_desc = ""
        if table_name in all_keywords:
            table_keywords_list = all_keywords[table_name].get('table_keywords', [])
            if table_keywords_list:
                # table_keywords_list is a list of strings
                keywords = table_keywords_list[:3]  # First 3 keywords
                if keywords:
                    table_desc = f"  -- {', '.join(keywords)}"
        
        prompt_parts.append(f"{table} ({table_desc}")
        
        columns = info.get('columns', [])
        column_details = info.get('column_details', {})
        
        # Show all columns
        for column in columns:
            details = column_details.get(column, {})
            data_type = details.get('data_type', 'UNKNOWN')
            is_pk = details.get('is_pk', False)
            is_fk = details.get('is_fk', False)
            fk_ref = details.get('fk_ref')
            
            # Get Turkish description for column
            col_desc = ""
            if table_name in all_keywords:
                col_keywords_dict = all_keywords[table_name].get('column_keywords', {})
                if column in col_keywords_dict:
                    col_keywords_list = col_keywords_dict[column]
                    if col_keywords_list:
                        # col_keywords_list is a list of strings
                        keywords = col_keywords_list[:2]  # First 2 keywords
                        if keywords:
                            col_desc = f" ({', '.join(keywords)})"
            
            # Build label text with FK path if available
            if is_pk:
                label_text = f" -- PK{col_desc}"
            elif is_fk and fk_ref:
                # Show FK path: column_name -- FK -> referenced_table.referenced_column
                ref_table = fk_ref.get('table', '?')
                ref_column = fk_ref.get('column', '?')
                label_text = f" -- FK -> {ref_table}.{ref_column}{col_desc}"
            elif is_fk:
                label_text = f" -- FK{col_desc}"
            else:
                label_text = col_desc
            
            prompt_parts.append(f"    {column} {data_type}{label_text}")
        
        prompt_parts.append(")")
        prompt_parts.append("")

    # Show FK-PK relationships with data types and SQL examples
    prompt_parts.append("\n=== ZİNCİRLEME JOIN YOLLARI ===")
    prompt_parts.append("(Her JOIN yolunda veri tipleri ve hazır SQL örneği verilmiştir - EĞER JOIN KULLANILACAKSA aynen kopyala!)")
    prompt_parts.append("")
    
    if paths:
        filtered_paths = _filter_maximal_paths(paths)
        
        printed_chains = set()
        for path_key, hops in sorted(filtered_paths.items()):
            if not hops:
                continue
            
            # Build chain description and SQL example
            chain_parts = []
            sql_joins = []
            
            for i, hop in enumerate(hops):
                fk_table = hop.get('fk_table') or hop.get('from')
                fk_col = hop.get('fk_column') or ''
                pk_table = hop.get('pk_table') or hop.get('to')
                pk_col = hop.get('pk_column') or hop.get('ref_column') or ''
                
                if not (fk_table and fk_col and pk_table and pk_col):
                    continue
                
                # Get data types from schema_pool
                fk_type = None
                pk_type = None
                
                if fk_table in schema_pool:
                    fk_details = schema_pool[fk_table].get('column_details', {}).get(fk_col, {})
                    fk_type = fk_details.get('data_type', 'UNKNOWN')
                
                if pk_table in schema_pool:
                    pk_details = schema_pool[pk_table].get('column_details', {}).get(pk_col, {})
                    pk_type = pk_details.get('data_type', 'UNKNOWN')
                
                # Build chain part with types
                chain_parts.append(f"{fk_table}.{fk_col} ({fk_type}) --> {pk_table}.{pk_col} ({pk_type})")
                
                # Build SQL JOIN with automatic type casting if needed
                needs_casting = False
                if fk_type and pk_type:
                    # Check if types are different (case-insensitive comparison)
                    fk_base = fk_type.upper().split('(')[0].strip()
                    pk_base = pk_type.upper().split('(')[0].strip()
                    
                    # List of numeric types that are compatible
                    numeric_types = {'BIGINT', 'INTEGER', 'INT', 'SMALLINT', 'NUMERIC', 'DECIMAL'}
                    text_types = {'VARCHAR', 'TEXT', 'CHAR', 'CHARACTER VARYING'}
                    
                    # If one is numeric and one is text, need casting
                    if (fk_base in numeric_types and pk_base in text_types) or \
                       (fk_base in text_types and pk_base in numeric_types):
                        needs_casting = True
                
                # Build JOIN clause using full table names (no aliases to avoid confusion)
                if needs_casting:
                    sql_joins.append(f"  JOIN {pk_table} ON {fk_table}.{fk_col}::TEXT = {pk_table}.{pk_col}::TEXT")
                else:
                    sql_joins.append(f"  JOIN {pk_table} ON {fk_table}.{fk_col} = {pk_table}.{pk_col}")
            
            if not chain_parts:
                continue
            
            chain = " --> ".join(chain_parts)
            if chain in printed_chains:
                continue
            printed_chains.add(chain)
            
            # Output: chain description + SQL example
            prompt_parts.append(f"• {chain}")
            if sql_joins:
                prompt_parts.append("  SQL:")
                for sql_join in sql_joins:
                    prompt_parts.append(f"    {sql_join}")
            prompt_parts.append("")
    
    # If no paths found, show all FK relationships from schema_pool with types
    if not paths or not any(filtered_paths.values() if paths else []):
        prompt_parts.append("• (FK ilişkileri yukarıda her sütunun yanında gösterilmiştir)")
        prompt_parts.append("")
        
        # Collect all FK relationships from schema_pool with type info
        fk_relationships = []
        for table, info in schema_pool.items():
            column_details = info.get('column_details', {})
            for col_name, details in column_details.items():
                if details.get('is_fk') and details.get('fk_ref'):
                    fk_ref = details['fk_ref']
                    
                    # Get types
                    fk_type = details.get('data_type', 'UNKNOWN')
                    pk_type = 'UNKNOWN'
                    ref_table = fk_ref['table']
                    ref_col = fk_ref['column']
                    
                    if ref_table in schema_pool:
                        ref_details = schema_pool[ref_table].get('column_details', {}).get(ref_col, {})
                        pk_type = ref_details.get('data_type', 'UNKNOWN')
                    
                    # Check if casting needed
                    needs_casting = False
                    if fk_type and pk_type:
                        fk_base = fk_type.upper().split('(')[0].strip()
                        pk_base = pk_type.upper().split('(')[0].strip()
                        numeric_types = {'BIGINT', 'INTEGER', 'INT', 'SMALLINT', 'NUMERIC', 'DECIMAL'}
                        text_types = {'VARCHAR', 'TEXT', 'CHAR', 'CHARACTER VARYING'}
                        if (fk_base in numeric_types and pk_base in text_types) or \
                           (fk_base in text_types and pk_base in numeric_types):
                            needs_casting = True
                    
                    # Build relationship description with SQL (using full table names)
                    rel_desc = f"{table}.{col_name} ({fk_type}) --> {ref_table}.{ref_col} ({pk_type})"
                    if needs_casting:
                        sql_example = f"JOIN {ref_table} ON {table}.{col_name}::TEXT = {ref_table}.{ref_col}::TEXT"
                    else:
                        sql_example = f"JOIN {ref_table} ON {table}.{col_name} = {ref_table}.{ref_col}"
                    
                    fk_relationships.append((rel_desc, sql_example))
        
        # Show unique FK relationships with SQL examples
        seen = set()
        for rel_desc, sql_example in sorted(fk_relationships):
            if rel_desc not in seen:
                seen.add(rel_desc)
                prompt_parts.append(f"• {rel_desc}")
                prompt_parts.append(f"  SQL: {sql_example}")
                prompt_parts.append("")

    return "\n".join(prompt_parts)


def find_minimal_connecting_paths(
    fk_graph: Dict,
    selected_tables: Set[str],
    max_hops: int = MAX_PATH_HOPS
) -> Dict[str, List[Dict]]:
    """
    Produce directed edge chains: e1.from->e1.to, then e2 where e2.from == e1.to, ...
    Each hop contains: {'from','to','fk_table','fk_column','pk_table','pk_column','direction'}
    Returns a dict mapping keys like "start-end-idx" to lists of hops.

    Note: Only return chains whose start AND end tables are both within selected_tables.
    """
    from collections import defaultdict

    edges = fk_graph.get('edges', []) if isinstance(fk_graph, dict) else []
    cleaned = []
    for e in edges:
        a = e.get('from'); b = e.get('to')
        if not a or not b:
            continue
        cleaned.append({
            'from': a,
            'to': b,
            'fk_column': e.get('fk_column'),
            'ref_column': e.get('ref_column'),
            'raw': e
        })

    by_from = defaultdict(list)
    for e in cleaned:
        by_from[e['from']].append(e)

    results = {}
    seen_chains = set()
    idx = 0

    def dfs(path):
        nonlocal idx
        last = path[-1]
        # candidate chain key for dedupe
        key_text = "||".join(f"{h['from']}->{h['to']}:{h.get('fk_column') or ''}->{h.get('ref_column') or ''}" for h in path)
        if key_text in seen_chains:
            return
        seen_chains.add(key_text)

        # keep only chains up to max_hops (edges count)
        if 1 <= len(path) <= max_hops:
            # check endpoints: both endpoints must be in selected_tables (either order)
            first = path[0]
            last_h = path[-1]
            endpoints = {first['from'], last_h['to']}
            # require both endpoints to be in selected_tables
            if endpoints.issubset(selected_tables):
                key = f"{first['from']}-{last_h['to']}-{idx}"
                hop_list = []
                for h in path:
                    hop_list.append({
                        'from': h['from'],
                        'to': h['to'],
                        'fk_table': h['from'],
                        'fk_column': h.get('fk_column'),
                        'pk_table': h['to'],
                        'pk_column': h.get('ref_column'),
                        'direction': 'forward'
                    })
                results[key] = hop_list
                idx += 1

        # if length == max_hops, stop extending
        if len(path) >= max_hops:
            return

        # extend: find edges starting from current 'to'
        next_edges = by_from.get(last['to'], [])
        for ne in next_edges:
            # avoid trivial cycles by repeating the same table sequence
            tables_in_path = [p['from'] for p in path] + [p['to'] for p in path]
            if ne['to'] in tables_in_path and ne['from'] in tables_in_path:
                continue
            dfs(path + [ne])

    # Start DFS from every edge
    for e in cleaned:
        dfs([e])

    return results


def select_top_tables_balanced(semantic_results: dict, top_columns: list, target_count: int = 5) -> Set[str]:
    """NEW: Balanced table selection - updated logic."""
    print(f"\n🎯 NEW: Balanced table selection - Target: {target_count} tables")
    
    # Group tables by source - updated
    semantic_tables = {}
    lexical_tables = {}
    keyword_tables = {}
    
    for table, column, score, source, keyword_info in top_columns:
        if source == "semantic" or source == "both":
            if table not in semantic_tables or score > semantic_tables[table]:
                semantic_tables[table] = score
        if source == "lexical" or source == "both":
            if table not in lexical_tables or score > lexical_tables[table]:
                lexical_tables[table] = score
        if source == "keyword":
            if table not in keyword_tables or score > keyword_tables[table]:
                keyword_tables[table] = score
    
    # Select tables from each group
    selected_tables = set()
    
    # Priority order: Keyword > Lexical > Semantic
    # Add keyword tables first
    top_keyword = sorted(keyword_tables.items(), key=lambda x: x[1], reverse=True)
    for table, score in top_keyword:
        if len(selected_tables) < target_count:
            selected_tables.add(table)
            print(f"   🔑 KEYWORD table: {table} (score: {score:.3f})")
    
    # Add lexical tables
    top_lexical = sorted(lexical_tables.items(), key=lambda x: x[1], reverse=True)
    lexical_added = 0
    for table, score in top_lexical:
        if table not in selected_tables and len(selected_tables) < target_count:
            selected_tables.add(table)
            lexical_added += 1
            print(f"   🔤 LEXICAL table: {table} (score: {score:.3f})")
    
    # Add semantic tables (fill remaining slots)
    top_semantic = sorted(semantic_tables.items(), key=lambda x: x[1], reverse=True)
    semantic_added = 0
    for table, score in top_semantic:
        if table not in selected_tables and len(selected_tables) < target_count:
            selected_tables.add(table)
            semantic_added += 1
            print(f"   🧠 SEMANTIC table: {table} (score: {score:.3f})")
    
    print(f"   ✅ Final: {len(selected_tables)} tables ({lexical_added} lexical, {semantic_added} semantic, {len(top_keyword)} keyword)")
    
    return selected_tables


def _filter_maximal_paths(paths: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """Remove paths that are subpaths of other (longer) paths.
    If a path is an exact contiguous subsequence of a longer path, it is removed.
    """
    if not paths:
        return {}
    
    # First sort all paths by length (longer ones first)
    sorted_paths = sorted(paths.items(), key=lambda x: len(x[1]), reverse=True)
    
    # Build string representations for each path
    path_strings = {}
    for key, hops in sorted_paths:
        if not isinstance(hops, list) or not hops:
            continue
            
        # Represent the path as a string (including table and column info)
        path_parts = []
        for hop in hops:
            fk_table = hop.get('fk_table') or hop.get('from', '')
            fk_col = hop.get('fk_column', '')
            pk_table = hop.get('pk_table') or hop.get('to', '')
            pk_col = hop.get('pk_column') or hop.get('ref_column', '')
            
            if fk_table and pk_table:
                hop_str = f"{fk_table}.{fk_col}->{pk_table}.{pk_col}"
                path_parts.append(hop_str)
        
        if path_parts:
            path_strings[key] = "|".join(path_parts)
    
    # Find and remove subpaths
    maximal_keys = set(path_strings.keys())
    all_keys = list(path_strings.keys())
    
    for i in range(len(all_keys)):
        key_i = all_keys[i]
        path_i = path_strings[key_i]
        
        for j in range(len(all_keys)):
            if i == j:
                continue
                
            key_j = all_keys[j]
            path_j = path_strings[key_j]
            
            # If path_j is a contiguous subsequence of path_i, remove it
            if path_j in path_i:
                # If it's shorter and not identical, remove it
                if path_j != path_i and len(path_j) < len(path_i):
                    if key_j in maximal_keys:
                        maximal_keys.remove(key_j)
    
    # Also dedupe identical paths (keep only one of identical strings)
    unique_paths = {}
    for key in maximal_keys:
        path_str = path_strings[key]
        if path_str not in unique_paths.values():
            unique_paths[key] = path_str
        else:
            # If another key has the same path string, discard this duplicate key
            maximal_keys.discard(key)
    
    # Return the original paths
    return {k: paths[k] for k in maximal_keys if k in paths}


def unqualify_table(name: Optional[str], default_schema: str = None) -> str: # type: ignore
    """Return the unqualified table name.
    Examples: 'schema.foo' -> 'foo'; 'any_schema.bar' -> 'bar'.
    Returns empty string when input is None or falsy.
    """
    if default_schema is None:
        default_schema = settings.DB_SCHEMA
    if not name:
        return ""
    nl = str(name).lower()
    if '.' in nl:
        return nl.split('.', 1)[1]
    return nl



# ================ GLOBAL CACHE FOR STATIC PROMPT =================
_STATIC_PROMPT_PRIMED = False
_LLM_INSTANCE = None

def get_llm_instance():
    """Manage the LLM instance as a singleton - UPDATED"""
    global _LLM_INSTANCE
    
    if _LLM_INSTANCE is not None:
        return _LLM_INSTANCE
        
    print("⏳ Loading LLM model...")
    
    try:
        # Settings for reduced memory footprint
        _LLM_INSTANCE = Llama(
            model_path="./models/OpenR1-Qwen-7B-Turkish-Q4_K_M.gguf",
            n_ctx=4096,  # Try with lower context
            n_threads=6,  # Reduce thread count
            n_batch=128,
            low_vram=True,  # Low VRAM mode
            verbose=False   # Turn off debug logs
        )
        print("✅ LLM ready!")
        
        # Prime the static prompt only on first load
        prime_static_prompt_once()
        
    except Exception as e:
        print(f"❌ LLM load error: {e}")
        # Try an alternative smaller model
        print("🔄 Trying fallback model...")
        _LLM_INSTANCE = create_fallback_llm()
    
    return _LLM_INSTANCE

def create_fallback_llm():
    """Create a fallback/mock LLM instance."""
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
    global _STATIC_PROMPT_PRIMED
    if not _STATIC_PROMPT_PRIMED and _LLM_INSTANCE is not None:
        print("⏳ Starting static prompt priming...")
        try:
            # Shorter priming
            _LLM_INSTANCE("Merhaba", max_tokens=1, temperature=0)
            _STATIC_PROMPT_PRIMED = True
            print("✅ Static prompt priming complete.")
        except Exception as e:
            print(f"⚠️ Priming error: {e}")
            # Priming failure is not critical; continue
            _STATIC_PROMPT_PRIMED = True
        
class SQLErrorAnalyzer:
    """SQL error analysis helper - ENHANCED VERSION"""
    
    def analyze_error(self, error_message: str, sql_query: str, schema_pool: Dict) -> Dict:
        """Analyze SQL errors, including timestamp issues."""
        error_lower = error_message.lower()
        
        # Timestamp format error
        if "invalid input syntax for type timestamp" in error_lower:
            return {
                "error_type": "timestamp_format_error",
                "message": "Invalid date/time format",
                "problematic_parts": self._extract_timestamp_value(error_message),
                "suggestions": self._suggest_timestamp_fixes(error_message, sql_query),
                "needs_clarification": True
            }
        # Missing table error
        elif "table" in error_lower and "does not exist" in error_lower:
            return {
                "error_type": "missing_table",
                "message": error_message,
                "problematic_parts": self._extract_table_name(error_message),
                "suggestions": self._suggest_tables(schema_pool, error_message),
                "needs_clarification": True
            }
        # Missing column error
        elif "column" in error_lower and "does not exist" in error_lower:
            return {
                "error_type": "missing_column", 
                "message": error_message,
                "problematic_parts": self._extract_column_name(error_message),
                "suggestions": self._suggest_columns(schema_pool, error_message),
                "needs_clarification": True
            }
        # Syntax error
        else:
            return {
                "error_type": "syntax_error",
                "message": error_message,
                "problematic_parts": [],
                "suggestions": self._suggest_syntax_fixes(error_message),
                "needs_clarification": False  # Suggest automatic fixes
            }
    
    def _extract_timestamp_value(self, error_message: str) -> List[str]:
        """Extract values from a timestamp error message."""
        import re
        # Find invalid values like "asdaba"
        matches = re.findall(r"\"([^\"]+)\"", error_message)
        return matches if matches else []
    
    def _suggest_timestamp_fixes(self, error_message: str, sql_query: str) -> List[Dict]:
        """Suggestions for timestamp formatting fixes."""
        suggestions = []
        
        # Suggest valid timestamp formats
        timestamp_formats = [
            "YYYY-MM-DD",
            "YYYY-MM-DD HH:MI:SS", 
            "DD.MM.YYYY",
            "DD/MM/YYYY"
        ]
        
        for fmt in timestamp_formats:
            suggestions.append({
                "suggested": fmt,
                "type": "timestamp_format",
                "description": f"Accepted date format: {fmt}",
                "confidence": 80
            })
        
        # Suggest removing the condition
        suggestions.append({
            "suggested": "REMOVE_CONDITION",
            "type": "remove_condition", 
            "description": "Remove this condition and return all rows",
            "confidence": 60
        })
        
        return suggestions
    
    def _suggest_syntax_fixes(self, error_message: str) -> List[Dict]:
        """Suggestions for syntax errors."""
        return [
            {
                "suggested": "simplify_query",
                "type": "simplify",
                "description": "Simplify the query",
                "confidence": 70
            },
            {
                "suggested": "retry_generation", 
                "type": "retry",
                "description": "Regenerate the SQL",
                "confidence": 80
            }
        ]
    
    def _extract_table_name(self, error_message: str) -> List[str]:
        """Extract table name from an error message."""
        import re
        matches = re.findall(r"table \"([^\"]+)\"", error_message, re.IGNORECASE)
        return matches if matches else []
    
    def _extract_column_name(self, error_message: str) -> List[str]:
        """Extract column name from an error message."""
        import re
        matches = re.findall(r"column \"([^\"]+)\"", error_message, re.IGNORECASE)
        return matches if matches else []
    
    def _suggest_tables(self, schema_pool: Dict, error_message: str) -> List[Dict]:
        """Create table suggestions based on schema pool."""
        problematic_tables = self._extract_table_name(error_message)
        suggestions = []
        
        for table in problematic_tables:
            for existing_table in schema_pool.keys():
                # Simple similarity check
                if table.lower() in existing_table.lower() or existing_table.lower() in table.lower():
                    suggestions.append({
                        "suggested": existing_table,
                        "confidence": 80,
                        "reason": "Similar table name"
                    })
        
        return suggestions[:5]
    
    def _suggest_columns(self, schema_pool: Dict, error_message: str) -> List[Dict]:
        """Create column suggestions based on schema pool."""
        problematic_columns = self._extract_column_name(error_message)
        suggestions = []
        
        for column in problematic_columns:
            for table, columns in schema_pool.items():
                for existing_column in columns:
                    # Simple similarity check
                    if column.lower() in existing_column.lower() or existing_column.lower() in column.lower():
                        suggestions.append({
                            "suggested": existing_column,
                            "table": table,
                            "confidence": 80,
                            "reason": "Similar column name"
                        })
        
        return suggestions[:5]


# ================ INTERACTIVE SQL GENERATOR =================
class InteractiveSQLGenerator:
    """Class for interactive SQL generation and error correction."""
    
    def __init__(self):
        self.error_analyzer = SQLErrorAnalyzer()
        self.max_retries = 3
        self.conversation_history = []
        self.current_schema_pool = {}  # store schema pool
        self.llm = get_llm_instance()  # get LLM instance from global cache
        self.last_successful_query = None  # Remember successful queries
        self.conversation_context_window = 3  # window of last N conversations
        self.fk_relationships = {}  # store FK-PK relationships
        self.similarity_threshold = 0.6  # similarity threshold
        self.query_similarity_cache = {}  # cache for query similarities
        self.previous_conversation_fk_cache = {} # cache of previous conversation FK-PK paths


    def _make_fk_cache_keys(self, user_query: str, sql_content: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """Create consistent cache keys:
        - simple_key: hash of user_query (backward-compatible)
        - combo_key: hash of user_query + sql_content (more specific)
        """
        try:
            simple_key = f"fk_simple_{hash(user_query)}"
            combo_key = f"fk_combo_{hash(user_query)}_{hash(sql_content)}" if sql_content is not None else None
            return simple_key, combo_key
        except Exception as e:
            print(f"🔍 [_make_fk_cache_keys] Key oluşturma hatası: {e}")
            return f"fk_simple_{hash(user_query)}", None


    def _get_previous_pairs_from_history(self, limit_pairs: int = 3) -> List[Tuple[Dict, Dict]]:
        """Return up to `limit_pairs` most recent user->assistant(successful_sql) pairs
        from the conversation history. Pairs are returned chronologically.
        """
        pairs: List[Tuple[Dict, Dict]] = []
        try:
            history = list(self.conversation_history)  # copy
            i = len(history) - 1
            # scan backwards to find user->assistant pairs
            while i >= 0 and len(pairs) < limit_pairs:
                item = history[i]
                if item.get("type") == "successful_sql":
                    # assistant SQL found; search backwards for the preceding appropriate user_query
                    j = i - 1
                    while j >= 0:
                        prev = history[j]
                        if prev.get("type") == "user_query":
                            pairs.append((prev, item))
                            break
                        j -= 1
                    i = j - 1
                else:
                    i -= 1
            # pairs were collected newest->oldest; reverse to chronological order
            pairs.reverse()
        except Exception as e:
            print(f"🔍 [_get_previous_pairs_from_history] Hata: {e}")
        return pairs


    def _get_extended_conversation_context(self) -> str:
        """ENHANCED: Take the previous `limit` user->successful_sql pairs (chronological)
        and include for each pair the SQL and the original FK-PK paths used in that conversation.
        A seen-hash set prevents duplicates.
        """
        try:
            context_parts = []
            pairs = self._get_previous_pairs_from_history(limit_pairs=self.conversation_context_window)

            if not pairs:
                return ""

            context_parts.append("/* === LAST {} CONVERSATIONS === */".format(len(pairs)))

            seen_pair_hashes = set()
            for user_msg, assistant_msg in pairs:
                # dedupe same user_query+sql
                phash = (hash(user_msg.get("content", "")), hash(assistant_msg.get("content", "")))
                if phash in seen_pair_hashes:
                    continue
                seen_pair_hashes.add(phash)

                # add entries
                context_parts.append(f"USER QUERY: {user_msg.get('content','')}")
                context_parts.append(f"SQL: {assistant_msg.get('content','')}")

                # include the original FK-PK paths from the previous conversation (cache or compute)
                previous_fk_paths = self._get_cached_previous_fk_paths(user_msg.get('content', ''), assistant_msg.get('content', ''))
                if previous_fk_paths:
                    context_parts.append("/* --- Previous conversation FK-PK paths --- */")
                    context_parts.append(previous_fk_paths)

                context_parts.append("---")

            return "\n".join(context_parts)
        except Exception as e:
            print(f"🔍 [_get_extended_conversation_context] Hata: {e}")
            return ""


    def _get_cached_previous_fk_paths(self, user_query: str, sql_content: str) -> str:
        """Get FK paths shown in the previous conversation's dynamic prompt.
        First check cache (combo key), then simple key. If not found, compute from SQL
        and store in cache (both combo and simple keys).
        """
        try:
            if not user_query and not sql_content:
                return ""

            # init cache
            if not hasattr(self, 'dynamic_prompt_fk_cache'):
                self.dynamic_prompt_fk_cache = {}

            simple_key, combo_key = self._make_fk_cache_keys(user_query, sql_content)

            # 1) Check combo key first (most specific)
            if combo_key:
                cached = self.dynamic_prompt_fk_cache.get(combo_key)
                if cached:
                    print(f"🔍 [_get_cached_previous_fk_paths] Combo-cache bulundu.")
                    return cached

            # 2) fallback to simple key
            cached = self.dynamic_prompt_fk_cache.get(simple_key)
            if cached:
                print(f"🔍 [_get_cached_previous_fk_paths] Simple-cache bulundu.")
                return cached

            # 3) If cache not found, extract tables from SQL and compute paths
            tables = self._extract_used_tables_from_sql(sql_content)
            if len(tables) < 2:
                # store empty string for performance/caching
                if combo_key:
                    self.dynamic_prompt_fk_cache[combo_key] = ""
                self.dynamic_prompt_fk_cache[simple_key] = ""
                print(f"🔍 [_get_cached_previous_fk_paths] Yeterli tablo yok, cache'e boş yazıldı.")
                return ""

            fk_graph = load_fk_graph()
            paths = find_minimal_connecting_paths(fk_graph, tables, MAX_PATH_HOPS)

            fk_paths = self._format_fk_paths_like_previous_dynamic(paths)
            # store in cache (both combo and simple)
            if combo_key:
                self.dynamic_prompt_fk_cache[combo_key] = fk_paths
            self.dynamic_prompt_fk_cache[simple_key] = fk_paths

            print(f"🔍 [_get_cached_previous_fk_paths] Computed FK paths and cached result.")
            return fk_paths
        except Exception as e:
            print(f"⚠️ [_get_cached_previous_fk_paths] Hata: {e}")
            return ""


    def _cache_current_fk_paths(self, natural_query: str, paths: Dict, sql_content: Optional[str] = None):
        """Cache the FK paths for the current query (store under both simple and combo keys).
        - natural_query: the user query
        - paths: output from find_minimal_connecting_paths
        - sql_content: optional final SQL or assistant response text
        """
        try:
            if not hasattr(self, 'dynamic_prompt_fk_cache'):
                self.dynamic_prompt_fk_cache = {}

            fk_paths = self._format_fk_paths_like_previous_dynamic(paths)
            if not fk_paths:
                # still write empty string under simple key (for future fallback)
                simple_key, combo_key = self._make_fk_cache_keys(natural_query, sql_content or "")
                self.dynamic_prompt_fk_cache[simple_key] = ""
                if combo_key:
                    self.dynamic_prompt_fk_cache[combo_key] = ""
                print(f"🔍 [_cache_current_fk_paths] FK paths empty, cached empty string.")
                return

            simple_key, combo_key = self._make_fk_cache_keys(natural_query, sql_content or fk_paths)

            # store
            self.dynamic_prompt_fk_cache[simple_key] = fk_paths
            if combo_key:
                self.dynamic_prompt_fk_cache[combo_key] = fk_paths

            print(f"🔍 [_cache_current_fk_paths] Current query FK paths cached (len={len(fk_paths)})")
        except Exception as e:
            print(f"⚠️ [_cache_current_fk_paths] Cache yazma hatası: {e}")


    # (Optional) call suggestion: when final `sql_text` is obtained after the LLM call
    # self._cache_current_fk_paths(natural_query, paths, sql_content=sql_text)
    # write it back using the combo-key like this. This strengthens exact matching.



    def _extract_tables_from_sql_simple(self, sql: str) -> set:
        """
        Extract table names from SQL - SIMPLE VERSION.
        Scans `FROM` and `JOIN` clauses and returns a set of table identifiers.
        """
        import re

        tables = set()

        try:
            # FROM / JOIN yakalama
            pattern = r'\bFROM\s+([\w\.]+)|\bJOIN\s+([\w\.]+)'
            matches = re.findall(pattern, sql, flags=re.IGNORECASE)

            for m in matches:
                t = m[0] if m[0] else m[1]
                # strip the alias
                t = t.split()[0]
                tables.add(t)

            return tables

        except Exception:
            return set()

    def _cache_fk_paths(self, tables, fk_paths):
        """
        Process found FK-PK paths into the cache.
        Store both directions for each table pair.
        """
        if not hasattr(self, "_FK_PATH_CACHE"):
            self._FK_PATH_CACHE = {}

        for (t1, t2), path in fk_paths.items():
            key = tuple(sorted([t1, t2]))
            self._FK_PATH_CACHE[key] = path

    def _get_fk_path_from_cache(self, t1, t2):
        """
        Önceki sorgulardan bilinen FK-PK yolunu getirir.
        """
        if not hasattr(self, "_FK_PATH_CACHE"):
            return None

        key = tuple(sorted([t1, t2]))
        return self._FK_PATH_CACHE.get(key)


    def _merge_fk_paths_with_cache(self, tables, new_fk_paths):
        """
        Yeni sorguda bulunan FK yollarını alır.
        Eğer bazı tablo çiftleri için yol bulunamazsa,
        önceki sorgulardan cache'teki yolu ekler.
        """
        final_paths = dict(new_fk_paths)

        # iterate over all table pairs
        table_list = list(tables)

        for i in range(len(table_list)):
            for j in range(i + 1, len(table_list)):
                t1 = table_list[i]
                t2 = table_list[j]

                key = (t1, t2)

                # skip if the new query already found
                if key in final_paths or (t2, t1) in final_paths:
                    continue

                # is there a path in the cache?
                cached = self._get_fk_path_from_cache(t1, t2)
                if cached:
                    final_paths[key] = cached

        return final_paths

    def resolve_fk_paths(self, tables, fk_paths_new):
        """
        Bu fonksiyon yeni FK yollarını alır,
        eksik olanları cache ile tamamlar,
        sonra final yolları yine cache'e yazar.
        """
        # 1) Merge with cache
        final_paths = self._merge_fk_paths_with_cache(tables, fk_paths_new)

        # 2) Update the cache
        self._cache_fk_paths(tables, final_paths)

        return final_paths

    def _format_fk_paths_like_previous_dynamic(self, paths: Dict[str, List[Dict]]) -> str:
        """
        FK yollarını önceki dinamik prompt'taki gibi formatla
        """
        if not paths:
            return ""

        # Filtrele: sadece maksimal zincirleri al
        filtered_paths = _filter_maximal_paths(paths)

        relationship_lines = []

        for path_key, hops in sorted(filtered_paths.items()):
            if not hops:
                continue

            parts = []

            for hop in hops:
                fk_table = hop.get("fk_table") or hop.get("from")
                fk_col = hop.get("fk_column") or ""
                pk_table = hop.get("pk_table") or hop.get("to")
                pk_col = hop.get("pk_column") or hop.get("ref_column") or ""

                if fk_table and fk_col and pk_table and pk_col:
                    parts.append(f"{fk_table}.{fk_col}(FK) --> {pk_table}.{pk_col}(PK)")

            if parts:
                chain = " ---- ".join(parts)
                relationship_lines.append(f"• {chain}")

        if not relationship_lines:
            return ""

        return "\n".join(relationship_lines)




    def _get_previous_conversation_fk_context_correct(self, user_msg: Dict, assistant_msg: Dict) -> str:
        """
        Retrieve the original FK-PK relationships referenced in the previous
        conversation - CORRECTED VERSION.
        """
        try:
            sql_content = assistant_msg.get('content', '')
            user_query = user_msg.get('content', '')
            
            print(f"🔍 [PREVIOUS_FK_CORRECT] Önceki konuşma analizi: '{user_query[:50]}...'")
            
            # Create the unique ID for the previous conversation
            conversation_id = f"prev_{hash(user_query)}_{hash(sql_content)}"
            
            # Check if it exists in the cache
            if hasattr(self, 'previous_conversation_fk_cache'):
                cached_result = self.previous_conversation_fk_cache.get(conversation_id)
                if cached_result is not None:
                    print(f"🔍 [PREVIOUS_FK_CORRECT] Retrieved previous conversation FK relationships from cache")
                    return cached_result
            
            # Extract tables from the SQL
            tables = self._extract_used_tables_from_sql(sql_content)
            
            if not tables:
                print(f"🔍 [PREVIOUS_FK_CORRECT] Önceki konuşmada tablo bulunamadı")
                self.previous_conversation_fk_cache[conversation_id] = ""
                return ""
            
            print(f"🔍 [PREVIOUS_FK_CORRECT] Önceki konuşmadan çıkarılan tablolar: {tables}")
            
            # Load the FK graph
            fk_graph = load_fk_graph()
            
            # ✅ CRITICAL FIX: Find FK-PK relationships for the tables in the previous conversation
            # Use only the tables from the previous conversation here, NOT the current schema pool
            paths = find_minimal_connecting_paths(fk_graph, tables, MAX_PATH_HOPS)
            
            print(f"🔍 [PREVIOUS_FK_CORRECT] Bulunan paths sayısı: {len(paths)}")
            
            # Format the relationships - PREVIOUS CONVERSATION style
            fk_context = self._format_previous_conversation_fk_context(paths, tables)
            
            if not fk_context:
                print(f"🔍 [PREVIOUS_FK_CORRECT] Önceki konuşma için FK ilişkisi bulunamadı")
                self.previous_conversation_fk_cache[conversation_id] = ""
                return ""
            
            # Cache'e kaydet
            if not hasattr(self, 'previous_conversation_fk_cache'):
                self.previous_conversation_fk_cache = {}
            self.previous_conversation_fk_cache[conversation_id] = fk_context
            
            print(f"🔍 [PREVIOUS_FK_CORRECT] Önceki konuşma FK context oluşturuldu: {len(fk_context)} karakter")
            
            return fk_context
            
        except Exception as e:
            print(f"⚠️ Önceki konuşma FK context hatası: {e}")
            return ""

    def _extract_used_tables_from_sql(self, sql: str) -> set:
        """
        Extract ONLY the tables actually used in the SQL.
        Returns a set of schema-qualified table names inferred from FROM/JOIN.
        """
        import re
        
        tables = set()
        
        try:
            # Only take table names from the FROM and JOIN clauses
            from_pattern = r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_.]*)'
            join_pattern = r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_.]*)'
            
            from_matches = re.findall(from_pattern, sql, re.IGNORECASE)
            join_matches = re.findall(join_pattern, sql, re.IGNORECASE)
            
            for table_name in from_matches + join_matches:
                # If not schema-qualified, add the schema
                table = table_name if '.' in table_name else f"{settings.DB_SCHEMA}.{table_name}"
                tables.add(table)
            
            print(f"🔍 [EXTRACT_USED_TABLES] Tables extracted FROM the SQL: {tables}")
            
        except Exception as e:
            print(f"⚠️ SQL'den tablo çıkarma hatası: {e}")
        
        return tables

    def _format_previous_conversation_fk_context(self, paths: Dict[str, List[Dict]], original_tables: set) -> str:
        """
        Format FK-PK relationships in the style used by previous-conversation
        dynamic prompts (corrected format).
        """
        if not paths:
            return ""
        
        filtered_paths = _filter_maximal_paths(paths)
        
        relationship_lines = []
        printed_chains = set()
        
        for path_key, hops in sorted(filtered_paths.items()):
            if not hops:
                continue
                
            parts = []
            for hop in hops:
                fk_table = hop.get('fk_table') or hop.get('from')
                fk_col = hop.get('fk_column') or ''
                pk_table = hop.get('pk_table') or hop.get('to')
                pk_col = hop.get('pk_column') or hop.get('ref_column') or ''
                
                if fk_table and fk_col and pk_table and pk_col:
                    parts.append(f"{fk_table}.{fk_col}(FK) --> {pk_table}.{pk_col}(PK)")
            
            if parts:  # Only if valid parts exist
                chain = " ---- ".join(parts)
                if chain not in printed_chains:
                    printed_chains.add(chain)
                    relationship_lines.append(f"• {chain}")
        
        if not relationship_lines:
            return ""
        
        # Show at most 3 relationships (to avoid too many)
        if len(relationship_lines) > 3:
            relationship_lines = relationship_lines[:3]
            relationship_lines.append("• ... (other relationships)")
        
        return "\n".join(relationship_lines)


    def _get_previous_conversation_fk_context_comprehensive(self, user_msg: Dict, assistant_msg: Dict) -> str:
        """
        Retrieve FK-PK relationships from the previous conversation - a
        SIMPLIFIED/COMPREHENSIVE variant that prefers direct relationships.
        """
        try:
            sql_content = assistant_msg.get('content', '')
            user_query = user_msg.get('content', '')
            
            print(f"🔍 [PREVIOUS_FK_SIMPLE] Önceki konuşma analizi: '{user_query[:50]}...'")
            
            # Create the unique ID for the previous conversation
            conversation_id = f"prev_{hash(user_query)}_{hash(sql_content)}"
            
            # Check if it exists in the cache
            if hasattr(self, 'previous_conversation_fk_cache'):
                cached_result = self.previous_conversation_fk_cache.get(conversation_id)
                if cached_result is not None:
                    print(f"🔍 [PREVIOUS_FK_SIMPLE] Cache'den önceki konuşma FK ilişkileri getirildi")
                    return cached_result
            
            # Extract tables from the SQL - SIMPLIFIED
            tables = self._extract_used_tables_from_sql(sql_content)
            
            # ✅ SINGLE-TABLE CHECK: If only 1 table, there are no FK relationships
            if len(tables) <= 1:
                print(f"🔍 [PREVIOUS_FK_SIMPLE] Previous conversation had 1 or fewer tables: {tables}, no FK relationships will be shown")
                self.previous_conversation_fk_cache[conversation_id] = ""
                return ""
            
            print(f"🔍 [PREVIOUS_FK_SIMPLE] Önceki konuşmadan çıkarılan tablolar: {tables}")
            
            # Load the FK graph
            fk_graph = load_fk_graph()
            
            # ✅ NEW APPROACH: Find only direct relationships among used tables
            direct_relationships = self._find_direct_relationships_only(fk_graph, tables)
            
            if not direct_relationships:
                print(f"🔍 [PREVIOUS_FK_SIMPLE] Önceki konuşma için doğrudan FK ilişkisi bulunamadı")
                self.previous_conversation_fk_cache[conversation_id] = ""
                return ""
            
            # Format the relationships - SIMPLIFIED
            fk_context = self._format_minimal_fk_context(direct_relationships)
            
            if not fk_context:
                print(f"🔍 [PREVIOUS_FK_SIMPLE] Formatlanacak FK ilişkisi bulunamadı")
                self.previous_conversation_fk_cache[conversation_id] = ""
                return ""
            
            # Cache'e kaydet
            if not hasattr(self, 'previous_conversation_fk_cache'):
                self.previous_conversation_fk_cache = {}
            self.previous_conversation_fk_cache[conversation_id] = fk_context
            
            print(f"🔍 [PREVIOUS_FK_SIMPLE] Önceki konuşma FK context oluşturuldu: {len(fk_context)} karakter")
            
            return fk_context
            
        except Exception as e:
            print(f"⚠️ Önceki konuşma FK context hatası: {e}")
            return ""

    def _find_direct_relationships_only(self, fk_graph: Dict, tables: set) -> List[Dict]:
        """
        Find ONLY direct FK relationships between the given tables. Do not
        return extended multi-hop relationships.
        """
        try:
            edges = fk_graph.get('edges', []) if isinstance(fk_graph, dict) else []
            relationships = []
            
            # Only take relationships where both tables are among the used tables
            for edge in edges:
                from_table = edge.get('from', '')
                to_table = edge.get('to', '')
                fk_column = edge.get('fk_column', '')
                ref_column = edge.get('ref_column', '')
                
                # ONLY if both tables are among the used tables
                if from_table in tables and to_table in tables:
                    relationships.append({
                        'from': from_table,
                        'to': to_table,
                        'fk_column': fk_column,
                        'ref_column': ref_column
                    })
            
            print(f"🔍 [FIND_DIRECT_RELATIONS] Bulunan doğrudan ilişki sayısı: {len(relationships)}")
            return relationships
            
        except Exception as e:
            print(f"⚠️ Doğrudan FK ilişki bulma hatası: {e}")
            return []

    def _format_minimal_fk_context(self, relationships: List[Dict]) -> str:
        """
        Minimal FK-PK formatting: show only direct relationships.
        """
        if not relationships:
            return ""
        
        print(f"🔍 [FORMAT_MINIMAL] Formatlanacak doğrudan ilişki sayısı: {len(relationships)}")
        
        relationship_lines = []
        printed_chains = set()
        
        for rel in relationships:
            chain = f"{rel['from']}.{rel['fk_column']}(FK) --> {rel['to']}.{rel['ref_column']}(PK)"
            if chain not in printed_chains:
                printed_chains.add(chain)
                relationship_lines.append(f"• {chain}")
                print(f"🔍 [FORMAT_MINIMAL] Doğrudan ilişki eklendi: {chain}")
        
        if not relationship_lines:
            print(f"🔍 [FORMAT_MINIMAL] Formatlanacak ilişki bulunamadı")
            return ""
        
        # Show at most 3 relationships (to avoid too many)
        if len(relationship_lines) > 3:
            relationship_lines = relationship_lines[:3]
            relationship_lines.append("• ... (other relationships)")
        
        result = "\n".join(relationship_lines)
        print(f"🔍 [FORMAT_MINIMAL] Sonuç: {len(relationship_lines)} ilişki")
        return result


    def _extract_all_tables_from_sql_comprehensive(self, sql: str) -> set:
        """
        Extract all table names from SQL - COMPREHENSIVE VERSION.
        Handles FROM, JOIN, INTO, UPDATE, and DELETE patterns.
        """
        import re
        
        tables = set()
        
        try:
            # Extract tables for all possible SQL patterns
            patterns = [
                r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_.]*)',           # FROM clause
                r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_.]*)',           # JOIN clause
                r'\bINTO\s+([a-zA-Z_][a-zA-Z0-9_.]*)',           # INSERT INTO
                r'\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_.]*)',         # UPDATE
                r'\bDELETE\s+FROM\s+([a-zA-Z_][a-zA-Z0-9_.]*)',  # DELETE FROM
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, sql, re.IGNORECASE)
                for match in matches:
                    # If not schema-qualified, add the schema
                    table = match if '.' in match else f"{settings.DB_SCHEMA}.{match}"
                    tables.add(table)
            
            print(f"🔍 [EXTRACT_TABLES_COMP] SQL'den çıkarılan tablolar: {tables}")
            
        except Exception as e:
            print(f"⚠️ SQL'den tablo çıkarma hatası: {e}")
        
        return tables

    def _find_all_fk_relationships_for_tables(self, fk_graph: Dict, tables: set) -> List[Dict]:
        """
        Find all FK relationships relevant to the provided table set.
        Returns direct relationships and extended ones when applicable.
        """
        try:
            edges = fk_graph.get('edges', []) if isinstance(fk_graph, dict) else []
            relationships = []
            
            # Check all edges
            for edge in edges:
                from_table = edge.get('from', '')
                to_table = edge.get('to', '')
                fk_column = edge.get('fk_column', '')
                ref_column = edge.get('ref_column', '')
                
                # If both ends of the edge are in our table set
                if from_table in tables and to_table in tables:
                    relationships.append({
                        'from': from_table,
                        'to': to_table, 
                        'fk_column': fk_column,
                        'ref_column': ref_column,
                        'type': 'direct'
                    })
                # Or only one end is in our table set (wider network)
                elif from_table in tables or to_table in tables:
                    relationships.append({
                        'from': from_table,
                        'to': to_table,
                        'fk_column': fk_column,
                        'ref_column': ref_column,
                        'type': 'extended'
                    })
            
            print(f"🔍 [FIND_ALL_FK] Bulunan ilişki sayısı: {len(relationships)}")
            return relationships
            
        except Exception as e:
            print(f"⚠️ FK ilişki bulma hatası: {e}")
            return []

    def _format_comprehensive_fk_context(self, relationships: List[Dict], original_tables: set) -> str:
        """
        Format a comprehensive FK-PK context string showing all relevant
        relationships (direct first, then extended relationships).
        """
        if not relationships:
            return ""
        
        print(f"🔍 [FORMAT_COMPREHENSIVE] Formatlanacak ilişki sayısı: {len(relationships)}")
        
        relationship_lines = []
        printed_chains = set()
        
        # First show direct relationships (both tables are in original_tables)
        direct_relationships = [r for r in relationships if r.get('type') == 'direct']
        for rel in direct_relationships:
            chain = f"{rel['from']}.{rel['fk_column']}(FK) --> {rel['to']}.{rel['ref_column']}(PK)"
            if chain not in printed_chains:
                printed_chains.add(chain)
                relationship_lines.append(f"• {chain}")
                print(f"🔍 [FORMAT_COMPREHENSIVE] Doğrudan ilişki eklendi: {chain}")
        
        # If no direct relationships, show extended relationships
        if not relationship_lines:
            extended_relationships = [r for r in relationships if r.get('type') == 'extended']
            for rel in extended_relationships:
                # Only show relationships that include tables from original_tables
                if rel['from'] in original_tables or rel['to'] in original_tables:
                    chain = f"{rel['from']}.{rel['fk_column']}(FK) --> {rel['to']}.{rel['ref_column']}(PK)"
                    if chain not in printed_chains:
                        printed_chains.add(chain)
                        relationship_lines.append(f"• {chain}")
                        print(f"🔍 [FORMAT_COMPREHENSIVE] Genişletilmiş ilişki eklendi: {chain}")
        
        if not relationship_lines:
            print(f"🔍 [FORMAT_COMPREHENSIVE] Formatlanacak ilişki bulunamadı")
            return ""
        
        result = "\n".join(relationship_lines)
        print(f"🔍 [FORMAT_COMPREHENSIVE] Sonuç: {len(relationship_lines)} ilişki")
        return result

    # Also, to ensure conversation history is recorded correctly:
    def _add_to_conversation_history(self, role: str, content: any, query_type: str = "general"): # type: ignore
        """Append a new message to the conversation history - UPDATED.

        Also performs light cache cleanup for previous FK caches when new
        user queries arrive to prevent unbounded growth.
        """
        # Add logic to clean up previous cache
        if role == "user" and query_type == "user_query":
            # When a new user query arrives, trim the previous conversation cache a bit
            # This prevents the cache from growing too large
            if hasattr(self, 'previous_conversation_fk_cache'):
                cache_size = len(self.previous_conversation_fk_cache)
                if cache_size > 10:  # If cache has grown too large
                    # Remove the oldest 5 entries
                    keys_to_remove = list(self.previous_conversation_fk_cache.keys())[:5]
                    for key in keys_to_remove:
                        del self.previous_conversation_fk_cache[key]
                    print(f"🔍 [CACHE_CLEANUP] {len(keys_to_remove)} old cache entries cleaned")
        
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "type": query_type
        })
        
        # Keep the last 20 messages (for performance)
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

    def _filter_paths_for_previous_conversation_only(self, paths: Dict[str, List[Dict]], original_tables: set) -> Dict[str, List[Dict]]:
        """
        Filter paths to include only those whose tables are all present in the
        provided `original_tables` set (paths limited to previous conversation).
        """
        filtered_paths = {}
        
        for path_key, hops in paths.items():
            if not hops:
                continue
                
            # Check whether all tables in the path were present in the previous conversation
            all_tables_in_previous = True
            for hop in hops:
                fk_table = hop.get('fk_table') or hop.get('from')
                pk_table = hop.get('pk_table') or hop.get('to')
                
                if fk_table not in original_tables or pk_table not in original_tables:
                    all_tables_in_previous = False
                    break
            
            if all_tables_in_previous:
                filtered_paths[path_key] = hops
        
        return filtered_paths



    def _format_fk_context(self, paths: Dict[str, List[Dict]]) -> str:
        """
        Format FK-PK relationships into a conversation-history-friendly string.
        Only maximal chains are kept and duplicate chains are suppressed.
        """
        if not paths:
            return ""
        
        # Filtrele: sadece maximal zincirleri al
        filtered_paths = _filter_maximal_paths(paths)
        
        relationship_lines = []
        printed_chains = set()
        
        for path_key, hops in sorted(filtered_paths.items()):
            if not hops:
                continue
                
            parts = []
            for hop in hops:
                fk_table = hop.get('fk_table') or hop.get('from')
                fk_col = hop.get('fk_column') or ''
                pk_table = hop.get('pk_table') or hop.get('to')
                pk_col = hop.get('pk_column') or hop.get('ref_column') or ''
                
                if fk_table and fk_col and pk_table and pk_col:
                    parts.append(f"{fk_table}.{fk_col}(FK) --> {pk_table}.{pk_col}(PK)")
                else:
                    parts.append(f"{hop.get('from')} → {hop.get('to')}")
            
            chain = " ---- ".join(parts)
            if chain in printed_chains:
                continue
            printed_chains.add(chain)
            relationship_lines.append(f"• {chain}")
        
        if not relationship_lines:
            return ""
        
        return "\n".join(relationship_lines)

    # Also, store FK paths in cache after each SQL generation
    def _generate_smart_sql_direct(self, natural_query: str, error_context: str = "", 
                        hybrid_results: Optional[Dict] = None) -> str:
        """
        UPDATED: Generate SQL directly using conversation history and FK
        relationships. FK paths are cached for reuse.
        """
        start_time = time.time()

        # 1. Load FK graph
        fk_graph = load_fk_graph()

        # 2. Enhanced search
        if hybrid_results is None:
            print("🔍 Performing enhanced semantic + lexical search...")
            search_start = time.time()
            hybrid_results = hybrid_search_with_separate_results(natural_query)
            print(f"⏱️  [1] Enhanced search: {time.time() - search_start:.2f}s")
        else:
            print("🔍 Using pre-computed enhanced results...")
        
        semantic_results = {
            "selected_tables": hybrid_results["selected_tables"],
            "all_semantic": hybrid_results["all_semantic"],
            "all_lexical": hybrid_results["all_lexical"],
            "keywords": hybrid_results.get("all_keywords", []),
            "values": hybrid_results.get("all_data_values", [])
        }
        
        value_context = {}
        
        print(f"📊 Semantic results: {len(semantic_results['all_semantic'])} columns")
        print(f"🔤 Lexical results: {len(semantic_results['all_lexical'])} columns")

        if not semantic_results.get('selected_tables'):
            raise ValueError("❌ İlgili tablo bulunamadı (enhanced search)")

        # 3. Column-based scoring
        scoring_start = time.time()
        top_columns = score_columns_by_relevance_separate(semantic_results, value_context, top_n=TOP_COLUMNS_IN_CONTEXT)
        print(f"⏱️  [2] Column scoring: {time.time() - scoring_start:.2f}s")
        print(f"🎯 Top columns selected: {len(top_columns)}")

        # 4. Table selection
        selected_tables = set(semantic_results["selected_tables"])
        print(f"🏢 Selected tables: {len(selected_tables)}")

        # 5. Build compact schema pool
        schema_start = time.time()
        schema_pool, paths, value_context = build_compact_schema_pool(
            semantic_results, selected_tables, fk_graph, top_columns=top_columns
        )
        
        # ✅ NEW: Cache this query's FK paths
        self._cache_current_fk_paths(natural_query, paths)
        
        # 6. ENHANCED: Get conversation history and FK relationships
        conversation_context = self._get_extended_conversation_context()
        
        # 7. Schema formatting - ENHANCED
        prompt_start = time.time()
        schema_text = format_compact_schema_prompt_with_keywords(
            schema_pool, paths, fk_graph, top_columns, natural_query
        )
        
        # Combine all contexts
        enhanced_context_parts = []
        if conversation_context:
            enhanced_context_parts.append(conversation_context)

        
        enhanced_context = "\n\n".join(enhanced_context_parts)
        enhanced_schema_text = f"{enhanced_context}\n\n{schema_text}" if enhanced_context else schema_text
        
        dynamic_prompt = generate_strict_prompt_dynamic_only(
            natural_query, enhanced_schema_text, schema_pool, value_context
        )

        print(f"⏱️  [5] Prompt generation: {time.time() - prompt_start:.2f}s")
        print(f"📝 Context uzunluğu: Konuşma: {len(conversation_context)}")

        # ✅ NEW: Print dynamic prompt in detail
        print(f"\n{'='*100}")
        print(f"🎯 DİNAMİK PROMPT İÇERİĞİ:")
        print(f"{'='*100}")
        print(dynamic_prompt)
        print(f"{'='*100}")
        print(f"🎯 PROMPT UZUNLUĞU: {len(dynamic_prompt)} karakter")
        print(f"{'='*100}\n")

        # 8. LLM call (rest of code unchanged)
        llm_start = time.time()
        try:
            response = self.llm(
                dynamic_prompt,
                max_tokens=500,  # Optimize: 800 -> 500 (hız için)
                temperature=0,
                top_p=0.9,
                stop=[";", "Kullanıcı", "Açıklama", "AÇIKLAMA", "**AÇIKLAMA**", "ÖRNEK", "```\n\n", "<|end"],
                stream=False,
                echo=False
            )
            
            # Response parsing
            text = self._parse_llm_response(response)
            
            print(f"⏱️  [6] LLM call: {time.time() - llm_start:.2f}s")
            print(f"🤖 LLM Response:\n{text}\n")
            
        except Exception as e:
            print(f"❌ LLM call failed: {e}")
            text = "SELECT 1"

        # 9. Extract SQL (rest of code unchanged)
        extraction_start = time.time()
        sql_text = extract_sql_from_response(text)
        print(f"⏱️  [7] SQL extraction: {time.time() - extraction_start:.2f}s")
        
        # 10. Clean meaningless WHERE clauses
        sql_text, where_changes = clean_meaningless_where_clauses(sql_text)
        if where_changes:
            print(f"🧹 Cleaned WHERE clauses:")
            for c in where_changes:
                print(f"  - {c}")
        
        # 11. Auto-fix
        autofix_start = time.time()
        try:
            print("🔧 Auto-fix running...")
            fixed_sql, changes, issues = auto_fix_sql_identifiers(
                sql_text, schema_pool, value_context
            )
            if changes:
                print(f"🔁 Auto-fix applied. Changes ({len(changes)}):")
                for c in changes[:5]:
                    print("  -", c)
                sql_to_format = fixed_sql
            else:
                print("🔎 Auto-fix found no changes.")
                sql_to_format = sql_text
            
            if issues:
                print("⚠️ Auto-fix issues:")
                for it in issues[:3]:
                    print("  -", it)
                    
        except Exception as e:
            print(f"❌ Auto-fix failed: {e}")
            sql_to_format = sql_text
        
        print(f"⏱️  [8] Auto-fix: {time.time() - autofix_start:.2f}s")
        
        # 12. Format SQL
        format_start = time.time()
        try:
            parsed = sqlparse.parse(sql_to_format)
            if not parsed:
                raise ValueError("❌ SQL parse edilemedi")
            final_sql = sqlparse.format(str(parsed[0]), reindent=True, keyword_case='upper')
        except Exception as e:
            print(f"❌ SQL formatting failed: {e}")
            final_sql = sql_to_format
        
        print(f"⏱️  [9] SQL formatting: {time.time() - format_start:.2f}s")
        
        total_time = time.time() - start_time
        print(f"\n{'#'*80}")
        print(f"# ✅ COMPLETED - {total_time:.2f}s")
        print(f"# FINAL SQL:")
        print(f"{'#'*80}")
        print(final_sql)
        print(f"{'#'*80}\n")
        
        return final_sql

    def _check_and_ask_for_low_similarity(self, sql_query: str, natural_query: str, 
                                    top_similarity: float, hybrid_results: Dict) -> Optional[Dict]:
        """If the top similarity is low, ask the user for clarification.

        Returns a frontend-friendly dict with suggestions when clarification is
        required; otherwise returns None.
        """
        if top_similarity >= self.similarity_threshold:
            return None
        
        # Get hybrid search suggestions (use existing results)
        hybrid_suggestions = self._get_hybrid_suggestions_from_results(hybrid_results)
        
        question = f"""🤔 Aradığınız sorgu için en iyi eşleşme %{top_similarity*100:.1f} benzerlik gösteriyor (eşik: %{self.similarity_threshold*100}).

    Bu, aradığınız şeyle tam olarak eşleşmediğimiz anlamına gelebilir.

    🔍 **En iyi eşleşen önerilerimiz:**"""
        
        # Add hybrid suggestions
        if hybrid_suggestions["suggestions"]:
            for i, suggestion in enumerate(hybrid_suggestions["suggestions"][:5], 1):
                icon = "🧠" if suggestion["type"] == "semantic" else "🔤" if suggestion["type"] == "lexical" else "⚡"
                question += f"\n{i}. {icon} **{suggestion['display']}** - {suggestion['description']}"
        
        question += "\n\n💡 **Nasıl devam etmek istersiniz?**\n"
        question += "• 'devam' - Yine de SQL oluşturmaya devam et\n"
        question += "• 'yeniden' - Sorguyu yeniden yaz\n"
        if hybrid_suggestions["suggestions"]:
            question += "• Numara (1-5) - Önerilen bir seçeneği kullan\n"
        
        question += "\nTercihiniz nedir?"
        
        # ✅ FRONTEND UYUMLU RESPONSE FORMATI
        return {
            "success": False,
            "sql": sql_query,
            "error": f"En yüksek benzerlik %{top_similarity*100:.1f} (eşik: %{self.similarity_threshold*100})",  # ✅ error eklendi
            "needs_clarification": True,
            "clarification_question": question,
            "suggestions": hybrid_suggestions["suggestions"],
            "natural_query": natural_query,
            "error_type": "low_similarity",
            "is_similarity_check": True,
            "has_hybrid_suggestions": len(hybrid_suggestions["suggestions"]) > 0,
            "attempts": 1,
            "top_similarity": top_similarity  # for debugging
        }

    def _get_hybrid_suggestions_from_results(self, hybrid_results: Dict) -> Dict:
        """Prepare hybrid search suggestions based on existing hybrid results."""
        try:
            top_results = hybrid_results.get("top_results", [])
            
            # Formatla
            suggestions = []
            
            for i, result in enumerate(top_results[:6]):  # Top 6 results
                table = result.get("table", "")
                column = result.get("column", "")
                score = result.get("combined_similarity", 0)
                source = result.get("source", "unknown")
                
                if table and column:
                    description = f"{source.capitalize()} eşleşme (%{int(score * 100)})"
                    suggestions.append({
                        "type": source,
                        "display": f"{table}.{column}",
                        "table": table,
                        "column": column,
                        "score": score,
                        "score_percent": int(score * 100),
                        "description": description
                    })
            
            print(f"🎯 Mevcut sonuçlardan öneriler hazır: {len(suggestions)} öneri")
            
            return {
                "suggestions": suggestions,
                "total_count": len(top_results)
            }
            
        except Exception as e:
            print(f"❌ Öneri hazırlama hatası: {e}")
            return {"suggestions": [], "total_count": 0}
                

    def _extract_tables_from_sql(self, sql: str) -> List[str]:
        """Extract table names from SQL"""
        import re
        tables = []
        # Find table names from FROM and JOIN clauses
        from_matches = re.findall(r'\bFROM\s+(\w+)', sql, re.IGNORECASE)
        join_matches = re.findall(r'\bJOIN\s+(\w+)', sql, re.IGNORECASE)
        tables.extend(from_matches)
        tables.extend(join_matches)
        return [t for t in tables if t]

    
    

    def _enhance_natural_query_with_context(self, natural_query: str) -> str:
        """Enrich the natural language query with context"""
        enhanced_query = natural_query
        
        # Check for reference words
        reference_words = ["bu", "şu", "önceki", "yukarıdaki", "aşağıdaki", "bunu", "şunu"]
        
        if any(word in natural_query.lower() for word in reference_words):
            # Get table info from the last successful query
            last_tables = self._get_last_used_tables()
            if last_tables:
                enhanced_query += f" [REFERANS: Önceki sorguda kullanılan tablolar: {', '.join(last_tables)}]"
        
        return enhanced_query

    def _get_last_used_tables(self) -> List[str]:
        """Return tables from the last successful queries"""
        tables = set()
        for msg in reversed(self.conversation_history):
            if msg["role"] == "assistant" and msg["type"] == "successful_sql":
                tables.update(self._extract_tables_from_sql(msg['content']))
            if len(tables) >= 3:  # At most 3 tables
                break
        return list(tables)
    
    def _get_recent_conversation_context(self, max_messages: int = 6) -> str:
        """Return recent conversations as context"""
        if not self.conversation_history:
            return ""
        
        context = "/* === ÖNCEKİ KONUŞMALAR === */\n"
        recent_messages = self.conversation_history[-max_messages:]
        
        for msg in recent_messages:
            if msg["role"] == "user":
                context += f"KULLANICI: {msg['content']}\n"
            elif msg["role"] == "assistant" and msg["type"] == "successful_sql":
                context += f"SQL: {msg['content']}\n"
            elif msg["role"] == "error":
                context += f"HATA: {msg['content']['message']}\n"
        
        context += "/* === YUKARIDAKİ KONUŞMALARI DİKKATE AL === */\n"
        return context

    def _get_hybrid_suggestions_for_user(self, natural_query: str) -> Dict:
        """
        Prepare hybrid search suggestions for the user.
        Return top 3 results from semantic and lexical sources.
        """
        try:
            print(f"🔍 Kullanıcı için hybrid search önerileri hazırlanıyor: '{natural_query}'")
            
            # Hybrid search yap
            hybrid_results = hybrid_search_with_separate_results(natural_query, top_k=MAX_INITIAL_RESULTS)
            top_results = hybrid_results.get("top_results", [])
            
            # Separate semantic and lexical results
            semantic_results = [r for r in top_results if r.get("source") == "semantic"]
            lexical_results = [r for r in top_results if r.get("source") == "lexical"]
            hybrid_results_list = [r for r in top_results if r.get("source") == "hybrid"]
            
            # Take top 3 semantic and top 3 lexical results
            top_semantic = sorted(semantic_results, key=lambda x: x.get("combined_similarity", 0), reverse=True)[:3]
            top_lexical = sorted(lexical_results, key=lambda x: x.get("combined_similarity", 0), reverse=True)[:3]
            top_hybrid = sorted(hybrid_results_list, key=lambda x: x.get("combined_similarity", 0), reverse=True)[:3]
            
            # Format
            suggestions = []
            
            # Semantic suggestions
            for i, result in enumerate(top_semantic):
                table = result.get("table", "")
                column = result.get("column", "")
                score = result.get("combined_similarity", 0)
                
                if table and column:
                    suggestions.append({
                        "type": "semantic",
                        "display": f"{table}.{column}",
                        "table": table,
                        "column": column,
                        "score": score,
                        "score_percent": int(score * 100),
                        "description": f"Semantic eşleşme (%{int(score * 100)})"
                    })
            
            # Lexical suggestions
            for i, result in enumerate(top_lexical):
                table = result.get("table", "")
                column = result.get("column", "")
                score = result.get("combined_similarity", 0)
                
                if table and column:
                    suggestions.append({
                        "type": "lexical", 
                        "display": f"{table}.{column}",
                        "table": table,
                        "column": column,
                        "score": score,
                        "score_percent": int(score * 100),
                        "description": f"Lexical eşleşme (%{int(score * 100)})"
                    })
            
            # Hybrid suggestions (optional)
            for i, result in enumerate(top_hybrid):
                if len(suggestions) >= 6:  # Maximum 6 suggestions
                    break
                table = result.get("table", "")
                column = result.get("column", "")
                score = result.get("combined_similarity", 0)
                
                if table and column:
                    suggestions.append({
                        "type": "hybrid",
                        "display": f"{table}.{column}",
                        "table": table,
                        "column": column,
                        "score": score,
                        "score_percent": int(score * 100),
                        "description": f"Hybrid eşleşme (%{int(score * 100)})"
                    })
            
            print(f"🎯 User suggestions ready: {len(suggestions)} suggestions")
            for suggestion in suggestions:
                print(f"   - {suggestion['display']} ({suggestion['description']})")
            
            return {
                "suggestions": suggestions,
                "semantic_count": len(top_semantic),
                "lexical_count": len(top_lexical),
                "hybrid_count": len(top_hybrid)
            }
            
        except Exception as e:
            print(f"❌ Hybrid search önerileri hazırlama hatası: {e}")
            return {"suggestions": [], "semantic_count": 0, "lexical_count": 0, "hybrid_count": 0}
    
    
    def _get_current_schema_pool(self, natural_query: str = "schema discovery") -> Dict:
        """
        Get current schema pool - CORRECTED real implementation
        """
        try:
            # If schema pool doesn't exist, construct via hybrid search
            if not self.current_schema_pool:
                print("🔍 Schema pool bulunamadı, yeniden oluşturuluyor...")
                fk_graph = load_fk_graph()
                
                # Do hybrid search - with required parameters
                hybrid_results = hybrid_search_with_separate_results(natural_query, top_k=MAX_INITIAL_RESULTS)
                
                # Prepare semantic results in correct format
                semantic_results = {
                    "schema": hybrid_results["top_results"],
                    "keywords": hybrid_results.get("keywords", []),
                    "values": hybrid_results.get("values", [])
                }
                
                # Perform column scoring
                top_columns = score_columns_by_relevance_separate(semantic_results, {}, top_n=20)
                
                # NEW: Use balanced table selection function
                selected_tables = select_top_tables_balanced(semantic_results, top_columns, target_count=15)
                
                # Build schema pool
                schema_pool, _, _ = build_compact_schema_pool(
                    semantic_results, selected_tables, fk_graph, top_columns=top_columns
                )
                
                self.current_schema_pool = schema_pool

                print(f"✅ Schema pool created: {len(schema_pool)} tables")
            
            return self.current_schema_pool
        
        except Exception as e:
            print(f"❌ Schema pool creation error: {e}")
            # Fallback: return empty schema pool
            return {}
    
    def _format_clarification_question(self, error_analysis: Dict) -> str:
        """Format the question to ask the user - FRONTEND COMPATIBLE"""
        if error_analysis["error_type"] == "timestamp_format_error":
            invalid_value = error_analysis["problematic_parts"][0] if error_analysis["problematic_parts"] else "bilinmeyen"
            suggestions = error_analysis["suggestions"]
            
            question = f"⚠️  '{invalid_value}' geçersiz tarih/zaman formatı.\n\n"
            question += "Lütfen bir seçenek belirleyin:\n"
            
            for i, suggestion in enumerate(suggestions, 1):
                # ✅ Use description for frontend compatibility
                if isinstance(suggestion, dict):
                    display_text = suggestion.get('description', str(suggestion))
                else:
                    display_text = str(suggestion)
                question += f"{i}. {display_text}\n"
            
            question += "\nLütfen bir numara seçin veya kendi tarih değerinizi yazın (örn: 2024-01-15):"
            return question
            
        elif error_analysis["error_type"] == "missing_table":
            table_name = error_analysis["problematic_parts"][0] if error_analysis["problematic_parts"] else "bilinmeyen"
            suggestions = error_analysis["suggestions"][:3]
            
            question = f"⚠️  '{table_name}' tablosu bulunamadı.\n\n"
            question += "Şunlardan birini mi kastettiniz?\n"
            
            for i, suggestion in enumerate(suggestions, 1):
                # ✅ Use suggested for frontend compatibility
                if isinstance(suggestion, dict):
                    table_name_display = suggestion.get('suggested', '')
                    confidence = suggestion.get('confidence', 0)
                    simple_name = unqualify_table(table_name_display)
                    question += f"{i}. {simple_name} ({confidence}% eşleşme)\n"
                else:
                    question += f"{i}. {suggestion}\n"
            
            question += "\nLütfen bir numara seçin veya doğru tablo adını yazın:"
            return question
        
        elif error_analysis["error_type"] == "missing_column":
            column_name = error_analysis["problematic_parts"][0] if error_analysis["problematic_parts"] else "bilinmeyen"
            suggestions = error_analysis["suggestions"][:3]
            
            question = f"⚠️  '{column_name}' sütunu bulunamadı.\n\n"
            question += "Şunlardan birini mi kastettiniz?\n"
            
            for i, suggestion in enumerate(suggestions, 1):
                # ✅ Use suggested and table for frontend compatibility
                if isinstance(suggestion, dict):
                    column_suggested = suggestion.get('suggested', '')
                    table_name = suggestion.get('table', '')
                    confidence = suggestion.get('confidence', 0)
                    table_simple = unqualify_table(table_name)
                    question += f"{i}. {column_suggested} ({confidence}% eşleşme, tablo: {table_simple})\n"
                else:
                    question += f"{i}. {suggestion}\n"
            
            question += "\nLütfen bir numara seçin veya doğru sütun adını yazın:"
            return question
            
        else:
            question = f"⚠️  SQL hatası: {error_analysis['message']}\n\nBu hatayı nasıl düzeltmek istersiniz?"
            return question
    
    
    def _parse_llm_response(self, response) -> str:
        """Parse LLM response"""
        text = ""
        try:
            if hasattr(response, '__dict__'):
                response_dict = response.__dict__
                if 'choices' in response_dict and response_dict['choices']:
                    choice = response_dict['choices'][0]
                    if hasattr(choice, '__dict__'):
                        choice_dict = choice.__dict__
                        if 'text' in choice_dict:
                            text = choice_dict['text']
                        elif 'message' in choice_dict and hasattr(choice_dict['message'], '__dict__'):
                            message_dict = choice_dict['message'].__dict__
                            if 'content' in message_dict:
                                text = message_dict['content']
                    else:
                        if isinstance(choice, dict):
                            if 'text' in choice:
                                text = choice['text']
                            elif 'message' in choice and isinstance(choice['message'], dict) and 'content' in choice['message']:
                                text = choice['message']['content']
            else:
                if isinstance(response, str):
                    text = response
                elif isinstance(response, dict):
                    for key in ['text', 'content', 'generated_text']:
                        if key in response:
                            text = response[key]
                            break
                    if not text and 'choices' in response and response['choices']:
                        choice = response['choices'][0]
                        if isinstance(choice, dict):
                            if 'text' in choice:
                                text = choice['text']
                            elif 'message' in choice and isinstance(choice['message'], dict) and 'content' in choice['message']:
                                text = choice['message']['content']
        except Exception as parse_error:
            print(f"⚠️ Response parsing failed: {parse_error}")
            text = str(response)
        
        return text.strip() if text else "SELECT 1"
    
    def generate_with_feedback(self, natural_query: str, user_feedback: Optional[Dict] = None) -> Dict:
        """
        Generate interactive SQL - CORRECTED: skip_similarity_check applies only to the next query
        """
        attempts = 0
        last_error = None
        current_sql = ""
        
        # Add user feedback to conversation history
        if user_feedback:
            self._add_to_conversation_history("user_feedback", user_feedback)
            print(f"🔄 Kullanıcı geri bildirimi alındı: {user_feedback}")
        
        # ✅ NEW: Check skip_similarity_check flag - only for this query
        skip_similarity_for_this_query = False
        if user_feedback and user_feedback.get('skip_similarity_check'):
            print("🚀 Skipping similarity check (skip_similarity_check=True) - ONLY FOR THIS QUERY")
            skip_similarity_for_this_query = True
        
        # If skip_similarity_check flag is present, skip similarity check - ONLY FOR THIS QUERY
        if skip_similarity_for_this_query:
            print("🚀 Skipping similarity check (skip_similarity_check=True)")
            # Continue generating SQL directly
            try:
                extended_context = self._get_extended_conversation_context()
                current_sql = self._generate_smart_sql_direct(natural_query, extended_context)
                
                # Try running the SQL
                columns, rows = run_sql(current_sql)
                
                self._add_to_conversation_history("assistant", current_sql, "successful_sql")
                self.last_successful_query = {
                    "sql": current_sql,
                    "natural_query": natural_query,
                    "timestamp": time.time()
                }
                
                return {
                    "success": True,
                    "sql": current_sql,
                    "columns": columns,
                    "rows": rows,
                    "needs_clarification": False,
                    "attempts": attempts + 1
                }
                
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Skip similarity check modunda hata: {error_msg}")
                return {
                    "success": False,
                    "sql": current_sql,
                    "error": error_msg,
                    "needs_clarification": False,
                    "attempts": attempts + 1
                }
        
        # ✅ NEW: Enrich the natural query with context
        enhanced_query = self._enhance_natural_query_with_context(natural_query)
        print(f"🎯 Geliştirilmiş sorgu: {enhanced_query}")
        
        # ✅ NEW: Add the enriched query to conversation history
        self._add_to_conversation_history("user", enhanced_query, "user_query")
        
        while attempts < self.max_retries:
            attempts += 1
            print(f"\n🔄 SQL Generation Attempt {attempts}/{self.max_retries}")
            
            try:
                # ✅ NEW: First perform hybrid search and similarity check
                print("🔍 Hybrid search yapılıyor...")
                hybrid_results = hybrid_search_with_separate_results(natural_query, top_k=MAX_INITIAL_RESULTS)
                
                # FIX: Similarity check - check number of tables above threshold
                above_threshold_count = hybrid_results.get("above_threshold_count", 0)
                similar_tables = hybrid_results.get("similar_tables", [])
                
                print(f"📊 Eşik üstü tablo sayısı: {above_threshold_count} (Eşik: {self.similarity_threshold})")
                
                # FIX: If no above-threshold tables and similar tables exist, show interactive table
                # ✅ NEW: Added skip_similarity_for_this_query check
                if above_threshold_count == 0 and similar_tables and not skip_similarity_for_this_query:
                    print(f"🎯 INTERAKTİF TABLO GÖSTERİLİYOR | Eşik üstü tablo yok, en iyi {len(similar_tables)} tablo gösteriliyor")
                    
                    # Format suggestions for interactive table
                    suggestions = []
                    for table, score in similar_tables[:8]:  # Show at most 8 tables
                        percent = int(score * 100)
                        suggestions.append({
                            "display": f"{table} (benzerlik: %{percent})",
                            "suggested": table,
                            "score": score,
                            "score_percent": percent,
                            "type": "interactive_table"
                        })
                    
                    # Get the highest similarity score
                    max_similarity = max([score for table, score in similar_tables]) if similar_tables else 0
                    
                    return {
                        "success": False,
                        "needs_clarification": True,
                        "clarification_question": f"Sorgunuzla eşleşen tablolar aşağıda listelenmiştir. Hangisini kastettiniz? (En yüksek benzerlik: %{int(max_similarity*100)})",
                        "suggestions": suggestions,
                        "error": f"Yüksek benzerlikli tablo bulunamadı. En iyi eşleşme: %{int(max_similarity*100)}",
                        "error_type": "low_similarity",
                        "similar_tables": similar_tables,
                        "has_hybrid_suggestions": False,
                        "attempts": attempts
                    }
                
                # If there are tables above threshold or skip_similarity_for_this_query is True, continue normal processing
                if skip_similarity_for_this_query:
                    print(f"✅ NORMAL PROCESSING | skip_similarity_check active, continuing to LLM")
                else:
                    print(f"✅ NORMAL PROCESSING | {above_threshold_count} tables above threshold, continuing to LLM")
                
                # ✅ Generate SQL with enhanced context
                extended_context = self._get_extended_conversation_context()
                print(f"📚 Context uzunluğu: {len(extended_context)} karakter")
                current_sql = self._generate_smart_sql_direct(enhanced_query, extended_context, hybrid_results=hybrid_results)
                
                # Try running the SQL
                print("🔍 Running SQL...")
                columns, rows = run_sql(current_sql)
                
                # ✅ Remember successful queries
                self._add_to_conversation_history("assistant", current_sql, "successful_sql")
                self.last_successful_query = {
                    "sql": current_sql,
                    "natural_query": natural_query,
                    "timestamp": time.time()
                }
                
                # Successful
                return {
                    "success": True,
                    "sql": current_sql,
                    "columns": columns,
                    "rows": rows,
                    "needs_clarification": False,
                    "attempts": attempts,
                    "similarity_score": hybrid_results.get("top_results", [{}])[0].get("combined_similarity", 0) if hybrid_results.get("top_results") else 0
                }
                
            except Exception as e:
                last_error = str(e)
                print(f"❌ Attempt {attempts} failed: {last_error}")
                
                # Handle the error interactively
                interactive_result = self._handle_error_interactively(
                    last_error, current_sql, natural_query, attempts
                )
                
                if interactive_result:
                    return interactive_result
                
                if attempts == self.max_retries:
                    return {
                        "success": False,
                        "sql": current_sql,
                        "error": last_error,
                        "needs_clarification": False,
                        "attempts": attempts
                    }
        
        return {
            "success": False,
            "sql": current_sql,
            "error": last_error or "Max retries exceeded",
            "needs_clarification": False,
            "attempts": attempts
        }

    def _generate_smart_sql_with_history(self, natural_query: str) -> str:
        """Generate SQL considering conversation history - UPDATED"""
        # ✅ NEW: Enhanced context (including FK-PK relationships)
        conversation_context = self._get_extended_conversation_context()  # _get_recent_conversation_context replacement
        
        full_context = f"{conversation_context}".strip()
        
        # ✅ NEW: Query enriched with context
        enhanced_query = self._enhance_natural_query_with_context(natural_query)
        
        return self._generate_smart_sql_direct(enhanced_query, full_context)
    
    
    def _suggest_automatic_fix_with_suggestions(self, error_analysis: Dict, 
                                          natural_query: str, sql_query: str,
                                          hybrid_suggestions: Dict) -> Dict:
        """
        Offer automatic fix options (with hybrid suggestions)
        """
        suggestions = hybrid_suggestions.get("suggestions", [])
        
        question = f"⚠️  {error_analysis['message']}\n\n"
        
        if suggestions:
            question += "🔍 **İlgili sütun önerileri:**\n"
            for i, suggestion in enumerate(suggestions[:3], 1):
                icon = "🧠" if suggestion["type"] == "semantic" else "🔤" if suggestion["type"] == "lexical" else "⚡"
                question += f"   {i}. {icon} {suggestion['display']} - {suggestion['description']}\n"
            question += "\n"
        
        question += "🛠️  **Otomatik düzeltme seçenekleri:**\n"
        question += "1. SQL'i yeniden oluştur (önerileri kullan)\n"
        question += "2. Sorguyu basitleştir\n"
        question += "3. Manuel düzeltme yap\n\n"
        question += "Lütfen bir numara seçin (1-3):"
        
        return {
            "success": False,
            "sql": sql_query,
            "error": error_analysis["message"],
            "needs_clarification": True,
            "clarification_question": question,
            "suggestions": suggestions,
            "natural_query": natural_query,
            "error_type": error_analysis["error_type"],
            "is_autofix_suggestion": True,
            "has_hybrid_suggestions": len(suggestions) > 0
        }

    
    def _handle_error_interactively(self, error_message: str, sql_query: str, 
                              natural_query: str, attempt: int) -> Optional[Dict]:
        """
        Ask the user about the error interactively and offer hybrid search suggestions
        """
        try:
            # Get current schema pool
            schema_pool = self._get_current_schema_pool()
            
            # Analyze the error
            error_analysis = self.error_analyzer.analyze_error(
                error_message, sql_query, schema_pool
            )
            
            # Add the error to conversation history
            self._add_to_conversation_history("error", error_analysis)
            
            print(f"🔍 Hata analizi tamamlandı: {error_analysis['error_type']}")
            
            # Get hybrid search suggestions
            hybrid_suggestions = self._get_hybrid_suggestions_for_user(natural_query)
            
            # Does user interaction required?
            if error_analysis["needs_clarification"] and attempt < self.max_retries:
                result = self._ask_user_for_clarification_with_suggestions(
                    error_analysis, natural_query, sql_query, hybrid_suggestions
                )
                result["attempts"] = attempt
                return result
            
            # Can automatic fix be attempted?
            elif attempt < self.max_retries:
                result = self._suggest_automatic_fix_with_suggestions(
                    error_analysis, natural_query, sql_query, hybrid_suggestions
                )
                result["attempts"] = attempt
                return result
                
        except Exception as e:
            print(f"⚠️ Hata işleme sırasında exception: {e}")
            import traceback
            traceback.print_exc()
        
        return None

    def _ask_user_for_clarification_with_suggestions(self, error_analysis: Dict, 
                                               natural_query: str, sql_query: str,
                                               hybrid_suggestions: Dict) -> Dict:
        """
        Kullanıcıya hata ve hybrid search önerileriyle birlikte sor
        """
        print("🎯 Starting user interaction (with hybrid suggestions)...")
        
        # Format the question to the user (with suggestions)
        question = self._format_clarification_question_with_suggestions(
            error_analysis, hybrid_suggestions
        )
        
        return {
            "success": False,
            "sql": sql_query,
            "error": error_analysis["message"],
            "needs_clarification": True,
            "clarification_question": question,
            "suggestions": hybrid_suggestions["suggestions"],
            "natural_query": natural_query,
            "error_type": error_analysis["error_type"],
            "has_hybrid_suggestions": len(hybrid_suggestions["suggestions"]) > 0
        }
    
    def _format_clarification_question_with_suggestions(self, error_analysis: Dict, 
                                                  hybrid_suggestions: Dict) -> str:
        """Ask the user with hybrid search suggestions"""
        
        suggestions = hybrid_suggestions.get("suggestions", [])
        
        # Base error message
        if error_analysis["error_type"] == "timestamp_format_error":
            invalid_value = error_analysis["problematic_parts"][0] if error_analysis["problematic_parts"] else "bilinmeyen"
            base_question = f"⚠️  '{invalid_value}' geçersiz tarih/zaman formatı.\n\n"
        elif error_analysis["error_type"] == "missing_table":
            table_name = error_analysis["problematic_parts"][0] if error_analysis["problematic_parts"] else "bilinmeyen"
            base_question = f"⚠️  '{table_name}' tablosu bulunamadı.\n\n"
        elif error_analysis["error_type"] == "missing_column":
            column_name = error_analysis["problematic_parts"][0] if error_analysis["problematic_parts"] else "bilinmeyen"
            base_question = f"⚠️  '{column_name}' sütunu bulunamadı.\n\n"
        else:
            base_question = f"⚠️  SQL hatası: {error_analysis['message']}\n\n"
        
        # Add suggestions
        if suggestions:
            base_question += "🔍 **Bunu mu demek istediniz?** (En iyi eşleşen sütunlar):\n\n"
            
            for i, suggestion in enumerate(suggestions, 1):
                icon = "🧠" if suggestion["type"] == "semantic" else "🔤" if suggestion["type"] == "lexical" else "⚡"
                base_question += f"{i}. {icon} **{suggestion['display']}** - {suggestion['description']}\n"
            
            base_question += "\n💡 **Seçenekler:**\n"
            base_question += "   • Bir öneri numarası seçin (1-6)\n"
            base_question += "   • Doğru tablo/sütun adını yazın\n"
            base_question += "   • 'tümünü göster' yazarak tüm veriyi isteyin\n"
            base_question += "   • Yeni bir sorgu yazın\n\n"
            base_question += "Lütfen seçiminizi yapın:"
        else:
            base_question += "ℹ️  İlgili sütun bulunamadı. Lütfen doğru tablo/sütun adını yazın veya yeni bir sorgu deneyin:"
        
        return base_question


    def _suggest_automatic_fix(self, error_analysis: Dict, 
                            natural_query: str, sql_query: str) -> Dict:
        """
        Otomatik düzeltme seçenekleri sun
        """
        fix_suggestions = []
        
        if error_analysis["error_type"] == "syntax_error":
            fix_suggestions = [
                {"type": "retry", "description": "SQL sözdizimini yeniden oluştur"},
                {"type": "simplify", "description": "Sorguyu basitleştir"}
            ]
        elif error_analysis["error_type"] in ["missing_table", "missing_column"]:
            fix_suggestions = [
                {"type": "expand_search", "description": "Daha geniş şema araması yap"},
                {"type": "alternative_tables", "description": "Alternatif tablolar dene"}
            ]
        else:
            fix_suggestions = [
                {"type": "retry", "description": "Yeniden dene"},
                {"type": "manual", "description": "Manuel SQL girme seçeneği"}
            ]
        
        question = f"⚠️  {error_analysis['message']}\n\nOtomatik düzeltme seçenekleri:\n"
        for i, suggestion in enumerate(fix_suggestions, 1):
            question += f"{i}. {suggestion['description']}\n"
        question += "\nBir numara seçin veya kendi düzeltmenizi yazın:"
        
        return {
            "success": False,
            "sql": sql_query,
            "error": error_analysis["message"],
            "needs_clarification": True,
            "clarification_question": question,
            "suggestions": fix_suggestions,
            "natural_query": natural_query,
            "error_type": error_analysis["error_type"],
            "is_autofix_suggestion": True
        }




def clean_meaningless_where_clauses(sql_text: str) -> tuple[str, list]:
    """Remove meaningless WHERE clauses like WHERE 1 = 1, WHERE TRUE, etc."""
    changes = []
    cleaned_sql = sql_text
    
    # Pattern 1: WHERE 1 = 1
    pattern1 = r'\s+WHERE\s+1\s*=\s*1\s*;'
    if re.search(pattern1, cleaned_sql, re.IGNORECASE):
        cleaned_sql = re.sub(pattern1, ';', cleaned_sql, flags=re.IGNORECASE)
        changes.append("Removed meaningless 'WHERE 1 = 1'")
    
    # Pattern 2: WHERE TRUE
    pattern2 = r'\s+WHERE\s+TRUE\s*;'
    if re.search(pattern2, cleaned_sql, re.IGNORECASE):
        cleaned_sql = re.sub(pattern2, ';', cleaned_sql, flags=re.IGNORECASE)
        changes.append("Removed meaningless 'WHERE TRUE'")
    
    # Pattern 3: WHERE 1=1 (multiline - before GROUP BY, ORDER BY, LIMIT, etc.)
    pattern3 = r'\s+WHERE\s+1\s*=\s*1\s*(?=\n|$|\s+GROUP\s+BY|\s+ORDER\s+BY|\s+LIMIT)'
    if re.search(pattern3, cleaned_sql, re.IGNORECASE):
        cleaned_sql = re.sub(pattern3, '', cleaned_sql, flags=re.IGNORECASE)
        changes.append("Removed meaningless 'WHERE 1 = 1' (before clause)")
    
    return cleaned_sql, changes


def auto_fix_sql_identifiers(sql_text, schema_pool, value_context=None, schema_prefix=None):
    """
    Geliştirilmiş auto-fix:
    - Schema prefix işlemesi düzeltildi
    - Tablo eşleştirme mantığı iyileştirildi
    - Hata yönetimi geliştirildi
    - Schema pool'dan dinamik sütun düzeltmesi
    """
    if schema_prefix is None:
        schema_prefix = settings.DB_SCHEMA
        
    changes = []
    issues = []
    fixed_sql = sql_text
    
    # Tüm sütunları schema_pool'dan topla
    all_columns_by_table = {}
    for table_name, columns in schema_pool.items():
        all_columns_by_table[table_name] = columns

    def strip_schema_prefix(name):
        if not name:
            return name
        # Strip the schema prefix, keep the table name
        pattern = fr'^{re.escape(schema_prefix)}\.'
        return re.sub(pattern, '', name, flags=re.IGNORECASE)

    def add_schema_prefix(name):
        if not name:
            return name
        if not name.lower().startswith(f"{schema_prefix}.") and name.strip():
            return f"{schema_prefix}.{name}"
        return name

    # Prepare schema keys both with and without prefix
    schema_keys = list(schema_pool.keys())
    schema_keys_lower = [k.lower() for k in schema_keys]
    
    # Prefixed ve unprefixed candidate'lar
    candidates = []
    for k in schema_keys:
        candidates.append(k)
        unprefixed = strip_schema_prefix(k)
        if unprefixed != k:
            candidates.append(unprefixed)

    def get_canonical_by_stripped(name):
        """Find canonical table name by stripped name"""
        if not name:
            return None
            
        stripped_target = strip_schema_prefix(name).lower()
        for k in schema_keys:
            if strip_schema_prefix(k).lower() == stripped_target:
                return k
        return None

    def find_best_table_match(table_name):
        """Find the best match for a table"""
        if not table_name or table_name.strip() == '':
            return None

        # 1. First search for exact match (original form)
        if table_name in schema_keys:
            return table_name
            
        # 2. Lowercase exact match
        table_lower = table_name.lower()
        if table_lower in schema_keys_lower:
            idx = schema_keys_lower.index(table_lower)
            return schema_keys[idx]
        
        # 3. Exact match for stripped form
        canonical = get_canonical_by_stripped(table_name)
        if canonical:
            return canonical

        # 4. Fuzzy match
        best_score = 0
        best_can = None
        stripped_input = strip_schema_prefix(table_name).lower()
        
        if not stripped_input:
            return None
            
        for k in schema_keys:
            stripped_k = strip_schema_prefix(k).lower()
            if not stripped_k:
                continue
                
            score = fuzz.ratio(stripped_input, stripped_k)
            if score > best_score and score >= 70:  # Threshold value lowered
                best_score = score
                best_can = k
        
        return best_can

    try:
        parsed = sqlparse.parse(sql_text)
        if not parsed:
            issues.append("SQL query could not be parsed.")
            return sql_text, changes, issues

        stmt = parsed[0]
        tokens = list(stmt.flatten())
        
        token_updates = {}
        table_aliases = {}
        from_tables_order = []

        # DEBUG: Log current schema pool
        print(f"🔍 Schema pool keys: {list(schema_pool.keys())}")
        print(f"🔍 SQL to fix: {sql_text}")

        # Step 1: FROM/JOIN clause parsing - IMPROVED
        i = 0
        while i < len(tokens):
            token = tokens[i]
            
            if token.ttype is sqlparse.tokens.Keyword and token.value.upper() in ('FROM', 'JOIN'):
                # Find the table name following the token
                j = i + 1
                # Whitespace'leri atla
                # Skip whitespaces
                while j < len(tokens) and tokens[j].ttype in (sqlparse.tokens.Whitespace, sqlparse.tokens.Newline):
                    j += 1
                
                if j < len(tokens) and tokens[j].ttype in (sqlparse.tokens.Name, sqlparse.tokens.String, sqlparse.tokens.Keyword):
                    table_token = tokens[j]
                    original_table_name = table_token.value
                    
                    # Correct the table name
                    best_table = find_best_table_match(original_table_name)
                    
                    if best_table:
                        # Use the canonical name from the schema pool
                        new_table_name = best_table  # Use canonical name as-is
                        
                        if new_table_name != original_table_name:
                            changes.append(f"Table '{original_table_name}' -> '{new_table_name}'")
                            token_updates[j] = new_table_name
                        
                        # Add to FROM order
                        if best_table not in from_tables_order:
                            from_tables_order.append(best_table)
                        
                        current_table = best_table
                        
                        # Alias handling
                        alias_start = j + 1
                        while (alias_start < len(tokens) and 
                               tokens[alias_start].ttype in (sqlparse.tokens.Whitespace, sqlparse.tokens.Newline)):
                            alias_start += 1
                        
                        if alias_start < len(tokens):
                            # Check for AS keyword
                            if (tokens[alias_start].ttype == sqlparse.tokens.Keyword and 
                                tokens[alias_start].value.upper() == 'AS'):
                                alias_start += 1
                                while (alias_start < len(tokens) and 
                                       tokens[alias_start].ttype in (sqlparse.tokens.Whitespace, sqlparse.tokens.Newline)):
                                    alias_start += 1
                            
                            # Alias name
                            if (alias_start < len(tokens) and 
                                tokens[alias_start].ttype in (sqlparse.tokens.Name, sqlparse.tokens.String)):
                                alias_name = tokens[alias_start].value
                                table_aliases[alias_name] = current_table
                                print(f"🔍 Alias detected: '{alias_name}' → '{current_table}'")
                    else:
                        issues.append(f"Table '{original_table_name}' not found in schema and no close match. Available: {list(schema_pool.keys())}")
            
            i += 1

        # Step 2: Column resolution - IMPROVED
        i = 0
        
        # Collect table names and aliases (SEPARATELY to avoid confusion)
        table_names_and_aliases = set()
        for table in from_tables_order:
            # Add both prefixed and unprefixed versions
            table_names_and_aliases.add(table.lower())
            table_names_and_aliases.add(strip_schema_prefix(table).lower())
        for alias in table_aliases.keys():
            table_names_and_aliases.add(alias.lower())

        while i < len(tokens):
            token = tokens[i]
            
            if token.ttype == sqlparse.tokens.Name:
                # Check context
                is_qualified = (i > 0 and tokens[i-1].value == '.')
                is_table_reference = (i + 1 < len(tokens) and tokens[i+1].value == '.')
                is_dot_after = (i + 1 < len(tokens) and tokens[i+1].value == '.')
                
                # Skip AS clause outputs (display names, not DB columns)
                is_as_output = False
                if i > 1 and tokens[i-1].ttype in (sqlparse.tokens.Whitespace, sqlparse.tokens.Newline):
                    j = i - 2
                    while j >= 0 and tokens[j].ttype in (sqlparse.tokens.Whitespace, sqlparse.tokens.Newline):
                        j -= 1
                    if j >= 0 and tokens[j].ttype == sqlparse.tokens.Keyword and tokens[j].value.upper() == 'AS':
                        is_as_output = True
                
                if is_as_output:
                    i += 1
                    continue
                
                # 🚨 FIX: Skip if it's a table reference (before dot) - DON'T treat as column
                if is_dot_after:
                    # This is a table/alias reference before a dot (e.g., "e_sayac" in "e_sayac.seri_no")
                    # Skip it - it's NOT a column name
                    i += 1
                    continue
                
                # Skip if it's a standalone table name or alias (not qualified, not before dot)
                if (not is_qualified and not is_dot_after and 
                    token.value.lower() in table_names_and_aliases):
                    i += 1
                    continue
                
                if is_qualified:
                    # Qualified column: table.column
                    table_index = i - 2
                    while table_index >= 0 and tokens[table_index].ttype in (sqlparse.tokens.Whitespace, sqlparse.tokens.Newline):
                        table_index -= 1
                    
                    if table_index >= 0 and tokens[table_index].ttype in (sqlparse.tokens.Name, sqlparse.tokens.String, sqlparse.tokens.Keyword):
                        table_ref = tokens[table_index].value
                        column_name = token.value
                        
                        # Resolve table alias
                        resolved_table = table_aliases.get(table_ref, table_ref)
                        
                        # Find canonical table
                        canonical_table = find_best_table_match(resolved_table)
                        if not canonical_table:
                            canonical_table = get_canonical_by_stripped(resolved_table)
                        
                        if canonical_table and canonical_table in schema_pool:
                            # Schema pool structure: {'columns': [...], 'column_details': {...}}
                            table_data = schema_pool[canonical_table]
                            cols = table_data.get('columns', []) if isinstance(table_data, dict) else table_data
                            
                            # Exact match first
                            exact_matches = [c for c in cols if c.lower() == column_name.lower()]
                            if exact_matches:
                                best_column = exact_matches[0]
                                if best_column != column_name:
                                    changes.append(f"Column '{column_name}' -> '{best_column}' in table '{canonical_table}'")
                                    token_updates[i] = best_column
                            else:
                                # Fuzzy match in current table
                                best_col, best_score = None, 0
                                for c in cols:
                                    s = fuzz.ratio(column_name.lower(), c.lower())
                                    if s > best_score:
                                        best_col, best_score = c, s
                                
                                # DEBUG: Her zaman göster
                                print(f"🔍 Column '{column_name}' in table '{canonical_table}': best_match='{best_col}' score={best_score}")
                                
                                if best_score >= 70 and best_col:  # Threshold lowered
                                    changes.append(f"Column '{column_name}' -> '{best_col}' in table '{canonical_table}' (score: {best_score})")
                                    token_updates[i] = best_col
                                else:
                                    # 🆕 LOW SCORE: Search for exact match in OTHER tables
                                    found_in_other_table = None
                                    for other_table, other_data in schema_pool.items():
                                        if other_table == canonical_table:
                                            continue  # Skip current table
                                        other_cols = other_data.get('columns', []) if isinstance(other_data, dict) else other_data
                                        if any(c.lower() == column_name.lower() for c in other_cols):
                                            found_in_other_table = other_table
                                            break
                                    
                                    if found_in_other_table:
                                        # CRITICAL FIX: Column exists in different table!
                                        print(f"🚨 CRITICAL: '{column_name}' NOT in '{canonical_table}' but FOUND in '{found_in_other_table}'!")
                                        changes.append(f"Table '{canonical_table}' -> '{found_in_other_table}' for column '{column_name}'")
                                        # Update the table reference (token before the dot)
                                        if table_index >= 0:
                                            token_updates[table_index] = found_in_other_table
                                    else:
                                        issues.append(f"Column '{column_name}' not found in table '{canonical_table}'. Available: {cols}")
                        else:
                            issues.append(f"Could not resolve table '{table_ref}' for qualified column '{table_ref}.{column_name}'. Available tables: {list(schema_pool.keys())}")
                
                elif not is_table_reference:
                    # Unqualified column name
                    column_name = token.value
                    
                    # Search across all tables (in FROM order)
                    candidate_tables = []
                    for table in from_tables_order:
                        if table in schema_pool:
                            table_data = schema_pool[table]
                            cols = table_data.get('columns', []) if isinstance(table_data, dict) else table_data
                            if any(c.lower() == column_name.lower() for c in cols):
                                candidate_tables.append(table)
                    
                    if candidate_tables:
                        # Use the first table from FROM order
                        best_table = candidate_tables[0]
                        table_data = schema_pool[best_table]
                        cols = table_data.get('columns', []) if isinstance(table_data, dict) else table_data
                        exact_match = next((c for c in cols if c.lower() == column_name.lower()), None)
                        if exact_match and exact_match != column_name:
                            changes.append(f"Unqualified column '{column_name}' -> '{exact_match}' (inferred table: '{best_table}')")
                            token_updates[i] = exact_match
                    else:
                        # Fuzzy search across entire schema pool
                        best_col, best_score, best_table = None, 0, None
                        for table, table_data in schema_pool.items():
                            cols = table_data.get('columns', []) if isinstance(table_data, dict) else table_data
                            for c in cols:
                                s = fuzz.ratio(column_name.lower(), c.lower())
                                if s > best_score:
                                    best_col, best_score, best_table = c, s, table
                        
                        if best_score >= 70 and best_col and best_table:  # Threshold lowered
                            changes.append(f"Unqualified column '{column_name}' -> '{best_col}' (inferred table: '{best_table}', score: {best_score})")
                            token_updates[i] = best_col
                        else:
                            issues.append(f"Could not resolve unqualified column '{column_name}'. Best match: {best_col} in {best_table} (score: {best_score})")
            
            i += 1

        # Apply token updates
        if token_updates:
            new_tokens = []
            for i, token in enumerate(tokens):
                if i in token_updates:
                    new_token = sqlparse.sql.Token(sqlparse.tokens.Name, token_updates[i])
                    new_tokens.append(new_token)
                else:
                    new_tokens.append(token)
            
            fixed_sql = ''.join(str(t) for t in new_tokens)
        
        # STEP 3: Type casting - add ::TEXT for VARCHAR columns in comparisons
        # Collect all VARCHAR columns (including alias resolution)
        varchar_columns = {}  # {table_name: [col1, col2, ...]}
        for table_name, table_data in schema_pool.items():
            if not isinstance(table_data, dict):
                continue
            column_details = table_data.get('column_details', {})
            varchar_cols = []
            for col_name, col_info in column_details.items():
                data_type = col_info.get('data_type', '').upper()
                if 'VARCHAR' in data_type or 'TEXT' in data_type or 'CHARACTER' in data_type:
                    varchar_cols.append(col_name)
            if varchar_cols:
                varchar_columns[table_name] = varchar_cols
        
        # Add ::TEXT to VARCHAR columns in = comparisons (with alias support)
        for table_name, cols in varchar_columns.items():
            stripped_table = strip_schema_prefix(table_name)
            # Find all aliases for this table
            table_refs = [stripped_table]
            for alias, aliased_table in table_aliases.items():
                if aliased_table == table_name:
                    table_refs.append(alias)
            
            for col_name in cols:
                for table_ref in table_refs:
                    # Pattern: table_ref.col_name = something (add ::TEXT after col_name)
                    pattern = rf'\b{re.escape(table_ref)}\.{re.escape(col_name)}\b(?!\s*::)'
                    if re.search(pattern, fixed_sql, re.IGNORECASE):
                        fixed_sql = re.sub(pattern, f'{table_ref}.{col_name}::TEXT', fixed_sql, flags=re.IGNORECASE)
                        changes.append(f"Type cast: {table_ref}.{col_name} → {table_ref}.{col_name}::TEXT")

    except Exception as e:
        issues.append(f"Error during auto-fix: {str(e)}")
        import traceback
        issues.append(f"Traceback: {traceback.format_exc()}")
        return sql_text, changes, issues

    return fixed_sql, changes, issues



def extract_all_tables_from_paths(paths: Dict[str, List[Dict]]) -> Set[str]:
    all_tables = set()
    for path in paths.values():
        if not isinstance(path, list):
            continue
        for hop in path:
            if not isinstance(hop, dict):
                continue
            for k in ('fk_table', 'pk_table', 'from', 'to', 'table'):
                v = hop.get(k)
                if v:
                    all_tables.add(v)
    return all_tables


# ================ SQL EXTRACTION =================
def extract_sql_from_response(text: str) -> str:
    """Extract SQL from an LLM response - safer and aggressive but careful.
    Priority: fenced code blocks first, then direct 'SELECT ... ;' capture.
    """
    text = text.strip()
    if not text:
        raise ValueError("❌ Boş metin verildi.")

    # 1) SQL inside a fenced code block (```sql ... ``` or ``` ... ``` containing SELECT)
    fenced_patterns = [
        r'```sql\s*(.*?)```',          # ```sql ... ```
        r'```\s*(SELECT[\s\S]*?)```',  # ``` SELECT ... ```
    ]
    for pat in fenced_patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            sql = m.group(1).strip()
            
            # ✅ FIX: Remove trailing ``` if LLM added it after ;
            sql = re.sub(r'\s*```\s*$', '', sql)
            
            # ✅ FIX: Remove **AÇIKLAMA:** or explanations after ;
            sql = re.sub(r';\s*(\*\*)?A[ÇC]IKLAMA(\*\*)?:.*$', ';', sql, flags=re.IGNORECASE | re.DOTALL)
            sql = re.sub(r';\s*--.*$', ';', sql, flags=re.MULTILINE)  # Remove inline comments after ;
            
            # If the block contains multiple statements, return the entire block.
            if not sql.endswith(';'):
                sql += ';'
            return sql.strip()

    # 2) If there's a clear 'SELECT ... ;' pattern in the text (multiline)
    m = re.search(r'(SELECT\b[\s\S]*?;)', text, re.IGNORECASE)
    if m:
        sql = m.group(1).strip()
        
        # ✅ FIX: Clean up explanations
        sql = re.sub(r';\s*(\*\*)?A[ÇC]IKLAMA(\*\*)?:.*$', ';', sql, flags=re.IGNORECASE | re.DOTALL)
        sql = re.sub(r';\s*```.*$', ';', sql, flags=re.DOTALL)
        
        return sql.strip()

    # 3) If SELECT exists but there's no semicolon, take from SELECT to the end
    idx = text.upper().find('SELECT')
    if idx != -1:
        sql = text[idx:].strip()
        
        # ✅ FIX: Stop at first ``` or explanation marker
        sql = re.split(r'```|\*\*A[ÇC]IKLAMA\*\*|A[ÇC]IKLAMA:', sql, flags=re.IGNORECASE)[0].strip()
        
        if not sql.endswith(';'):
            sql += ';'
        return sql.strip()

    # 4) If not found, raise an error
    raise ValueError(f"❌ SQL çıkarılamadı: {text[:200]}")



# ================ SQL EXECUTION =================
def run_sql(sql: str):
    """Execute SQL"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]  # type: ignore
        return columns, rows
    except Exception as e:
        raise ValueError(f"SQL çalıştırma hatası: {e}")
    finally:
        cur.close()
        conn.close()

def results_to_html(columns: List[str], rows: List[Tuple]) -> str:
    """Sonuçları modern HTML tabloya çevir"""
    if not rows:
        return '<div class="status-message status-info"><i class="fas fa-info-circle"></i> No results found.</div>'
    
    html = '<div class="table-container">'
    html += '<div class="sql-header"><strong><i class="fas fa-table"></i> Query Results:</strong>'
    html += f'<span> ({len(rows)} row{"s" if len(rows) != 1 else ""})</span></div>'
    html += '<table>'
    html += '<thead><tr>' + ''.join(f'<th>{c}</th>' for c in columns) + '</tr></thead>'
    html += '<tbody>'
    for row in rows:
        html += '<tr>' + ''.join(f'<td>{str(v) if v is not None else "NULL"}</td>' for v in row) + '</tr>'
    html += '</tbody></table></div>'
    return html










app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Get the directory of the current file
current_dir = os.path.dirname(os.path.abspath(__file__))
# chat.html is in the static folder
chat_html_path = os.path.join(current_dir, "static", "chat.html")

# ================ ROOT ENDPOINT =================
@app.get("/")
def read_root():
    """Root page - serves `chat.html`"""
    if os.path.exists(chat_html_path):
        return FileResponse(chat_html_path)
    else:
        # Helpful error message: show expected path so user can debug mount issues
        raise HTTPException(
            status_code=404,
            detail=f"chat.html not found at {chat_html_path}. Ensure ./chat.html exists on the host and is mounted into the container."
        )

# ================ UPDATED FASTAPI ENDPOINTS =================
class ChatRequest(BaseModel):
    question: str
    user_feedback: Optional[Dict] = None
    session_id: Optional[str] = None

# Global cache for session management - now also manages LLM instances
session_cache = {}

# WebSocket endpoint for streaming
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        question = data.get("question")
        session_id = data.get("session_id", "default")
        
        if session_id not in session_cache:
            session_cache[session_id] = InteractiveSQLGenerator()
        
        generator = session_cache[session_id]
        
        # Simulate streaming response
        result = generator.generate_with_feedback(question, None)
        
        if result["success"]:
            # Send explanation first
            await websocket.send_json({
                "type": "token",
                "content_type": "explanation",
                "content": "Sorgunuz başarıyla SQL'e dönüştürüldü. Aşağıda oluşturulan SQL sorgusunu ve sonuçları görebilirsiniz."
            })
            
            # Send SQL in chunks (simulate streaming)
            sql = result["sql"]
            chunk_size = 50
            for i in range(0, len(sql), chunk_size):
                await websocket.send_json({
                    "type": "token",
                    "content_type": "sql",
                    "content": sql[i:i+chunk_size]
                })
                await asyncio.sleep(0.1)  # Simulate processing time
            
            # ✅ Send table results
            html = results_to_html(result["columns"], result["rows"])
            await websocket.send_json({
                "type": "token", 
                "content_type": "results",
                "content": html
            })
            
            await websocket.send_json({"type": "done"})
        else:
            await websocket.send_json({
                "type": "token",
                "content_type": "explanation",
                "content": f"Hata oluştu: {result.get('error', 'Bilinmeyen hata')}"
            })
            await websocket.send_json({"type": "done"})
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "content": str(e)
        })

@app.post("/chat")
def chat(req: ChatRequest):
    try:
        session_id = req.session_id or "default"
        
        if session_id not in session_cache:
            session_cache[session_id] = InteractiveSQLGenerator()
        
        generator = session_cache[session_id]
        
        # Generate SQL
        result = generator.generate_with_feedback(req.question, req.user_feedback)
        
        attempts = result.get("attempts", 1)
        
        if result["success"]:
            html = results_to_html(result["columns"], result["rows"])
            return {
                "success": True,
                "sql": result["sql"],
                "html": html,
                "attempts": attempts,
                "session_id": session_id
            }
        else:
            if result.get("needs_clarification"):
                # ✅ Now return suggestions as-is
                return {
                    "success": False,
                    "error": result.get("error", ""),  # If missing, empty string
                    "needs_clarification": True,
                    "clarification_question": result.get("clarification_question", ""),
                    "suggestions": result.get("suggestions", []),  # Direct suggestions
                    "sql": result.get("sql", ""),
                    "attempts": attempts,
                    "session_id": session_id,
                    "error_type": result.get("error_type", "unknown"),
                    "has_hybrid_suggestions": result.get("has_hybrid_suggestions", False)
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", ""),
                    "attempts": attempts,
                    "session_id": session_id
                }
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

# Session cleanup endpoint
@app.delete("/session/{session_id}")
def clear_session(session_id: str):
    if session_id in session_cache:
        del session_cache[session_id]
    return {"success": True, "message": "Session cleared"}

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "Text2SQL API is running"}

# Endpoint to check whether chat.html exists
@app.get("/check-chat-html")
def check_chat_html():
    if os.path.exists(chat_html_path):
        return {"exists": True, "path": chat_html_path}
    else:
        return {"exists": False, "path": chat_html_path}
