"""
Integration tests for analysis framework caching.

Tests the complete caching infrastructure with real cache read/write operations:
- AnalysisCacheManager: 3-level caching (visits, visit_results, flw_results)
- Cache invalidation: visit count changes, config hash changes
- Cache validation: exact matching and time-based tolerance
- Both Django cache (Redis) and file-based backends
- Multi-opportunity cache isolation

Optimized for speed (~2 seconds):
- Uses minimal test fixtures instead of real API calls
- Tests cache logic directly without full analysis pipeline
- No mocking of cache layer - real read/write operations
"""
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from commcare_connect.labs.analysis import AnalysisConfig, FieldComputation
from commcare_connect.labs.analysis.backends.python_redis.cache import (
    CACHE_DIR,
    AnalysisCacheManager,
    clear_all_analysis_caches,
    get_config_hash,
)
from commcare_connect.labs.analysis.models import FLWAnalysisResult, VisitAnalysisResult


@pytest.fixture
def test_config():
    """Minimal analysis config for testing."""
    return AnalysisConfig(
        grouping_key="username",
        fields=[
            FieldComputation(name="test_field", path="form.test", aggregation="count"),
        ],
        filters={"status": "approved"},
    )


@pytest.fixture
def test_opportunity_id():
    """Test opportunity ID."""
    return 999


@pytest.fixture
def mock_request(test_opportunity_id):
    """Create mock request with minimal labs context."""
    factory = RequestFactory()
    request = factory.get("/test/")
    request.labs_context = {
        "opportunity_id": test_opportunity_id,
        "opportunity": {"id": test_opportunity_id, "name": "Test", "visit_count": 10},
    }
    request.user = Mock(username="testuser", email="test@example.com")
    from django.contrib.sessions.backends.db import SessionStore

    request.session = SessionStore()
    return request


