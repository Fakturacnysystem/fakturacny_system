from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_governance_docs_exist() -> None:
    required = [
        "LIVE_AUTHORITY_BOUNDARY.md",
        "RELEASE_BASELINE.md",
        "PROMOTION_GATES.md",
        "RUN_REVIEW_TEMPLATE.md",
        "OPERATOR_RUNTIME_CHECKLIST.md",
    ]

    for name in required:
        path = REPO_ROOT / name
        assert path.exists(), name
        assert path.read_text(encoding="utf-8").strip(), name


def test_evidence_scorecard_preserves_doctrine_floor_and_non_authoritative_additives() -> None:
    payload = json.loads((REPO_ROOT / "evidence_scorecard.json").read_text(encoding="utf-8"))

    assert payload["global_invariants"]["provider"] == "kraken_spot"
    assert payload["global_invariants"]["product"] == "spot"
    assert payload["global_invariants"]["minimum_sell_net_profit_bps_floor"] >= 120.0
    assert payload["global_invariants"]["no_additive_live_authority_promotion_without_explicit_code_gate"] is True

    by_name = {item["name"]: item for item in payload["subsystems"]}
    for name in [
        "market_universe_ranking",
        "playbook_framework",
        "opportunity_auction",
        "portfolio_allocator",
        "adaptive_cadence_and_self_throttling",
    ]:
        assert by_name[name]["authority_level"] == "shadow_only"
        assert by_name[name]["decision_status"] == "shadow_only"


def test_authority_boundary_doc_explicitly_marks_legacy_live_path_as_authoritative() -> None:
    content = (REPO_ROOT / "LIVE_AUTHORITY_BOUNDARY.md").read_text(encoding="utf-8")

    assert "canonical live authority" in content.lower()
    assert "policy/service.py" in content
    assert "execution/live_kraken_spot_service.py" in content
    assert "shadow-only by design" in content.lower()
