"""
SQL Fixer - Automatic SQL identifier correction and cleaning
"""

import re
import sqlparse
from fuzzywuzzy import fuzz
from typing import Dict, Optional, Tuple, List

from config import settings


def clean_meaningless_where_clauses(sql_text: str) -> Tuple[str, List[str]]:
    """
    Remove meaningless WHERE clauses like WHERE 1 = 1, WHERE TRUE, etc.
    
    Args:
        sql_text: SQL query text
        
    Returns:
        tuple: (cleaned_sql, list of changes)
    """
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


def auto_fix_sql_identifiers(
    sql_text: str,
    schema_pool: Dict,
    value_context: Optional[Dict] = None,
    schema_prefix: Optional[str] = None
) -> Tuple[str, List[str], List[str]]:
    """
    Geliştirilmiş auto-fix:
    - Schema prefix işlemesi düzeltildi
    - Tablo eşleştirme mantığı iyileştirildi
    - Hata yönetimi geliştirildi
    - Schema pool'dan dinamik sütun düzeltmesi
    
    Args:
        sql_text: SQL query to fix
        schema_pool: Schema pool dictionary
        value_context: Optional value context
        schema_prefix: Optional schema prefix (defaults to settings.DB_SCHEMA)
        
    Returns:
        tuple: (fixed_sql, changes, issues)
    """
    if schema_prefix is None:
        schema_prefix = settings.DB_SCHEMA
        
    changes = []
    issues = []
    fixed_sql = sql_text
    
    # Tüm sütunları schema_pool'dan topla
    all_columns_by_table = {}
    for table_name, table_data in schema_pool.items():
        if isinstance(table_data, dict):
            all_columns_by_table[table_name] = table_data.get('columns', [])
        else:
            all_columns_by_table[table_name] = table_data

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

    def find_best_column_match(column_name, table_name):
        """Find best column match for a table"""
        if table_name not in all_columns_by_table:
            return None, 0
            
        columns = all_columns_by_table[table_name]
        if not columns:
            return None, 0
            
        col_lower = column_name.lower()
        
        # Exact match
        for col in columns:
            if col.lower() == col_lower:
                return col, 100
        
        # Fuzzy match
        best_score = 0
        best_col = None
        for col in columns:
            score = fuzz.ratio(col_lower, col.lower())
            if score > best_score:
                best_score = score
                best_col = col
        
        return best_col, best_score

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
        current_table = None
        
        while i < len(tokens):
            token = tokens[i]
            
            if token.ttype is sqlparse.tokens.Keyword and token.value.upper() in ('FROM', 'JOIN'):
                # Find the table name following the token
                j = i + 1
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
                    while (table_index >= 0 and 
                           tokens[table_index].ttype in (sqlparse.tokens.Whitespace, sqlparse.tokens.Newline)):
                        table_index -= 1
                    
                    if table_index >= 0:
                        table_ref = tokens[table_index].value
                        column_name = token.value
                        
                        # Resolve table (could be an alias)
                        resolved_table = table_aliases.get(table_ref)
                        if not resolved_table:
                            resolved_table = find_best_table_match(table_ref)
                        
                        if resolved_table:
                            # Find best column match
                            best_col, best_score = find_best_column_match(column_name, resolved_table)
                            
                            if best_col and best_score >= 80:
                                if best_col != column_name:
                                    changes.append(f"Column '{table_ref}.{column_name}' -> '{table_ref}.{best_col}'")
                                    token_updates[i] = best_col
                            else:
                                issues.append(f"Could not resolve qualified column '{table_ref}.{column_name}'. Best match: {best_col} (score: {best_score})")
                else:
                    # Unqualified column - try to match to a table
                    column_name = token.value
                    
                    # Try to find the column in FROM tables
                    best_table = None
                    best_col = None
                    best_score = 0
                    
                    for table in from_tables_order:
                        col, score = find_best_column_match(column_name, table)
                        if col and score > best_score:
                            best_score = score
                            best_col = col
                            best_table = table
                    
                    if best_col and best_score >= 80:
                        if best_col != column_name:
                            changes.append(f"Unqualified column '{column_name}' -> '{best_col}' (from {best_table})")
                            token_updates[i] = best_col
                    else:
                        if best_table:
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