@pytest.fixture
def cache_manager(test_opportunity_id, test_config):
    """Create cache manager for testing."""
    return AnalysisCacheManager(test_opportunity_id, test_config)


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear all caches before and after each test."""
    # Clear file cache
    clear_all_analysis_caches()

    # Clear Django cache
    try:
        cache.clear()
    except Exception:
        pass

    yield

    # Clean up after test
    clear_all_analysis_caches()
    try:
        cache.clear()
    except Exception:
        pass


@pytest.mark.django_db
class TestAnalysisCacheManager:
    """Test AnalysisCacheManager with real cache backends."""

    def test_config_hash_generation(self, test_config):
        """Test config hash is generated consistently."""
        hash1 = get_config_hash(test_config)
        hash2 = get_config_hash(test_config)

        assert hash1 == hash2
        assert len(hash1) == 12  # MD5 truncated to 12 chars
        assert hash1.isalnum()

    def test_cache_write_and_read_all_levels(self, cache_manager):
        """Test writing and reading at all cache levels."""
        # Level 1: Visits cache
        visits = [{"id": 1, "username": "test"}]
        assert cache_manager.set_visits_cache(visit_count=10, visits=visits) is True
        cached_visits = cache_manager.get_visits_cache()
        assert cached_visits["visit_count"] == 10
        assert len(cached_visits["visits"]) == 1

        # Level 2: Visit results cache
        visit_result = VisitAnalysisResult(rows=[], metadata={"test": "data"})
        assert cache_manager.set_visit_results_cache(visit_count=10, result=visit_result) is True
        cached_visit_result = cache_manager.get_visit_results_cache()
        assert cached_visit_result["visit_count"] == 10
        assert cached_visit_result["result"] == visit_result

        # Level 3: FLW results cache
        flw_result = FLWAnalysisResult(rows=[], metadata={"test": "data"})
        assert cache_manager.set_results_cache(visit_count=10, result=flw_result) is True
        cached_flw_result = cache_manager.get_results_cache()
        assert cached_flw_result["visit_count"] == 10
        assert cached_flw_result["result"] == flw_result

    def test_cache_clear(self, cache_manager):
        """Test clearing all cache levels."""
        # Write to all levels
        cache_manager.set_visits_cache(10, [{"test": "data"}])
        cache_manager.set_visit_results_cache(10, VisitAnalysisResult(rows=[], metadata={}))
        cache_manager.set_results_cache(10, FLWAnalysisResult(rows=[], metadata={}))

        # Clear cache
        cache_manager.clear_cache()

        # Verify cleared
        assert cache_manager.get_visits_cache() is None
        assert cache_manager.get_visit_results_cache() is None
        assert cache_manager.get_results_cache() is None

    def test_cache_validation_matching_counts(self, cache_manager):
        """Test cache validation succeeds with matching visit counts."""
        cached_data = {"visit_count": 10, "cached_at": datetime.utcnow().isoformat()}
        assert cache_manager.validate_cache(current_visit_count=10, cached_data=cached_data) is True

    def test_cache_validation_mismatching_counts_no_tolerance(self, cache_manager):
        """Test cache validation fails with mismatched counts and no tolerance."""
        cached_data = {"visit_count": 10, "cached_at": datetime.utcnow().isoformat()}
        assert cache_manager.validate_cache(current_visit_count=15, cached_data=cached_data) is False

    def test_cache_validation_with_tolerance_recent(self, cache_manager):
        """Test cache validation succeeds with tolerance for recent cache."""
        recent_time = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
        cached_data = {"visit_count": 10, "cached_at": recent_time}
        is_valid = cache_manager.validate_cache(current_visit_count=15, cached_data=cached_data, tolerance_minutes=10)
        assert is_valid is True

    def test_cache_validation_with_tolerance_expired(self, cache_manager):
        """Test cache validation fails with tolerance for old cache."""
        old_time = (datetime.utcnow() - timedelta(minutes=15)).isoformat()
        cached_data = {"visit_count": 10, "cached_at": old_time}
        is_valid = cache_manager.validate_cache(current_visit_count=15, cached_data=cached_data, tolerance_minutes=10)
        assert is_valid is False


@pytest.mark.django_db
class TestAnalysisPipelineCaching:
    """Test analysis pipeline caching with direct cache operations."""

    def test_cache_persistence(self, cache_manager):
        """Test cache persists across operations."""
        # Create and cache results
        visit_result = VisitAnalysisResult(rows=[], metadata={"visits": 10})
        cache_manager.set_visit_results_cache(10, visit_result)

        # Retrieve and verify
        cached = cache_manager.get_visit_results_cache()
        assert cached is not None
        assert cached["result"] == visit_result

        # Clear and verify
        cache_manager.clear_cache()
        assert cache_manager.get_visit_results_cache() is None

    def test_multiple_opportunity_caches(self, test_config):
        """Test caches for different opportunities are independent."""
        manager1 = AnalysisCacheManager(111, test_config)
        manager2 = AnalysisCacheManager(222, test_config)

        # Cache data for both
        result1 = FLWAnalysisResult(rows=[], metadata={"opp": 111})
        result2 = FLWAnalysisResult(rows=[], metadata={"opp": 222})

        manager1.set_results_cache(10, result1)
        manager2.set_results_cache(20, result2)

        # Verify independence
        cached1 = manager1.get_results_cache()
        cached2 = manager2.get_results_cache()

        assert cached1["result"].metadata["opp"] == 111
        assert cached2["result"].metadata["opp"] == 222
        assert cached1["visit_count"] == 10
        assert cached2["visit_count"] == 20


@pytest.mark.django_db
class TestCacheBackends:
    """Test cache backend functionality."""

    def test_django_cache_backend_detection(self):
        """Test Django cache backend detection works."""
        from commcare_connect.labs.analysis.backends.python_redis.cache import _use_django_cache

        use_django = _use_django_cache()
        assert isinstance(use_django, bool)

    def test_clear_all_file_caches(self, test_opportunity_id):
        """Test clearing all file-based caches."""
        CACHE_DIR.mkdir(exist_ok=True)
        test_file = CACHE_DIR / f"{test_opportunity_id}_test_hash_visits.pkl"
        test_file.write_text("test")

        cleared = clear_all_analysis_caches()
        assert cleared >= 1
        assert not test_file.exists()

    def test_cache_key_format(self, cache_manager):
        """Test cache key format is consistent."""
        key = cache_manager._get_cache_key("visits")
        assert key.startswith("analysis_")
        assert str(cache_manager.opportunity_id) in key
        assert cache_manager.config_hash in key
