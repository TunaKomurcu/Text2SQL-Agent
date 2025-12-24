"""
SQL Parser - Extract and parse SQL from LLM responses
"""

import re
from typing import Optional

from config import settings


def extract_sql_from_response(text: str) -> str:
    """
    Extract SQL from an LLM response - safer and aggressive but careful.
    Priority: fenced code blocks first, then direct 'SELECT ... ;' capture.
    
    Args:
        text: LLM response text
        
    Returns:
        str: Extracted SQL query
        
    Raises:
        ValueError: If no SQL found or empty text
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
            # We assume the first one is the main query.
            if sql.upper().startswith("SELECT"):
                return sql
    
    # 2) Direct SQL: SELECT ... ; (most common)
    m = re.search(r'(SELECT\s+[\s\S]+?;)', text, re.IGNORECASE | re.DOTALL)
    if m:
        sql = m.group(1).strip()
        
        # ✅ FIX: Remove explanations after ;
        sql = re.sub(r';\s*(\*\*)?A[ÇC]IKLAMA(\*\*)?:.*$', ';', sql, flags=re.IGNORECASE | re.DOTALL)
        sql = re.sub(r';\s*--.*$', ';', sql, flags=re.MULTILINE)
        
        return sql
    
    # 3) Fallback: just SELECT without semicolon (riskier, but acceptable)
    m = re.search(r'(SELECT\s+.+)', text, re.IGNORECASE | re.DOTALL)
    if m:
        sql = m.group(1).strip()
        # Stop at common break points
        for stop_word in ['**AÇIKLAMA', '**Explanation', 'Note:', 'Açıklama:', '\n\n---']:
            idx = sql.find(stop_word)
            if idx > 0:
                sql = sql[:idx].strip()
        return sql
    
    raise ValueError("❌ Metinde SQL kodu bulunamadı.")


def unqualify_table(name: Optional[str], default_schema: str = None) -> str:
    """
    Return the unqualified table name.
    Examples: 'schema.foo' -> 'foo'; 'any_schema.bar' -> 'bar'.
    Returns empty string when input is None or falsy.
    
    Args:
        name: Table name (potentially schema-qualified)
        default_schema: Default schema name
        
    Returns:
        str: Unqualified table name
    """
    if default_schema is None:
        default_schema = settings.DB_SCHEMA
    if not name:
        return ""
    nl = str(name).lower()
    if '.' in nl:
        return nl.split('.', 1)[1]
    return nl
