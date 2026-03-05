from autonomous_investment_robot.services.compliance.service import ComplianceService


def test_paper_provider_always_authorized():
    svc = ComplianceService(provider_whitelist=["kraken_spot"])
    decision = svc.check_provider_authorization("paper_sim_provider")
    assert decision.allowed is True
    assert decision.reason == "authorized"


def test_live_provider_must_be_whitelisted():
    svc = ComplianceService(provider_whitelist=["kraken_spot"])
    decision = svc.check_provider_authorization("kraken_futures")
    assert decision.allowed is False
    assert decision.reason == "provider_not_authorized"
