from commcare_connect.labs.analysis.backends.sql.query_builder import _aggregation_to_sql


class TestAggregationToSQL:
    def test_count_distinct(self):
        result = _aggregation_to_sql("count_distinct", "beneficiary_case_id", "total_cases")
        assert "COUNT(DISTINCT" in result
        assert "beneficiary_case_id" in result

    def test_count_unique_alias(self):
        """count_unique should behave like count_distinct."""
        result = _aggregation_to_sql("count_unique", "case_id", "cases")
        assert "COUNT(DISTINCT" in result

    def test_last_uses_desc_subquery(self):
        result = _aggregation_to_sql("last", "weight", "last_weight")
        assert "ORDER BY visit_date DESC" in result
        assert "LIMIT 1" in result

    def test_count(self):
        result = _aggregation_to_sql("count", "visit_id", "total_visits")
        assert result == "COUNT(visit_id)"

    def test_first_uses_asc_subquery(self):
        result = _aggregation_to_sql("first", "weight", "first_weight")
        assert "ORDER BY visit_date ASC" in result
        assert "LIMIT 1" in result

    def test_unknown_falls_to_min(self):
        result = _aggregation_to_sql("bogus", "val", "field")
        assert result == "MIN(val)"
