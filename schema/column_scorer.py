"""
Column Scorer - Score and rank columns by relevance
"""

from typing import List, Dict


def score_columns_by_relevance_separate(semantic_results: dict, value_context: dict, top_n: int = 10) -> list:
    """
    Score columns coming from separate groups (semantic, lexical, keyword, data_values).
    
    Args:
        semantic_results: Dictionary containing results from all search types
        value_context: Context about data values
        top_n: Number of top columns to return
        
    Returns:
        list: Top scored columns as tuples (table, column, similarity, type, extra_info)
    """
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
    
    # Return as list of dicts for builder compatibility
    formatted_columns = []
    for col_info in final_columns:
        formatted_columns.append({
            "table": col_info["table"],
            "column": col_info["column"],
            "similarity": col_info["similarity"],
            "type": col_info["type"],
            "keyword": col_info.get("keyword"),
            "value_text": col_info.get("value_text")
        })
    
    print(f"\n📊 FINAL TOP COLUMNS (SEPARATE GROUPS): {len(formatted_columns)} columns")
    for i, col in enumerate(formatted_columns, 1):
        icon = "🧠" if col["type"] == "semantic" else "🔤" if col["type"] == "lexical" else "🔑" if col["type"] == "keyword" else "📊"
        extra_info = ""
        if col.get("keyword"):
            extra_info = f" [keyword: '{col['keyword']}']"
        elif col.get("value_text"):
            extra_info = f" [value: '{col['value_text']}']"
        print(f"  {i:2d}. {col['table']}.{col['column']} (score={col['similarity']:.3f}, source={icon} {col['type']}{extra_info})")
    
    return formatted_columns
