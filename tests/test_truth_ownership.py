from autonomous_investment_robot.config.settings import ExecutionMode
from autonomous_investment_robot.core.truth_ownership import TruthDomain, ownership_gaps, ownership_map, validate_ownership_map


def _domain_values(rows) -> set[str]:
    return {row.domain.value for row in rows}


def test_paper_truth_ownership_map_has_all_domains_and_single_owner_each():
    rows = ownership_map(ExecutionMode.PAPER, provider_id="binance_um_perps")
    assert _domain_values(rows) == {d.value for d in TruthDomain}
    assert validate_ownership_map(rows) == []
    assert set(ownership_gaps(rows)) == {"unrealized_pnl_truth"}


def test_live_truth_ownership_map_declares_fill_fee_and_realized_pnl_as_authoritative():
    rows = ownership_map(ExecutionMode.LIVE_TESTNET, provider_id="binance_um_perps")
    assert _domain_values(rows) == {d.value for d in TruthDomain}
    assert validate_ownership_map(rows) == []
    by_domain = {row.domain.value: row for row in rows}
    assert by_domain["fill_truth"].authority.value == "authoritative"
    assert by_domain["fee_truth"].authority.value == "authoritative"
    assert by_domain["realized_pnl_truth"].authority.value == "authoritative"


def test_truth_ownership_map_declares_runtime_gate_and_reconciliation_domains():
    rows = ownership_map(ExecutionMode.LIVE_TESTNET, provider_id="binance_um_perps")
    domains = _domain_values(rows)

    assert "risk_mode_truth" in domains
    assert "live_gating_status_truth" in domains
    assert "reconciliation_status_truth" in domains
