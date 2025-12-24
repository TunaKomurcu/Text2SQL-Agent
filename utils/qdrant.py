"""
Qdrant Client Management and Utilities
"""

from config import create_qdrant_client


# Singleton Qdrant client
_QDRANT_CLIENT = None


def get_qdrant_client():
    """
    Get or create Qdrant client (singleton pattern).
    
    Returns:
        QdrantClient: Qdrant client instance
    """
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is None:
        _QDRANT_CLIENT = create_qdrant_client()
    return _QDRANT_CLIENT


def normalize_qdrant_hit(hit):
    """
    Normalize Qdrant hit to extract payload and score.
    
    Accepts different return shapes from qdrant-client (object with .payload/.score,
    or tuple/list like (id, score, payload) or similar).
    
    Args:
        hit: Qdrant search result (various formats)
        
    Returns:
        tuple: (payload_dict, score_float)
    """
    payload = {}
    score = None

    # tuple/list style: try to find dict and numeric score
    if isinstance(hit, (list, tuple)):
        for el in hit:
            if isinstance(el, dict):
                payload = el
            elif isinstance(el, (float, int)) and score is None:
                score = float(el)
        return payload or {}, score or 0.0

    # object style (PointStruct / QueryResult)
    if hasattr(hit, 'payload'):
        payload = getattr(hit, 'payload') or {}
    elif isinstance(hit, dict) and 'payload' in hit:
        payload = hit.get('payload') or {}

    if hasattr(hit, 'score') and getattr(hit, 'score') is not None:
        try:
            score = float(getattr(hit, 'score'))
        except Exception:
            score = None

    # fallback: try common dict keys
    if score is None and isinstance(hit, dict):
        for key in ('score', 'distance'):
            if key in hit:
                try:
                    score = float(hit[key])
                    break
                except Exception:
                    pass

    return payload or {}, score or 0.0
