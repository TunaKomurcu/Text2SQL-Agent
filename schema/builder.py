"""
Schema Builder - Build compact schema pool and format prompts
"""

from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict

from config import settings
from utils.db import get_connection
from .loader import fetch_all_columns_for_table
from .path_finder import find_minimal_connecting_paths, extract_all_tables_from_paths, _filter_maximal_paths


# Constants
DEFAULT_SCHEMA = settings.DB_SCHEMA
MAX_PATH_HOPS = settings.MAX_PATH_HOPS


def normalize_table_name(name: str) -> str:
    """Normalize table name by adding schema if missing"""
    if not name:
        return ""
    if "." not in name:
        return f"{DEFAULT_SCHEMA}.{name}"
    return name


def split_table_name(normalized_table: str) -> Tuple[str, str]:
    """Split table name into (schema, table)"""
    if '.' in normalized_table:
        parts = normalized_table.split('.', 1)
        return parts[0], parts[1]
    return DEFAULT_SCHEMA, normalized_table


def build_compact_schema_pool(
    semantic_results: Dict[str, List[Dict]],
    selected_tables: Set[str],
    fk_graph: Dict,
    top_columns: Optional[List] = None
) -> Tuple[Dict, Dict, Dict]:
    """
    Build compact schema pool with PK/FK prioritization.
    
    Args:
        semantic_results: Results from hybrid search (all_semantic, all_lexical, etc.)
        selected_tables: Set of selected table names
        fk_graph: FK graph dictionary
        top_columns: Optional list of top columns from scoring
        
    Returns:
        tuple: (schema_pool, paths, value_context)
    """
    print(f"\n{'='*80}")
    print(f"🏗️  NEW: COMPACT SCHEMA POOL BUILDER (PK/FK PRIORITIZED)")
    print(f"{'='*80}")

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
    fk_columns = {}  # (table, col) -> {table, column, ref_table, ref_column}
    
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
    
    print(f"✅ Detected {len(pk_columns)} PK columns")

    # 2. Extract FK columns from the FK graph edges
    edges = fk_graph.get('edges', []) if isinstance(fk_graph, dict) else []
    for edge in edges:
        from_table = normalize_table_name(edge.get('from', ''))
        fk_col = edge.get('fk_column', '')
        to_table = normalize_table_name(edge.get('to', ''))
        ref_col = edge.get('ref_column', '')
        
        # If FK table is in our selected tables, mark the column as FK
        if from_table in all_tables and fk_col:
            key = (from_table, fk_col)
            fk_columns[key] = {
                'table': from_table,
                'column': fk_col,
                'ref_table': to_table,
                'ref_column': ref_col
            }

    print(f"✅ Detected {len(fk_columns)} FK columns")

    # === AGGREGATE SIMILARITY SCORES ===
    print(f"🔍 Aggregating similarity scores...")
    column_scores = defaultdict(float)
    
    # Use top_columns if provided (new format: list of dicts)
    if top_columns:
        for col_dict in top_columns:
            table = normalize_table_name(col_dict.get("table", ""))
            column = col_dict.get("column", "")
            similarity = col_dict.get("similarity", 0)
            
            if table and column:
                key = (table, column)
                column_scores[key] = max(column_scores[key], similarity)
    else:
        # Fallback to semantic_results (old format)
        for result in (semantic_results.get("all_semantic", []) + 
                       semantic_results.get("all_lexical", []) + 
                       semantic_results.get("all_keywords", []) + 
                       semantic_results.get("all_data_values", [])):
            table = normalize_table_name(result.get("table", ""))
            column = result.get("column", "")
            similarity = result.get("similarity", 0)
            
            if table in all_tables and column:
                key = (table, column)
                # Keep highest score for each column
                column_scores[key] = max(column_scores[key], similarity)
    
    print(f"✅ Aggregated scores for {len(column_scores)} columns")

    # === BUILD SCHEMA POOL ===
    print(f"🔍 Building schema pool for {len(all_tables)} tables...")
    
    for table in all_tables:
        if not table:
            continue
            
        schema_name, table_name = split_table_name(table)
        
        # Fetch all columns for the table (returns list of tuples: [(name, type, desc), ...])
        all_cols_tuples = fetch_all_columns_for_table(conn, table_name, schema_name)
        
        # Categorize columns
        pk_columns_list = []
        fk_columns_list = []
        additional_columns = []
        
        for col_tuple in all_cols_tuples:
            # Unpack tuple: (column_name, data_type, description)
            col_name = col_tuple[0]
            col_type = col_tuple[1]
            col_desc = col_tuple[2]
            
            key = (table, col_name)
            
            # Check if PK
            is_pk = key in pk_columns
            
            # Check if FK
            is_fk = key in fk_columns
            fk_ref = fk_columns.get(key)
            
            # Create col_info dict
            col_info = {
                'column_name': col_name,
                'data_type': col_type,
                'description': col_desc,
                'is_pk': is_pk,
                'is_fk': is_fk
            }
            
            if fk_ref:
                col_info['fk_ref'] = fk_ref
            
            # Categorize
            if is_pk:
                pk_columns_list.append(col_info)
            elif is_fk:
                fk_columns_list.append(col_info)
            else:
                # Get similarity score
                score = column_scores.get(key, 0)
                col_info['similarity_score'] = score
                additional_columns.append(col_info)
        
        # Sort additional columns by similarity score (descending)
        additional_columns.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
        
        # Take top N additional columns (configurable)
        max_additional = 10  # Configurable
        additional_columns = additional_columns[:max_additional]
        
        # Combine: PK first, then FK, then top similar columns
        final_columns = pk_columns_list + fk_columns_list + additional_columns
        
        # Build schema pool entry
        schema_pool[table] = {
            'columns': [col['column_name'] for col in final_columns],
            'column_details': {}
        }
        
        # Store detailed column information
        for col_info in final_columns:
            col_name = col_info['column_name']
            schema_pool[table]['column_details'][col_name] = {
                'data_type': col_info['data_type'],
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
    print(f"🔍 [VALUE_CONTEXT_DEBUG] semantic_results.get('values'): {len(semantic_results.get('values', []))} items")
    for v in semantic_results.get("values", []) or []:
        t = normalize_table_name(v.get('table', ''))
        c = v.get('column', '')
        value_text = v.get('value_text', '')
        
        # ✅ FIX: Add to context even if value_text is empty (so model knows which columns have data)
        if t and c:
            if f"{t}.{c}" not in value_context:
                if value_text:  # Only add if there's actual text
                    value_context.setdefault(f"{t}.{c}", []).append(value_text)
    
    print(f"🔍 [VALUE_CONTEXT_DEBUG] Final value_context keys: {list(value_context.keys())}")

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
    
    Args:
        schema_pool: Schema pool dictionary
        paths: FK paths dictionary
        fk_graph: FK graph dictionary
        top_columns: Top columns list
        natural_query: Natural language query
        
    Returns:
        str: Formatted schema prompt
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
                ref_table = fk_ref.get('ref_table', '?')
                ref_column = fk_ref.get('ref_column', '?')
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
        
        # Debug: Show schema_pool tables
        print(f"🔍 [FK_PATH_FILTER] Schema pool tables: {list(schema_pool.keys())}")
        
        printed_chains = set()
        skipped_paths = 0
        
        for path_key, hops in sorted(filtered_paths.items()):
            if not hops:
                continue
            
            # First pass: Check if ALL tables in this path exist in schema_pool
            all_tables_in_path_exist = True
            tables_in_path = set()
            
            for hop in hops:
                fk_table = hop.get('fk_table') or hop.get('from')
                pk_table = hop.get('pk_table') or hop.get('to')
                
                if fk_table:
                    tables_in_path.add(fk_table)
                if pk_table:
                    tables_in_path.add(pk_table)
                
                # Check if both tables exist in schema_pool
                if fk_table and fk_table not in schema_pool:
                    all_tables_in_path_exist = False
                    print(f"🔍 [FK_PATH_FILTER] Skipping path: {fk_table} not in schema_pool")
                    break
                if pk_table and pk_table not in schema_pool:
                    all_tables_in_path_exist = False
                    print(f"🔍 [FK_PATH_FILTER] Skipping path: {pk_table} not in schema_pool")
                    break
            
            # Skip this entire path if any table is missing
            if not all_tables_in_path_exist:
                skipped_paths += 1
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
                fk_details = schema_pool[fk_table].get('column_details', {}).get(fk_col, {})
                fk_type = fk_details.get('data_type', 'UNKNOWN')
                
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
        
        print(f"🔍 [FK_PATH_FILTER] Skipped {skipped_paths} paths with missing tables")
        print(f"🔍 [FK_PATH_FILTER] Included {len(printed_chains)} paths")
    
    # If no paths found, show all FK relationships from schema_pool with types
    if not paths or not any(filtered_paths.values() if paths else []):
        prompt_parts.append("• (FK ilişkileri yukarıda her sütunun yanında gösterilmiştir)")
        prompt_parts.append("")
        
        # Collect all FK relationships from schema_pool with type info
        # ✅ CRITICAL: Only show FK relationships where BOTH tables are in schema_pool
        fk_relationships = []
        for table, info in schema_pool.items():
            column_details = info.get('column_details', {})
            for col_name, details in column_details.items():
                if details.get('is_fk') and details.get('fk_ref'):
                    fk_ref = details['fk_ref']
                    
                    # Get types
                    fk_type = details.get('data_type', 'UNKNOWN')
                    pk_type = 'UNKNOWN'
                    ref_table = fk_ref['ref_table']
                    ref_col = fk_ref['ref_column']
                    
                    # ✅ Skip if ref_table is not in schema_pool
                    if ref_table not in schema_pool:
                        continue
                    
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
