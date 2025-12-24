"""
Hybrid Search - Combines multiple search strategies
"""

from typing import List, Dict, Set, Tuple
from config import settings
from .semantic import semantic_search
from .lexical import lexical_search
from .keyword import keyword_search
from .data_values import data_values_search


def get_top_tables_from_search_results(search_results: List[Dict], search_type: str, top_k: int = 3) -> List[Tuple[str, float]]:
    """
    Extract the top-scoring tables from search results.
    
    Args:
        search_results: List of search results
        search_type: Type of search (for logging)
        top_k: Number of top tables to return
        
    Returns:
        list: List of (table_name, score) tuples
    """
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


def select_top_tables_balanced(semantic_results: dict, top_columns: list, target_count: int = 5) -> Set[str]:
    """
    Balanced table selection from different sources.
    
    Args:
        semantic_results: Results from semantic search
        top_columns: Top columns with sources
        target_count: Target number of tables
        
    Returns:
        set: Selected table names
    """
    print(f"\n🎯 NEW: Balanced table selection - Target: {target_count} tables")
    
    # Group tables by source
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


def hybrid_search_with_separate_results(natural_query: str, top_k: int = 15, similarity_threshold: float = None):
    """
    FIXED: Combines all search types with separate result tracking.
    
    Args:
        natural_query: User's natural language query
        top_k: Maximum number of results to return
        similarity_threshold: Minimum similarity score (uses config if None)
        
    Returns:
        dict: Combined results from all search types with detailed metrics
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

    print(f"🔍 [SEPARATE_SEARCH] Raw semantic results: {len(semantic_results)}")
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
    for result in semantic_results + lexical_results + keyword_results + data_values_results:
        table = result.get("table", "")
        similarity = result.get("similarity", 0)
        if table:
            # 🔥 BOOST: If table name exactly matches query, give max score
            schema_name = "example_schema_name."
            table_lower = table.lower().replace(schema_name, "")
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
    all_results_in_priority = top_data_values + top_keyword + top_semantic + top_lexical
    
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
    
    print(f"🧠 SEMANTIC (Top 3):")
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
    top_semantic_tables = []
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
        "all_semantic": semantic_results,
        "all_lexical": lexical_results,
        "all_keywords": keyword_results,
        "all_data_values": data_values_results,
        "schema": combined_results,
        "keywords": keyword_results,
        "values": data_values_results,
        "top_semantic_tables": top_semantic_tables,
        "top_lexical_tables": top_lexical_tables,
        "top_keyword_tables": top_keyword_tables,
        "top_data_values_tables": top_data_values_tables,
        "selected_tables": list(set([table for table, score in top_semantic_tables + top_lexical_tables + top_keyword_tables + top_data_values_tables])),
        "similar_tables": top_similar_tables,
        "similarity_threshold": similarity_threshold,
        "above_threshold_count": len(above_threshold_tables)
    }
