from __future__ import annotations

from autonomous_investment_robot.universe_gateway.auth import decode_token, issue_token, role_allows


def test_issue_and_decode_token() -> None:
    token = issue_token(username="alice", role="analyst", secret="s3cr3t", ttl_s=120)
    payload = decode_token(token, secret="s3cr3t")
    assert payload["sub"] == "alice"
    assert payload["role"] == "analyst"


def test_rbac_rank_order() -> None:
    assert role_allows("admin", {"observer"})
    assert role_allows("operator", {"analyst"})
    assert not role_allows("observer", {"operator"})
