"""
Prompt Builder - Build prompts for LLM SQL generation
"""

import os
from .llm_manager import get_llm_instance, STATIC_PROMPT


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

    except Exception as e:
        print(f"⚠️ Priming error: {e}")
        # Continue even if priming fails
        print("⚠️ Continuing without cache...")

    # Mark so priming is not repeated
    setattr(llm_inst, "_static_prompt_primed", True)
    print("✅ Static prompt priming complete (in-memory cache).")


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


def generate_strict_prompt_dynamic_only(
    natural_query: str,
    schema_text: str,
    schema_pool: dict,
    value_context: dict,
    extended_context: str = ""
) -> str:
    """
    Generate dynamic prompt for LLM SQL generation - EXACT MATCH WITH ORIGINAL.
    
    Args:
        natural_query: Natural language query
        schema_text: Schema text from format_compact_schema_prompt_with_keywords
        schema_pool: Schema pool dictionary
        value_context: Value context dictionary
        extended_context: Extended conversation context (optional)
        
    Returns:
        str: Complete dynamic prompt
    """
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


    # ✅ EXACT MATCH WITH ORIGINAL - extended_context at the beginning
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
