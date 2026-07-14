"""Tests for the LiteLLM routing classifier."""
import os
import sys

os.environ.setdefault("SESSION_BACKEND", "memory")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from routing import classify_query, FAST_MODEL, DEEP_MODEL, BACKUP_MODEL


def test_return_policy_is_fast_faq():
    assert classify_query("What is your return policy?") == "fast-faq"


def test_shipping_info_is_fast_faq():
    assert classify_query("How long does shipping take?") == "fast-faq"


def test_warranty_query_is_fast_faq():
    assert classify_query("What is the warranty on the TV?") == "fast-faq"


def test_comparison_is_deep_support():
    assert classify_query("Compare the 4K TV vs 8K TV for home theatre") == "deep-support"


def test_budget_recommendation_is_deep_support():
    assert classify_query("Recommend a noise-cancelling headphone under $200") == "deep-support"


def test_specs_question_is_deep_support():
    assert classify_query("What are the specs and pros and cons of the keyboard?") == "deep-support"


def test_returns_valid_route_for_any_input():
    for query in ["Hello", "help", "1234", "!@#$"]:
        result = classify_query(query)
        assert result in ("fast-faq", "deep-support"), f"Unexpected route for {query!r}: {result}"


def test_model_constants_are_strings():
    assert isinstance(FAST_MODEL, str) and FAST_MODEL
    assert isinstance(DEEP_MODEL, str) and DEEP_MODEL
    assert isinstance(BACKUP_MODEL, str) and BACKUP_MODEL
