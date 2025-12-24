"""
Database Connection Management
"""

import psycopg2
from config import get_db_conn_kwargs


def get_connection():
    """
    Create and return a new PostgreSQL connection using config settings.
    
    Returns:
        psycopg2.connection: PostgreSQL connection object
    """
    kwargs = get_db_conn_kwargs()
    return psycopg2.connect(**kwargs)
