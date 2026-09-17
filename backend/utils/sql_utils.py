"""
SQL utility functions.
"""
import re
from typing import List, Set, Tuple


def extract_table_names(sql: str) -> Set[str]:
    """
    Extract table names from SQL query.

    Args:
        sql: SQL query string

    Returns:
        Set of table names found in the query
    """
    # Remove comments to avoid false positives
    sql_no_comments = re.sub(r'/\\*.*?\\*/|--.*?$', '', sql, flags=re.MULTILINE | re.DOTALL)

    # Find table names after FROM, JOIN, etc.
    table_pattern = r'(?:FROM|JOIN|INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|FULL\s+JOIN)\s+[`"]?(\w+)[`"]?'
    matches = re.findall(table_pattern, sql_no_comments, re.IGNORECASE)

    return set(matches)


def extract_column_names(sql: str) -> Set[str]:
    """
    Extract column names from SQL query.

    Args:
        sql: SQL query string

    Returns:
        Set of column names found in the query
    """
    # This is a simplified implementation
    # A production version would use proper SQL parsing
    sql_upper = sql.upper()

    # Look for common patterns
    column_patterns = [
        r'SELECT\s+(.*?)\s+FROM',
        r'WHERE\s+(.*?)\s+(?:ORDER|GROUP|LIMIT|$)',
        r'ORDER\s+BY\s+(.*?)\s*(?:LIMIT|$)',
        r'GROUP\s+BY\s+(.*?)\s*(?:ORDER|LIMIT|$)'
    ]

    columns = set()
    for pattern in column_patterns:
        matches = re.findall(pattern, sql_upper, re.IGNORECASE | re.DOTALL)
        for match in matches:
            # Split by commas and clean up
            parts = re.split(r'\s*,\s*', match.strip())
            for part in parts:
                # Remove aliases, function calls, etc. (simplified)
                clean_part = re.sub(r'\s+AS\s+\w+.*$', '', part, flags=re.IGNORECASE)
                clean_part = re.sub(r'\w+\s*$$.*$$', '', clean_part)  # Remove function calls
                clean_part = clean_part.strip()
                if clean_part and not clean_part.startswith('('):
                    columns.add(clean_part)

    return columns


def sanitize_sql_comment(sql: str) -> str:
    """
    Remove or sanitize comments from SQL to prevent injection attempts.

    Args:
        sql: SQL query string

    Returns:
        SQL with comments removed
    """
    # Remove SQL comments
    sql_no_comments = re.sub(r'/\\*.*?\\*/|--.*?$', '', sql, flags=re.MULTILINE | re.DOTALL)
    return sql_no_comments.strip()


def build_select_query(
    table: str,
    columns: List[str] = None,
    where_clause: str = None,
    order_by: str = None,
    limit: int = None
) -> str:
    """
    Build a simple SELECT query.

    Args:
        table: Table name
        columns: List of column names (None for all)
        where_clause: WHERE clause (without 'WHERE')
        order_by: ORDER BY clause (without 'ORDER BY')
        limit: LIMIT value

    Returns:
        Formatted SELECT query
    """
    # Select clause
    if columns:
        select_clause = f"SELECT {', '.join(columns)}"
    else:
        select_clause = "SELECT *"

    # From clause
    from_clause = f"FROM {table}"

    # Build query
    query_parts = [select_clause, from_clause]

    if where_clause:
        query_parts.append(f"WHERE {where_clause}")

    if order_by:
        query_parts.append(f"ORDER BY {order_by}")

    if limit is not None:
        query_parts.append(f"LIMIT {limit}")

    return ' '.join(query_parts)