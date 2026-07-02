"""Tests for tool output limiting to prevent context flooding."""

import pytest

from src.tools.utils import (
    format_result_summary,
    format_tool_result,
    limit_dict_result,
    limit_list_items,
    truncate_string,
)


class TestTruncateString:
    """Tests for string truncation."""

    def test_truncate_short_string(self):
        """Short strings should not be truncated."""
        text = "Hello, world!"
        result = truncate_string(text, max_length=100)
        assert result == text
        assert "truncated" not in result.lower()

    def test_truncate_long_string(self):
        """Long strings should be truncated with indication."""
        text = "a" * 10000
        result = truncate_string(text, max_length=5000)
        assert len(result) < len(text)
        assert "truncated" in result.lower()
        assert "10000 characters" in result
        assert "5000 characters" in result
        assert result.startswith("a" * 5000)

    def test_truncate_exact_length(self):
        """Strings at exact max length should not be truncated."""
        text = "a" * 5000
        result = truncate_string(text, max_length=5000)
        assert result == text
        assert "truncated" not in result.lower()


class TestLimitListItems:
    """Tests for list item limiting."""

    def test_limit_short_list(self):
        """Short lists should not be limited."""
        items = [1, 2, 3, 4, 5]
        result, truncated = limit_list_items(items, max_items=10)
        assert result == items
        assert truncated is False

    def test_limit_long_list(self):
        """Long lists should be limited."""
        items = list(range(100))
        result, truncated = limit_list_items(items, max_items=50)
        assert len(result) == 50
        assert result == list(range(50))
        assert truncated is True

    def test_limit_exact_length_list(self):
        """Lists at exact max length should not be limited."""
        items = list(range(50))
        result, truncated = limit_list_items(items, max_items=50)
        assert result == items
        assert truncated is False


class TestLimitDictResult:
    """Tests for dictionary result limiting."""

    def test_limit_dict_with_lists(self):
        """Dictionaries with large lists should be limited."""
        data = {
            "hits": [{"id": i, "data": f"item_{i}"} for i in range(100)],
            "total": 100,
            "metadata": "test",
        }
        result = limit_dict_result(data, list_keys=["hits"], max_items=50)

        assert len(result["hits"]) == 50
        assert result["total"] == 100
        assert result["metadata"] == "test"
        assert "_truncation_info" in result
        assert "hits" in result["_truncation_info"]
        assert result["_truncation_info"]["hits"]["original_count"] == 100
        assert result["_truncation_info"]["hits"]["displayed_count"] == 50

    def test_limit_dict_with_long_strings(self):
        """Dictionaries with long strings should truncate them."""
        long_text = "x" * 10000
        data = {
            "message": long_text,
            "status": "ok",
        }
        result = limit_dict_result(data, max_string_length=5000)

        assert len(result["message"]) < len(long_text)
        assert "truncated" in result["message"].lower()
        assert result["status"] == "ok"
        assert "_truncation_info" in result

    def test_limit_dict_multiple_lists(self):
        """Dictionaries with multiple large lists should limit all."""
        data = {
            "pods": [f"pod-{i}" for i in range(200)],
            "events": [f"event-{i}" for i in range(150)],
            "nodes": [f"node-{i}" for i in range(30)],
        }
        result = limit_dict_result(
            data, list_keys=["pods", "events", "nodes"], max_items=50
        )

        assert len(result["pods"]) == 50
        assert len(result["events"]) == 50
        assert len(result["nodes"]) == 30  # Not truncated, under limit
        assert "_truncation_info" in result
        assert "pods" in result["_truncation_info"]
        assert "events" in result["_truncation_info"]
        assert "nodes" not in result["_truncation_info"]  # Not truncated

    def test_limit_dict_no_truncation_needed(self):
        """Dictionaries within limits should not be modified."""
        data = {
            "items": [1, 2, 3],
            "message": "short message",
        }
        result = limit_dict_result(data, list_keys=["items"], max_items=50)

        assert result["items"] == [1, 2, 3]
        assert result["message"] == "short message"
        assert "_truncation_info" not in result


