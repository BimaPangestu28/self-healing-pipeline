from rag.query import extract_ranked_matches


def test_extract_ranked_matches_keeps_top_match():
    result = {
        "value": [
            {"id": "doc-1", "@search.score": 0.95, "error": "timeout"},
            {"id": "doc-2", "@search.score": 0.93, "error": "retry"},
        ]
    }

    matches = extract_ranked_matches(result, k=1)

    assert len(matches) == 1
    assert matches[0]["id"] == "doc-1"
    assert matches[0]["similarity"] == 0.95


def test_extract_ranked_matches_filters_low_score_results():
    result = {
        "value": [
            {"id": "doc-1", "@search.score": 0.12, "error": "timeout"},
            {"id": "doc-2", "@search.score": 0.11, "error": "retry"},
        ]
    }

    matches = extract_ranked_matches(result, k=1)

    assert matches == []


def test_extract_ranked_matches_requires_strictly_greater_than_threshold():
    result = {
        "value": [
            {"id": "doc-1", "@search.score": 0.80, "error": "timeout"},
            {"id": "doc-2", "@search.score": 0.81, "error": "retry"},
        ]
    }

    matches = extract_ranked_matches(result, k=1)

    assert len(matches) == 1
    assert matches[0]["id"] == "doc-2"
    assert matches[0]["similarity"] == 0.81
