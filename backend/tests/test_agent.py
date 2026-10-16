"""Agent guardrails that don't need an LLM call: the 'no path, no claim' verifier and schema cleanup."""
from warden.agent import _clean_schema, _compact, verify

SERVICES = {"frontend", "checkoutservice", "paymentservice", "loadgenerator"}
RESULTS = [{"tool": "reachable_findings", "summary": "Highest risk: CVE-2023-44487 in golang.org/x/net on frontend", "rows": [{"service": "checkoutservice"}], "args": {}}]


def test_verifier_accepts_claims_present_in_tool_results():
    v = verify("Fix CVE-2023-44487 on frontend first; checkoutservice is next.", RESULTS, SERVICES)
    assert v["ok"] and v["unsupported"] == []


def test_verifier_flags_entities_no_tool_returned():
    v = verify("Also patch CVE-2021-44228 in paymentservice.", RESULTS, SERVICES)
    assert not v["ok"] and v["unsupported"] == ["CVE-2021-44228", "paymentservice"]


def test_verifier_rejects_answers_without_any_tool_call():
    v = verify("Everything is fine.", [], SERVICES)
    assert not v["ok"] and v["no_tools"]


def test_schema_cleanup_flattens_optional_fields():
    s = _clean_schema({"title": "x", "properties": {"service": {"title": "Service", "anyOf": [{"type": "string"}, {"type": "null"}]}}})
    assert s == {"properties": {"service": {"type": "string"}}}


def test_compact_tool_result_keeps_only_listed_columns():
    out = _compact({"summary": "s", "error": None, "columns": ["a"], "rows": [{"a": 1, "b": 2}] * 20})
    assert '"b"' not in out and out.count('"a"') == 6


def test_verifier_flags_topic_claims_without_the_tool_that_knows_them():
    v = verify("Fix CVE-2023-44487 on frontend. No prior decision is recorded.", RESULTS, SERVICES)
    assert not v["ok"] and v["unsupported"] == ["decisions (no decisions_about call)"]
    ok = verify("No prior decision is recorded.", RESULTS + [{"tool": "decisions_about", "summary": "none", "rows": [], "args": {}}], SERVICES)
    assert ok["ok"]
