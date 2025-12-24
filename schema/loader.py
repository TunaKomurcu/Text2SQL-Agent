"""
Schema Loader - Load FK graph and fetch table columns
"""

import os
import json
from typing import Dict
from functools import lru_cache
from utils.db import get_connection


# Cache for FK graph
_FK_GRAPH_CACHE = None


@lru_cache(maxsize=1)
def load_fk_graph(json_path: str = "fk_graph.json") -> Dict:
    """
    Load the FK (foreign-key) graph, preferring a local JSON at `json_path`.
    If the JSON file does not exist, attempt to read the latest entry from
    the Postgres `fk_graph_metadata` table. Raise an error only if neither
    source provides the graph. The result is cached for subsequent calls.
    
    Args:
        json_path: Path to FK graph JSON file
        
    Returns:
        dict: FK graph with edges and adjacency information
    """
    global _FK_GRAPH_CACHE
    if _FK_GRAPH_CACHE is not None:
        return _FK_GRAPH_CACHE

    print("\n" + "="*80)
    print("🔗 FK GRAPH YÜKLENİYOR")
    print("="*80)

    # 1) Local JSON preference
    try:
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                _FK_GRAPH_CACHE = json.load(f)
            print(f"✅ FK graph yüklendi ({json_path}): {len(_FK_GRAPH_CACHE.get('edges',[]))} edge, {len(_FK_GRAPH_CACHE.get('adjacency',{}))} tablo")
            return _FK_GRAPH_CACHE
    except Exception as e:
        print("⚠️ Lokal fk_graph.json okunurken hata:", e)

    # 2) Fallback: read from Postgres (legacy behavior)
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT graph_data FROM fk_graph_metadata ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()

        if not row:
            raise ValueError("❌ Postgres'te fk_graph_metadata bulunamadı ve lokal fk_graph.json yok. Önce build işlemini çalıştırın.")

        graph_data = row[0]
        _FK_GRAPH_CACHE = json.loads(graph_data) if isinstance(graph_data, str) else graph_data

        print(f"✅ FK graph yüklendi (Postgres): {len(_FK_GRAPH_CACHE.get('edges',[]))} edge, {len(_FK_GRAPH_CACHE.get('adjacency',{}))} tablo")
        return _FK_GRAPH_CACHE

    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass


def fetch_all_columns_for_table(conn, table_name, schema_name=None):
    """
    Return real table columns from information_schema.
    
    Args:
        conn: Database connection
        table_name: Table name to fetch columns for
        schema_name: Optional schema name
        
    Returns:
        list: [(column_name, data_type, description), ...]
    """
    cur = conn.cursor()
    try:
        if schema_name:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = %s
                ORDER BY ordinal_position
            """, (table_name, schema_name))
        else:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
        rows = cur.fetchall()
        # normalize to (name, type, desc)
        return [(r[0], r[1], f"nullable={r[2]}, default={r[3]}") for r in rows]
    finally:
        cur.close()
