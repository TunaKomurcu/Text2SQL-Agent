"""
Path Finder - Find minimal connecting paths between tables using FK graph
"""

from typing import Dict, List, Set
from collections import defaultdict
from config import settings


# Constants
MAX_PATH_HOPS = settings.MAX_PATH_HOPS


def find_minimal_connecting_paths(
    fk_graph: Dict,
    selected_tables: Set[str],
    max_hops: int = MAX_PATH_HOPS
) -> Dict[str, List[Dict]]:
    """
    Produce directed edge chains: e1.from->e1.to, then e2 where e2.from == e1.to, ...
    Each hop contains: {'from','to','fk_table','fk_column','pk_table','pk_column','direction'}
    Returns a dict mapping keys like "start-end-idx" to lists of hops.

    Note: Only return chains whose start AND end tables are both within selected_tables.
    
    Args:
        fk_graph: FK graph dictionary with edges
        selected_tables: Set of selected table names
        max_hops: Maximum number of hops in a path
        
    Returns:
        dict: Mapping of path keys to hop lists
    """
    edges = fk_graph.get('edges', []) if isinstance(fk_graph, dict) else []
    cleaned = []
    for e in edges:
        a = e.get('from'); b = e.get('to')
        if not a or not b:
            continue
        cleaned.append({
            'from': a,
            'to': b,
            'fk_column': e.get('fk_column'),
            'ref_column': e.get('ref_column'),
            'raw': e
        })

    by_from = defaultdict(list)
    for e in cleaned:
        by_from[e['from']].append(e)

    results = {}
    seen_chains = set()
    idx = 0

    def dfs(path):
        nonlocal idx
        last = path[-1]
        # candidate chain key for dedupe
        key_text = "||".join(f"{h['from']}->{h['to']}:{h.get('fk_column') or ''}->{h.get('ref_column') or ''}" for h in path)
        if key_text in seen_chains:
            return
        seen_chains.add(key_text)

        # keep only chains up to max_hops (edges count)
        if 1 <= len(path) <= max_hops:
            # check endpoints: both endpoints must be in selected_tables (either order)
            first = path[0]
            last_h = path[-1]
            endpoints = {first['from'], last_h['to']}
            # require both endpoints to be in selected_tables
            if endpoints.issubset(selected_tables):
                key = f"{first['from']}-{last_h['to']}-{idx}"
                hop_list = []
                for h in path:
                    hop_list.append({
                        'from': h['from'],
                        'to': h['to'],
                        'fk_table': h['from'],
                        'fk_column': h.get('fk_column'),
                        'pk_table': h['to'],
                        'pk_column': h.get('ref_column'),
                        'direction': 'forward'
                    })
                results[key] = hop_list
                idx += 1

        # if length == max_hops, stop extending
        if len(path) >= max_hops:
            return

        # extend: find edges starting from current 'to'
        next_edges = by_from.get(last['to'], [])
        for ne in next_edges:
            # avoid trivial cycles by repeating the same table sequence
            tables_in_path = [p['from'] for p in path] + [p['to'] for p in path]
            if ne['to'] in tables_in_path and ne['from'] in tables_in_path:
                continue
            dfs(path + [ne])

    # Start DFS from every edge
    for e in cleaned:
        dfs([e])

    return results


def _filter_maximal_paths(paths: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """
    Remove paths that are subpaths of other (longer) paths.
    If a path is an exact contiguous subsequence of a longer path, it is removed.
    
    Args:
        paths: Dictionary of path keys to hop lists
        
    Returns:
        dict: Filtered paths containing only maximal paths
    """
    if not paths:
        return {}
    
    # First sort all paths by length (longer ones first)
    sorted_paths = sorted(paths.items(), key=lambda x: len(x[1]), reverse=True)
    
    # Build string representations for each path
    path_strings = {}
    for key, hops in sorted_paths:
        if not isinstance(hops, list) or not hops:
            continue
            
        # Represent the path as a string (including table and column info)
        path_parts = []
        for hop in hops:
            fk_table = hop.get('fk_table') or hop.get('from', '')
            fk_col = hop.get('fk_column', '')
            pk_table = hop.get('pk_table') or hop.get('to', '')
            pk_col = hop.get('pk_column') or hop.get('ref_column', '')
            
            if fk_table and pk_table:
                hop_str = f"{fk_table}.{fk_col}->{pk_table}.{pk_col}"
                path_parts.append(hop_str)
        
        if path_parts:
            path_strings[key] = "|".join(path_parts)
    
    # Find and remove subpaths
    maximal_keys = set(path_strings.keys())
    all_keys = list(path_strings.keys())
    
    for i in range(len(all_keys)):
        key_i = all_keys[i]
        path_i = path_strings[key_i]
        
        for j in range(len(all_keys)):
            if i == j:
                continue
                
            key_j = all_keys[j]
            path_j = path_strings[key_j]
            
            # If path_j is a contiguous subsequence of path_i, remove it
            if path_j in path_i:
                # If it's shorter and not identical, remove it
                if path_j != path_i and len(path_j) < len(path_i):
                    if key_j in maximal_keys:
                        maximal_keys.remove(key_j)
    
    # Also dedupe identical paths (keep only one of identical strings)
    unique_paths = {}
    for key in maximal_keys:
        path_str = path_strings[key]
        if path_str not in unique_paths.values():
            unique_paths[key] = path_str
        else:
            # If another key has the same path string, discard this duplicate key
            maximal_keys.discard(key)
    
    # Return the original paths
    return {k: paths[k] for k in maximal_keys if k in paths}


def extract_all_tables_from_paths(paths: Dict[str, List[Dict]]) -> Set[str]:
    """
    Extract all unique table names from paths.
    
    Args:
        paths: Dictionary of path keys to hop lists
        
    Returns:
        set: Set of all table names found in paths
    """
    all_tables = set()
    for path in paths.values():
        if not isinstance(path, list):
            continue
        for hop in path:
            if not isinstance(hop, dict):
                continue
            for k in ('fk_table', 'pk_table', 'from', 'to', 'table'):
                v = hop.get(k)
                if v:
                    all_tables.add(v)
    return all_tables
