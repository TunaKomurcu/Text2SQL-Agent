"""
Data Values Search - Search actual data values in database
"""

from typing import List, Dict
from config import settings
from utils.qdrant import get_qdrant_client, normalize_qdrant_hit
from utils.models import get_semantic_model


def data_values_search(natural_query: str, top_k: int = 10) -> List[Dict]:
    """
    Data values search - from the data_samples collection in Qdrant.
    
    Args:
        natural_query: Natural language query
        top_k: Number of results to return
        
    Returns:
        list: Formatted search results with data value matches
    """
    print(f"📊 [DATA_VALUES] Query: '{natural_query}'")
    
    try:
        client = get_qdrant_client()
        semantic_model = get_semantic_model()
        
        # Query'yi semantic model ile encode et
        query_vector = semantic_model.encode([natural_query])[0].tolist()
        
        # Search the data_samples collection in Qdrant
        if hasattr(client, 'query_points'):
            results = client.query_points(
                collection_name=settings.QDRANT_DATA_SAMPLES_COLLECTION, 
                query=query_vector, 
                limit=top_k
            )
        elif hasattr(client, 'search'):
            results = client.search(
                collection_name=settings.QDRANT_DATA_SAMPLES_COLLECTION, 
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
