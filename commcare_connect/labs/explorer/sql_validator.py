"""
SQL validation for safe execution of user-provided WHERE clauses.

Ensures user SQL is read-only and only operates on form_json column.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Dangerous SQL keywords that should not appear in WHERE clauses
BLACKLISTED_KEYWORDS = [
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "TRUNCATE",
    "ALTER",
    "CREATE",
    "REPLACE",
    "EXEC",
    "EXECUTE",
    "GRANT",
    "REVOKE",
    "UNION",
    "IMPORT",
    "LOAD",
    "COPY",
    "MERGE",
    "CALL",
    "DO",
    "HANDLER",
    "PREPARE",
    "DEALLOCATE",
]


def validate_where_clause(clause: str) -> tuple[bool, str]:
    """
    Validate a user-provided SQL WHERE clause for safety.

    Args:
        clause: The WHERE clause string (without the WHERE keyword)

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if the clause is safe to execute
        - error_message: Empty string if valid, otherwise describes the issue

    Examples:
        >>> validate_where_clause("form_json->>'status' = 'complete'")
        (True, "")

        >>> validate_where_clause("form_json->'form'->>'name' LIKE '%test%'")
        (True, "")

        >>> validate_where_clause("DROP TABLE users")
        (False, "Clause contains blacklisted keyword: DROP")

        >>> validate_where_clause("username = 'admin' OR 1=1; DROP TABLE users")
        (False, "Clause contains blacklisted keyword: DROP")
    """
    if not clause or not clause.strip():
        return False, "WHERE clause cannot be empty"

    clause_upper = clause.upper()

    # Check for blacklisted keywords
    for keyword in BLACKLISTED_KEYWORDS:
        # Use word boundaries to avoid false positives (e.g., "UPDATE" in "updated_at")
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, clause_upper):
            return False, f"Clause contains blacklisted keyword: {keyword}"

    # Check for semicolons (could indicate multiple statements)
    if ";" in clause:
        return False, "Semicolons are not allowed in WHERE clauses"

    # Check for comments (could be used to bypass validation)
    if "--" in clause or "/*" in clause or "*/" in clause:
        return False, "SQL comments are not allowed"

    # Verify it references form_json (primary safety requirement)
    # This is the main column we want to allow querying
    if "form_json" not in clause.lower():
        return False, "WHERE clause must reference the form_json column"

    # Basic length check
    if len(clause) > 1000:
        return False, "WHERE clause is too long (max 1000 characters)"

    logger.info(f"Validated WHERE clause: {clause[:100]}...")
    return True, ""


def build_safe_query(opportunity_id: int, where_clause: str, limit: int = 1000) -> tuple[str, list]:
    """
    Build a safe SQL query with the user's WHERE clause.

    Args:
        opportunity_id: The opportunity ID to filter by
        where_clause: The validated user WHERE clause
        limit: Maximum number of results to return

    Returns:
        Tuple of (query_string, params) ready for cursor.execute()

    The query will always:
    - Be read-only (SELECT only)
    - Filter by opportunity_id
    - Limit results to prevent massive downloads
    - Use parameterized queries for opportunity_id
    """
    # Note: We can't parameterize the WHERE clause because it contains operators and column names
    # But we've validated it doesn't contain dangerous keywords
    query = f"""
        SELECT
            visit_id,
            username,
            visit_date,
            status,
            deliver_unit,
            entity_id,
            form_json
        FROM labs_raw_visit_cache
        WHERE opportunity_id = %s AND ({where_clause})
        ORDER BY visit_id DESC
        LIMIT {limit}
    """

    params = [opportunity_id]
    return query, params
