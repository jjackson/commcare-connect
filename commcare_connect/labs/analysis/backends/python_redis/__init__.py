"""
Python/Redis backend for labs analysis.

Uses Redis (or file) caching with pandas-based computation.
"""

from commcare_connect.labs.analysis.backends.python_redis.backend import PythonRedisBackend

__all__ = ["PythonRedisBackend"]
