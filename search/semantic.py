"""
Semantic Search - Vector similarity search using BERT embeddings
"""

from config import settings
from utils.qdrant import get_qdrant_client, normalize_qdrant_hit
from utils.models import get_semantic_model


def semantic_search(query: str, top_k: int = 10):
    """
    Semantic similarity search against Qdrant schema embeddings.
    
    Args:
        query: Natural language query
        top_k: Number of results to return
        
    Returns:
        list: Formatted search results with table, column, similarity, type, rank
    """
    semantic_model = get_semantic_model()
    query_vector = semantic_model.encode([query])[0].tolist()
    
    client = get_qdrant_client()
    results = client.query_points(
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
        payload, score = normalize_qdrant_hit(hit)
        formatted_results.append({
            "table": payload.get("table_name", ""),
            "column": payload.get("column_name", ""),
            "similarity": float(score),
            "type": "semantic",
            "rank": i + 1
        })
    
    return formatted_results
