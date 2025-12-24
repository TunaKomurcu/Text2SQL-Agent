"""
Keyword Search - Schema keyword matching via Qdrant
"""

from typing import List, Dict
from config import settings
from utils.qdrant import get_qdrant_client, normalize_qdrant_hit
from utils.models import get_semantic_model


def keyword_search(natural_query: str, top_k: int = 10) -> List[Dict]:
    """
    Search keyword matches in the `schema_keywords` collection in Qdrant (vector-based).
    
    Args:
        natural_query: Natural language query
        top_k: Number of results to return
        
    Returns:
        list: Formatted search results with keyword matches
    """
    print(f"🔑 [KEYWORD] Query: '{natural_query}'")
    
    try:
        client = get_qdrant_client()
        semantic_model = get_semantic_model()
        
        # Encode query with semantic model
        query_vector = semantic_model.encode([natural_query])[0].tolist()
        
        # Search the `schema_keywords` collection in Qdrant
        if hasattr(client, 'query_points'):
            results = client.query_points(
                collection_name=settings.QDRANT_KEYWORDS_COLLECTION, 
                query=query_vector, 
                limit=top_k
            )
        elif hasattr(client, 'search'):
            results = client.search(
                collection_name=settings.QDRANT_KEYWORDS_COLLECTION, 
                query_vector=query_vector, 
                limit=top_k
            )
        else:
            raise RuntimeError('Qdrant client does not support search/query_points')
        
        # Extract points from QueryResponse
        if hasattr(results, 'points'):
            hits = results.points
        else:
            hits = results
        
        formatted_results = []
        for i, hit in enumerate(hits):
            payload, score = normalize_qdrant_hit(hit)
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
