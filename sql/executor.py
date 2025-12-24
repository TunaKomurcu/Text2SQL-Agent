"""
SQL Executor - Run SQL queries and format results
"""

from typing import List, Tuple

from utils.db import get_connection


def run_sql(sql: str) -> Tuple[List[str], List[Tuple]]:
    """
    Run SQL query and return columns and rows.
    
    Args:
        sql: SQL query to execute
        
    Returns:
        tuple: (columns, rows) where columns is list of column names
               and rows is list of tuples
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return columns, rows
    finally:
        cursor.close()
        conn.close()


def results_to_html(columns: List[str], rows: List[Tuple]) -> str:
    """
    Sonuçları modern HTML tabloya çevir
    
    Args:
        columns: List of column names
        rows: List of result tuples
        
    Returns:
        str: HTML formatted table
    """
    if not rows:
        return '<div class="status-message status-info"><i class="fas fa-info-circle"></i> No results found.</div>'
    
    html = '<div class="table-container">'
    html += '<div class="sql-header"><strong><i class="fas fa-table"></i> Query Results:</strong>'
    html += f'<span> ({len(rows)} row{"s" if len(rows) != 1 else ""})</span></div>'
    html += '<table>'
    html += '<thead><tr>' + ''.join(f'<th>{c}</th>' for c in columns) + '</tr></thead>'
    html += '<tbody>'
    for row in rows:
        html += '<tr>' + ''.join(f'<td>{str(v) if v is not None else "NULL"}</td>' for v in row) + '</tr>'
    html += '</tbody></table></div>'
    return html
