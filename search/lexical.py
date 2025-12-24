"""
Lexical Search - TF-IDF based character n-gram search
"""

import numpy as np
from config import settings
from utils.qdrant import get_qdrant_client, normalize_qdrant_hit


def lexical_search(query: str, top_k: int = 10):
    """
    Lexical similarity search using TF-IDF vectorizer.
    
    Args:
        query: Natural language query
        top_k: Number of results to return
        
    Returns:
        list: Formatted search results with table, column, similarity, type, rank
    """
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
        client = get_qdrant_client()
        results = client.query_points(
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
            p, score = normalize_qdrant_hit(hit)
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