class TestFormatResultSummary:
    """Tests for result summary formatting."""

    def test_format_summary_with_fields(self):
        """Summary should include specified fields."""
        data = {
            "total": 100,
            "hits": [1, 2, 3],
            "status": "success",
        }
        summary = format_result_summary(data, summary_fields=["total", "status"])

        assert "total: 100" in summary
        assert "status: success" in summary

    def test_format_summary_with_list_fields(self):
        """Summary should show item counts for list fields."""
        data = {
            "results": [1, 2, 3, 4, 5],
            "errors": [],
        }
        summary = format_result_summary(data, summary_fields=["results", "errors"])

        assert "results: 5 items" in summary
        assert "errors: 0 items" in summary

    def test_format_summary_with_truncation_info(self):
        """Summary should include truncation information."""
        data = {
            "hits": [1, 2, 3],
            "_truncation_info": {
                "hits": {
                    "original_count": 200,
                    "displayed_count": 50,
                    "truncated": True,
                }
            },
        }
        summary = format_result_summary(data)

        assert "hits truncated" in summary
        assert "50/200" in summary


class TestFormatToolResult:
    """Tests for complete tool result formatting."""

    def test_format_tool_result_with_large_list(self):
        """Tool result with large list should be limited and summarized."""
        result = {
            "hits": [{"id": i, "log": f"log entry {i}"} for i in range(200)],
            "total": 200,
            "took": 42,
        }

        formatted = format_tool_result(
            description="Test log search:",
            result=result,
            list_keys=["hits"],
            summary_fields=["total", "took"],
            max_items=50,
        )

        assert "Test log search:" in formatted
        assert "total: 200" in formatted
        assert "took: 42" in formatted
        assert "hits truncated" in formatted
        assert "50/200" in formatted
        # Verify JSON is truncated
        assert '"hits"' in formatted

    def test_format_tool_result_elasticsearch_simulation(self):
        """Simulate Elasticsearch response with limiting."""
        # Simulate a large Elasticsearch response
        elk_result = {
            "took": 15,
            "hits": {
                "total": 1500,
                "hits": [
                    {
                        "_index": "logs-2024.01",
                        "_id": str(i),
                        "_source": {
                            "timestamp": "2024-01-28T10:00:00Z",
                            "level": "ERROR",
                            "message": f"Error log entry number {i}" * 10,
                        },
                    }
                    for i in range(200)
                ],
            },
        }

        # This would typically be nested, let's flatten for the test
        flattened = {
            "took": elk_result["took"],
            "total": elk_result["hits"]["total"],
            "hits": elk_result["hits"]["hits"],
        }

        formatted = format_tool_result(
            description="ELK search results:",
            result=flattened,
            list_keys=["hits"],
            summary_fields=["total", "took"],
            max_items=50,
            max_string_length=8000,
        )

        assert "ELK search results:" in formatted
        assert "total: 1500" in formatted
        assert "took: 15" in formatted
        # Should be limited to 50 hits
        assert "hits truncated" in formatted

    def test_format_tool_result_k8s_pods_simulation(self):
        """Simulate Kubernetes pod list with limiting."""
        k8s_result = {
            "deployment": "my-app",
            "replicas": 100,
            "available_replicas": 98,
            "pods": [
                {
                    "name": f"my-app-{i}",
                    "status": "Running",
                    "restarts": 0,
                }
                for i in range(100)
            ],
            "events": [
                {
                    "type": "Normal",
                    "reason": "Scheduled",
                    "message": f"Event {i}",
                }
                for i in range(150)
            ],
        }

        formatted = format_tool_result(
            description="Deployment details:",
            result=k8s_result,
            list_keys=["pods", "events"],
            summary_fields=["replicas", "available_replicas"],
            max_items=50,
        )

        assert "Deployment details:" in formatted
        assert "replicas: 100" in formatted
        assert "available_replicas: 98" in formatted
        assert "pods truncated" in formatted
        assert "50/100" in formatted
        assert "events truncated" in formatted
        assert "50/150" in formatted


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_dict(self):
        """Empty dictionary should be handled."""
        result = limit_dict_result({})
        assert result == {}

    def test_none_values(self):
        """None values should be handled."""
        data = {"field": None}
        result = limit_dict_result(data)
        assert result["field"] is None

    def test_nested_structures(self):
        """Nested structures should be handled (top-level limiting only)."""
        data = {
            "items": [
                {
                    "nested_list": [1, 2, 3, 4, 5],
                }
                for _ in range(100)
            ]
        }
        result = limit_dict_result(data, list_keys=["items"], max_items=50)
        # Only top-level list should be limited
        assert len(result["items"]) == 50
        # Nested lists remain unchanged
        assert len(result["items"][0]["nested_list"]) == 5
