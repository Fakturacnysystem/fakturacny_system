from __future__ import annotations

from dataclasses import asdict

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.compliance.service import ComplianceService
from autonomous_investment_robot.services.execution.service import ExecutionService
from autonomous_investment_robot.services.models.service import ModelsService
from autonomous_investment_robot.services.ops.service import OpsService
from autonomous_investment_robot.services.policy.service import PolicyService
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


class RobotOrchestrator:
    def __init__(self, settings: RobotSettings) -> None:
        self.settings = settings
        self.compliance = ComplianceService(settings.compliance)
        self.models = ModelsService()
        self.policy = PolicyService()
        self.risk = RiskEngineService(settings.risk, safe_mode=settings.safe_mode_default)
        self.execution = ExecutionService(paper_mode=settings.trading_mode.value != "live")
        self.ops = OpsService()

    def boot(self) -> None:
        authorization = self.compliance.check_provider_authorization()
        if not authorization.allowed:
            self.ops.emit_alert("compliance_veto", authorization.reason)
            return
        snapshot = self.models.make_snapshot()
        intent = self.policy.make_intent(snapshot)
        risk_decision = self.risk.evaluate(intent, snapshot)
        self.ops.record_metric("risk_allowed", int(risk_decision.allowed))
        if not risk_decision.allowed:
            self.ops.emit_alert("risk_block", risk_decision.reason)
            return
        result = self.execution.execute(intent, risk_decision)
        self.ops.audit_event("execution_result", asdict(result))
