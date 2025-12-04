"""
Analysis backends.

Each backend provides a different approach to caching and computation:
- python_redis: Redis/file caching with pandas computation (default)
- sql: PostgreSQL table caching with SQL computation
"""
