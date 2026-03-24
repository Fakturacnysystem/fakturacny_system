from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from pathlib import Path

from autonomous_investment_robot.core.contracts import AccountingDomainJudgment, AccountingJudgment, TruthConfidenceLevel, TruthConfidenceSnapshot
from autonomous_investment_robot.services.execution.service import Fill


class ReconciliationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ReconciliationAction(str, Enum):
    CONTINUE = "continue"
    ALERT = "alert"
    DEGRADE = "degrade"
    FLATTEN_ONLY = "flatten_only"
    HALT = "halt"
    HALT_AND_FLATTEN = "halt_and_flatten"


@dataclass(frozen=True)
class ReconciliationOutcome:
    ok: bool
    code: str
    severity: ReconciliationSeverity
    action: ReconciliationAction
    details: dict

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "code": self.code,
            "severity": self.severity.value,
            "action": self.action.value,
            "details": self.details,
        }


class ReconciliationService:
    _ACTION_ORDER = {
        ReconciliationAction.CONTINUE: 0,
        ReconciliationAction.ALERT: 1,
        ReconciliationAction.DEGRADE: 2,
        ReconciliationAction.FLATTEN_ONLY: 3,
        ReconciliationAction.HALT: 4,
        ReconciliationAction.HALT_AND_FLATTEN: 5,
    }

    def _classify(self, code: str) -> tuple[ReconciliationSeverity, ReconciliationAction]:
        if code in {"ok"}:
            return ReconciliationSeverity.INFO, ReconciliationAction.CONTINUE
        if code in {"position_mismatch", "live_position_mismatch"}:
            return ReconciliationSeverity.CRITICAL, ReconciliationAction.HALT_AND_FLATTEN
        if code in {"realized_pnl_mismatch", "live_realized_pnl_mismatch"}:
            return ReconciliationSeverity.CRITICAL, ReconciliationAction.HALT
        if code in {
            "open_order_state_mismatch",
            "live_open_order_state_mismatch",
            "cash_mismatch",
            "live_cash_mismatch",
        }:
            return ReconciliationSeverity.CRITICAL, ReconciliationAction.HALT
        if code in {"unrealized_pnl_mismatch", "live_unrealized_pnl_mismatch"}:
            return ReconciliationSeverity.WARNING, ReconciliationAction.ALERT
        return ReconciliationSeverity.WARNING, ReconciliationAction.ALERT

    def _outcome(self, ok: bool, code: str, details: dict) -> ReconciliationOutcome:
        severity, action = self._classify(code)
        return ReconciliationOutcome(ok=ok, code=code, severity=severity, action=action, details=details)

    def _domain(
        self,
        *,
        domain: str,
        ok: bool,
        code: str,
        severity: ReconciliationSeverity,
        action: ReconciliationAction,
        confidence: str,
        delta: float | None = None,
        tolerance: float | None = None,
        details: dict | None = None,
    ) -> AccountingDomainJudgment:
        return AccountingDomainJudgment(
            domain=domain,
            ok=ok,
            code=code,
            severity=severity.value,
            action=action.value,
            confidence=confidence,
            delta=delta,
            tolerance=tolerance,
            details={} if details is None else dict(details),
        )

    def _combine(self, domains: list[AccountingDomainJudgment]) -> AccountingJudgment:
        failing = [domain for domain in domains if not domain.ok]
        if not failing:
            return AccountingJudgment(
                ok=True,
                code="ok",
                severity=ReconciliationSeverity.INFO.value,
                action=ReconciliationAction.CONTINUE.value,
                domains=domains,
                details={"failing_domains": []},
            )
        primary = max(failing, key=lambda domain: self._ACTION_ORDER[ReconciliationAction(domain.action)])
        severity = primary.severity
        if any(domain.severity == ReconciliationSeverity.CRITICAL.value for domain in failing):
            severity = ReconciliationSeverity.CRITICAL.value
        elif any(domain.severity == ReconciliationSeverity.WARNING.value for domain in failing):
            severity = ReconciliationSeverity.WARNING.value
        return AccountingJudgment(
            ok=False,
            code=primary.code,
            severity=severity,
            action=primary.action,
            domains=domains,
            details={
                "failing_domains": [domain.domain for domain in failing],
                "primary_domain": primary.domain,
            },
        )

    def _confidence_level(self, snapshot: TruthConfidenceSnapshot | None, attr: str, default: str = TruthConfidenceLevel.AUTHORITATIVE.value) -> str:
        if snapshot is None:
            return default
        confidence = getattr(snapshot, attr, None)
        if confidence is None:
            return default
        level = getattr(confidence, "level", default)
        return level.value if hasattr(level, "value") else str(level)

    def _confidence_reason(self, snapshot: TruthConfidenceSnapshot | None, attr: str) -> str:
        if snapshot is None:
            return ""
        confidence = getattr(snapshot, attr, None)
        if confidence is None:
            return ""
        return str(getattr(confidence, "reason", ""))

    def _judgment_to_outcome(self, judgment: AccountingJudgment) -> ReconciliationOutcome:
        return ReconciliationOutcome(
            ok=judgment.ok,
            code=judgment.code,
            severity=ReconciliationSeverity(judgment.severity),
            action=ReconciliationAction(judgment.action),
            details={
                **judgment.details,
                "domains": [asdict(domain) for domain in judgment.domains],
            },
        )

    def reconcile_lifecycle_judgment(
        self,
        *,
        lifecycle_snapshot: list[dict] | None,
        confidence: str | None = None,
    ) -> AccountingDomainJudgment:
        lifecycle_snapshot = lifecycle_snapshot or []
        raw_conf = confidence or TruthConfidenceLevel.AUTHORITATIVE.value
        problematic = [
            item for item in lifecycle_snapshot if str(item.get("state", "")).lower() in {"orphaned", "stuck", "unknown", "cancel_rejected"}
        ]
        if not lifecycle_snapshot and raw_conf == TruthConfidenceLevel.UNAVAILABLE.value:
            return self._domain(
                domain="order_lifecycle_truth",
                ok=False,
                code="live_order_lifecycle_unavailable",
                severity=ReconciliationSeverity.CRITICAL,
                action=ReconciliationAction.FLATTEN_ONLY,
                confidence=raw_conf,
            )
        if problematic:
            return self._domain(
                domain="order_lifecycle_truth",
                ok=False,
                code="live_order_lifecycle_mismatch",
                severity=ReconciliationSeverity.CRITICAL,
                action=ReconciliationAction.FLATTEN_ONLY,
                confidence=raw_conf,
                details={"problematic_orders": problematic},
            )
        if raw_conf == TruthConfidenceLevel.PROXY.value:
            return self._domain(
                domain="order_lifecycle_truth",
                ok=False,
                code="live_order_lifecycle_proxy",
                severity=ReconciliationSeverity.WARNING,
                action=ReconciliationAction.DEGRADE,
                confidence=raw_conf,
                details={"order_count": len(lifecycle_snapshot)},
            )
        return self._domain(
            domain="order_lifecycle_truth",
            ok=True,
            code="ok",
            severity=ReconciliationSeverity.INFO,
            action=ReconciliationAction.CONTINUE,
            confidence=raw_conf,
            details={"order_count": len(lifecycle_snapshot)},
        )

    def expected_exposure(self, fills: list[Fill]) -> float:
        return sum(f.notional if f.side == "buy" else -f.notional for f in fills)

    def reconcile_judgment(
        self,
        *,
        fills: list[Fill],
        internal_exposure: float,
        open_orders_state_ok: bool,
        cash_ok: bool,
        local_realized_pnl: float | None = None,
        exchange_realized_pnl: float | None = None,
        local_unrealized_pnl: float | None = None,
        exchange_unrealized_pnl: float | None = None,
    ) -> AccountingJudgment:
        expected = self.expected_exposure(fills)
        tolerance = max(1.0, abs(expected) * 0.3)
        delta = expected - internal_exposure
        domains = [
            self._domain(
                domain="exposure",
                ok=abs(delta) <= tolerance,
                code="ok" if abs(delta) <= tolerance else "position_mismatch",
                severity=ReconciliationSeverity.INFO if abs(delta) <= tolerance else ReconciliationSeverity.CRITICAL,
                action=ReconciliationAction.CONTINUE if abs(delta) <= tolerance else ReconciliationAction.HALT_AND_FLATTEN,
                confidence=TruthConfidenceLevel.AUTHORITATIVE.value,
                delta=delta,
                tolerance=tolerance,
                details={"expected_exposure": expected, "internal_exposure": internal_exposure},
            ),
            self._domain(
                domain="open_orders",
                ok=open_orders_state_ok,
                code="ok" if open_orders_state_ok else "open_order_state_mismatch",
                severity=ReconciliationSeverity.INFO if open_orders_state_ok else ReconciliationSeverity.CRITICAL,
                action=ReconciliationAction.CONTINUE if open_orders_state_ok else ReconciliationAction.HALT,
                confidence=TruthConfidenceLevel.AUTHORITATIVE.value,
            ),
            self._domain(
                domain="balance",
                ok=cash_ok,
                code="ok" if cash_ok else "cash_mismatch",
                severity=ReconciliationSeverity.INFO if cash_ok else ReconciliationSeverity.CRITICAL,
                action=ReconciliationAction.CONTINUE if cash_ok else ReconciliationAction.HALT,
                confidence=TruthConfidenceLevel.AUTHORITATIVE.value,
            ),
        ]
        if local_realized_pnl is not None and exchange_realized_pnl is not None:
            pnl_delta = exchange_realized_pnl - local_realized_pnl
            pnl_tolerance = max(2.0, abs(exchange_realized_pnl) * 0.2)
            domains.append(
                self._domain(
                    domain="realized_pnl",
                    ok=abs(pnl_delta) <= pnl_tolerance,
                    code="ok" if abs(pnl_delta) <= pnl_tolerance else "realized_pnl_mismatch",
                    severity=ReconciliationSeverity.INFO if abs(pnl_delta) <= pnl_tolerance else ReconciliationSeverity.CRITICAL,
                    action=ReconciliationAction.CONTINUE if abs(pnl_delta) <= pnl_tolerance else ReconciliationAction.HALT,
                    confidence=TruthConfidenceLevel.AUTHORITATIVE.value,
                    delta=pnl_delta,
                    tolerance=pnl_tolerance,
                    details={"exchange_realized_pnl": exchange_realized_pnl, "local_realized_pnl": local_realized_pnl},
                )
            )
        if local_unrealized_pnl is not None and exchange_unrealized_pnl is not None:
            pnl_delta = exchange_unrealized_pnl - local_unrealized_pnl
            pnl_tolerance = max(2.0, abs(exchange_unrealized_pnl) * 0.25)
            domains.append(
                self._domain(
                    domain="unrealized_pnl",
                    ok=abs(pnl_delta) <= pnl_tolerance,
                    code="ok" if abs(pnl_delta) <= pnl_tolerance else "unrealized_pnl_mismatch",
                    severity=ReconciliationSeverity.INFO if abs(pnl_delta) <= pnl_tolerance else ReconciliationSeverity.WARNING,
                    action=ReconciliationAction.CONTINUE if abs(pnl_delta) <= pnl_tolerance else ReconciliationAction.ALERT,
                    confidence=TruthConfidenceLevel.AUTHORITATIVE.value,
                    delta=pnl_delta,
                    tolerance=pnl_tolerance,
                    details={"exchange_unrealized_pnl": exchange_unrealized_pnl, "local_unrealized_pnl": local_unrealized_pnl},
                )
            )
        judgment = self._combine(domains)
        judgment.details.setdefault("expected_exposure", expected)
        judgment.details.setdefault("internal_exposure", internal_exposure)
        return judgment

    def reconcile_report(
        self,
        fills: list[Fill],
        internal_exposure: float,
        open_orders_state_ok: bool,
        cash_ok: bool,
        local_realized_pnl: float | None = None,
        exchange_realized_pnl: float | None = None,
        local_unrealized_pnl: float | None = None,
        exchange_unrealized_pnl: float | None = None,
    ) -> ReconciliationOutcome:
        return self._judgment_to_outcome(
            self.reconcile_judgment(
                fills=fills,
                internal_exposure=internal_exposure,
                open_orders_state_ok=open_orders_state_ok,
                cash_ok=cash_ok,
                local_realized_pnl=local_realized_pnl,
                exchange_realized_pnl=exchange_realized_pnl,
                local_unrealized_pnl=local_unrealized_pnl,
                exchange_unrealized_pnl=exchange_unrealized_pnl,
            )
        )

    def reconcile(
        self,
        fills: list[Fill],
        internal_exposure: float,
        open_orders_state_ok: bool,
        cash_ok: bool,
    ) -> tuple[bool, str]:
        report = self.reconcile_report(
            fills=fills,
            internal_exposure=internal_exposure,
            open_orders_state_ok=open_orders_state_ok,
            cash_ok=cash_ok,
        )
        return report.ok, report.code

    def reconcile_live_judgment(
        self,
        *,
        exchange_exposure: float,
        internal_exposure: float,
        open_orders_state_ok: bool,
        cash_ok: bool,
        local_realized_pnl: float | None = None,
        exchange_realized_pnl: float | None = None,
        local_unrealized_pnl: float | None = None,
        exchange_unrealized_pnl: float | None = None,
        truth_confidence: TruthConfidenceSnapshot | None = None,
        stale_account_snapshot: bool = False,
        stale_market_snapshot: bool = False,
        lifecycle_snapshot: list[dict] | None = None,
        order_lifecycle_confidence: str | None = None,
    ) -> AccountingJudgment:
        tolerance = max(2.0, abs(exchange_exposure) * 0.1)
        delta = exchange_exposure - internal_exposure
        balance_conf = self._confidence_level(truth_confidence, "balance_truth_confidence")
        fill_conf = self._confidence_level(truth_confidence, "fill_truth_confidence")
        fee_conf = self._confidence_level(truth_confidence, "fee_truth_confidence")
        realized_conf = self._confidence_level(truth_confidence, "realized_pnl_confidence")
        exposure_conf = self._confidence_level(truth_confidence, "exposure_truth_confidence")
        market_conf = self._confidence_level(truth_confidence, "market_data_truth_confidence")
        unrealized_conf = self._confidence_level(truth_confidence, "unrealized_pnl_confidence")

        domains = [
            self._domain(
                domain="exposure",
                ok=abs(delta) <= tolerance,
                code="ok" if abs(delta) <= tolerance else "live_position_mismatch",
                severity=ReconciliationSeverity.INFO if abs(delta) <= tolerance else ReconciliationSeverity.CRITICAL,
                action=ReconciliationAction.CONTINUE if abs(delta) <= tolerance else ReconciliationAction.HALT_AND_FLATTEN,
                confidence=exposure_conf,
                delta=delta,
                tolerance=tolerance,
                details={"exchange_exposure": exchange_exposure, "internal_exposure": internal_exposure},
            ),
            self._domain(
                domain="open_orders",
                ok=open_orders_state_ok,
                code="ok" if open_orders_state_ok else "live_open_order_state_mismatch",
                severity=ReconciliationSeverity.INFO if open_orders_state_ok else ReconciliationSeverity.CRITICAL,
                action=ReconciliationAction.CONTINUE if open_orders_state_ok else ReconciliationAction.HALT,
                confidence=exposure_conf,
            ),
            self._domain(
                domain="balance",
                ok=cash_ok and balance_conf != TruthConfidenceLevel.UNAVAILABLE.value,
                code="ok" if cash_ok and balance_conf != TruthConfidenceLevel.UNAVAILABLE.value else "live_cash_mismatch",
                severity=ReconciliationSeverity.INFO if cash_ok and balance_conf != TruthConfidenceLevel.UNAVAILABLE.value else ReconciliationSeverity.CRITICAL,
                action=(
                    ReconciliationAction.CONTINUE
                    if cash_ok and balance_conf != TruthConfidenceLevel.UNAVAILABLE.value
                    else (ReconciliationAction.FLATTEN_ONLY if balance_conf == TruthConfidenceLevel.UNAVAILABLE.value else ReconciliationAction.HALT)
                ),
                confidence=balance_conf,
                details={"confidence_reason": self._confidence_reason(truth_confidence, "balance_truth_confidence")},
            ),
        ]
        if truth_confidence is not None:
            domains.extend(
                [
                    self._domain(
                        domain="fill_completeness",
                        ok=fill_conf == TruthConfidenceLevel.AUTHORITATIVE.value,
                        code=(
                            "ok"
                            if fill_conf == TruthConfidenceLevel.AUTHORITATIVE.value
                            else ("live_fill_truth_proxy" if fill_conf == TruthConfidenceLevel.PROXY.value else "live_fill_truth_unavailable")
                        ),
                        severity=(
                            ReconciliationSeverity.INFO
                            if fill_conf == TruthConfidenceLevel.AUTHORITATIVE.value
                            else (ReconciliationSeverity.WARNING if fill_conf == TruthConfidenceLevel.PROXY.value else ReconciliationSeverity.CRITICAL)
                        ),
                        action=(
                            ReconciliationAction.CONTINUE
                            if fill_conf == TruthConfidenceLevel.AUTHORITATIVE.value
                            else (ReconciliationAction.DEGRADE if fill_conf == TruthConfidenceLevel.PROXY.value else ReconciliationAction.FLATTEN_ONLY)
                        ),
                        confidence=fill_conf,
                        details={"confidence_reason": self._confidence_reason(truth_confidence, "fill_truth_confidence")},
                    ),
                    self._domain(
                        domain="fees",
                        ok=fee_conf == TruthConfidenceLevel.AUTHORITATIVE.value,
                        code=(
                            "ok"
                            if fee_conf == TruthConfidenceLevel.AUTHORITATIVE.value
                            else ("live_fee_truth_proxy" if fee_conf == TruthConfidenceLevel.PROXY.value else "live_fee_truth_unavailable")
                        ),
                        severity=(
                            ReconciliationSeverity.INFO
                            if fee_conf == TruthConfidenceLevel.AUTHORITATIVE.value
                            else (ReconciliationSeverity.WARNING if fee_conf == TruthConfidenceLevel.PROXY.value else ReconciliationSeverity.CRITICAL)
                        ),
                        action=(
                            ReconciliationAction.CONTINUE
                            if fee_conf == TruthConfidenceLevel.AUTHORITATIVE.value
                            else (ReconciliationAction.DEGRADE if fee_conf == TruthConfidenceLevel.PROXY.value else ReconciliationAction.FLATTEN_ONLY)
                        ),
                        confidence=fee_conf,
                        details={"confidence_reason": self._confidence_reason(truth_confidence, "fee_truth_confidence")},
                    ),
                ]
            )
        if lifecycle_snapshot is not None or order_lifecycle_confidence is not None:
            domains.append(
                self.reconcile_lifecycle_judgment(
                    lifecycle_snapshot=lifecycle_snapshot,
                    confidence=order_lifecycle_confidence,
                )
            )

        if local_realized_pnl is None or exchange_realized_pnl is None:
            if truth_confidence is None:
                realized_ok = True
                realized_code = "ok"
                realized_severity = ReconciliationSeverity.INFO
                realized_action = ReconciliationAction.CONTINUE
            else:
                realized_ok = False
                realized_code = "live_realized_pnl_proxy" if realized_conf == TruthConfidenceLevel.PROXY.value else "live_realized_pnl_unavailable"
                realized_severity = ReconciliationSeverity.WARNING if realized_conf == TruthConfidenceLevel.PROXY.value else ReconciliationSeverity.CRITICAL
                realized_action = ReconciliationAction.DEGRADE if realized_conf == TruthConfidenceLevel.PROXY.value else ReconciliationAction.FLATTEN_ONLY
            domains.append(
                self._domain(
                    domain="realized_pnl",
                    ok=realized_ok,
                    code=realized_code,
                    severity=realized_severity,
                    action=realized_action,
                    confidence=realized_conf,
                    details={"confidence_reason": self._confidence_reason(truth_confidence, "realized_pnl_confidence")},
                )
            )
        else:
            pnl_delta = exchange_realized_pnl - local_realized_pnl
            pnl_tolerance = max(2.0, abs(exchange_realized_pnl) * 0.2)
            if abs(pnl_delta) <= pnl_tolerance:
                realized_action = ReconciliationAction.CONTINUE
                realized_code = "ok"
                realized_severity = ReconciliationSeverity.INFO
            elif realized_conf == TruthConfidenceLevel.AUTHORITATIVE.value:
                realized_action = ReconciliationAction.HALT
                realized_code = "live_realized_pnl_mismatch"
                realized_severity = ReconciliationSeverity.CRITICAL
            elif realized_conf == TruthConfidenceLevel.PROXY.value:
                realized_action = ReconciliationAction.DEGRADE
                realized_code = "live_realized_pnl_proxy_mismatch"
                realized_severity = ReconciliationSeverity.WARNING
            else:
                realized_action = ReconciliationAction.FLATTEN_ONLY
                realized_code = "live_realized_pnl_unavailable"
                realized_severity = ReconciliationSeverity.CRITICAL
            domains.append(
                self._domain(
                    domain="realized_pnl",
                    ok=abs(pnl_delta) <= pnl_tolerance,
                    code=realized_code,
                    severity=realized_severity,
                    action=realized_action,
                    confidence=realized_conf,
                    delta=pnl_delta,
                    tolerance=pnl_tolerance,
                    details={"exchange_realized_pnl": exchange_realized_pnl, "local_realized_pnl": local_realized_pnl},
                )
            )
        if truth_confidence is not None:
            domains.append(
                self._domain(
                    domain="cost_basis",
                    ok=fill_conf == TruthConfidenceLevel.AUTHORITATIVE.value and realized_conf == TruthConfidenceLevel.AUTHORITATIVE.value,
                    code=(
                        "ok"
                        if fill_conf == TruthConfidenceLevel.AUTHORITATIVE.value and realized_conf == TruthConfidenceLevel.AUTHORITATIVE.value
                        else (
                            "live_cost_basis_proxy"
                            if TruthConfidenceLevel.PROXY.value in {fill_conf, realized_conf}
                            else "live_cost_basis_unverified"
                        )
                    ),
                    severity=(
                        ReconciliationSeverity.INFO
                        if fill_conf == TruthConfidenceLevel.AUTHORITATIVE.value and realized_conf == TruthConfidenceLevel.AUTHORITATIVE.value
                        else (ReconciliationSeverity.WARNING if TruthConfidenceLevel.PROXY.value in {fill_conf, realized_conf} else ReconciliationSeverity.CRITICAL)
                    ),
                    action=(
                        ReconciliationAction.CONTINUE
                        if fill_conf == TruthConfidenceLevel.AUTHORITATIVE.value and realized_conf == TruthConfidenceLevel.AUTHORITATIVE.value
                        else (ReconciliationAction.DEGRADE if TruthConfidenceLevel.PROXY.value in {fill_conf, realized_conf} else ReconciliationAction.FLATTEN_ONLY)
                    ),
                    confidence=realized_conf,
                )
            )

        if local_unrealized_pnl is None or exchange_unrealized_pnl is None:
            if truth_confidence is not None:
                domains.append(
                    self._domain(
                        domain="unrealized_pnl",
                        ok=unrealized_conf == TruthConfidenceLevel.AUTHORITATIVE.value and exchange_unrealized_pnl is not None,
                        code=(
                            "ok"
                            if unrealized_conf == TruthConfidenceLevel.AUTHORITATIVE.value and exchange_unrealized_pnl is not None
                            else (
                                "live_unrealized_pnl_truth_proxy"
                                if unrealized_conf == TruthConfidenceLevel.PROXY.value
                                else "live_unrealized_pnl_truth_unavailable"
                            )
                        ),
                        severity=(
                            ReconciliationSeverity.INFO
                            if unrealized_conf == TruthConfidenceLevel.AUTHORITATIVE.value and exchange_unrealized_pnl is not None
                            else ReconciliationSeverity.WARNING
                        ),
                        action=(
                            ReconciliationAction.CONTINUE
                            if unrealized_conf == TruthConfidenceLevel.AUTHORITATIVE.value and exchange_unrealized_pnl is not None
                            else ReconciliationAction.DEGRADE
                        ),
                        confidence=unrealized_conf,
                        details={"confidence_reason": self._confidence_reason(truth_confidence, "unrealized_pnl_confidence")},
                    )
                )
        else:
            pnl_delta = exchange_unrealized_pnl - local_unrealized_pnl
            pnl_tolerance = max(2.0, abs(exchange_unrealized_pnl) * 0.25)
            domains.append(
                self._domain(
                    domain="unrealized_pnl",
                    ok=abs(pnl_delta) <= pnl_tolerance and unrealized_conf != TruthConfidenceLevel.UNAVAILABLE.value,
                    code=(
                        "ok"
                        if abs(pnl_delta) <= pnl_tolerance and unrealized_conf != TruthConfidenceLevel.UNAVAILABLE.value
                        else (
                            "live_unrealized_pnl_mismatch"
                            if unrealized_conf == TruthConfidenceLevel.AUTHORITATIVE.value
                            else (
                                "live_unrealized_pnl_proxy_mismatch"
                                if unrealized_conf == TruthConfidenceLevel.PROXY.value
                                else "live_unrealized_pnl_truth_unavailable"
                            )
                        )
                    ),
                    severity=(
                        ReconciliationSeverity.INFO
                        if abs(pnl_delta) <= pnl_tolerance and unrealized_conf != TruthConfidenceLevel.UNAVAILABLE.value
                        else (ReconciliationSeverity.WARNING if unrealized_conf != TruthConfidenceLevel.UNAVAILABLE.value else ReconciliationSeverity.WARNING)
                    ),
                    action=(
                        ReconciliationAction.CONTINUE
                        if abs(pnl_delta) <= pnl_tolerance and unrealized_conf != TruthConfidenceLevel.UNAVAILABLE.value
                        else (ReconciliationAction.ALERT if unrealized_conf == TruthConfidenceLevel.AUTHORITATIVE.value else ReconciliationAction.DEGRADE)
                    ),
                    confidence=unrealized_conf,
                    delta=pnl_delta,
                    tolerance=pnl_tolerance,
                    details={
                        "exchange_unrealized_pnl": exchange_unrealized_pnl,
                        "local_unrealized_pnl": local_unrealized_pnl,
                        "confidence_reason": self._confidence_reason(truth_confidence, "unrealized_pnl_confidence"),
                    },
                )
            )

        if truth_confidence is not None or stale_account_snapshot or stale_market_snapshot:
            domains.append(
                self._domain(
                    domain="stale_snapshots",
                    ok=not stale_account_snapshot and not stale_market_snapshot and market_conf != TruthConfidenceLevel.UNAVAILABLE.value,
                    code=(
                        "ok"
                        if not stale_account_snapshot and not stale_market_snapshot and market_conf != TruthConfidenceLevel.UNAVAILABLE.value
                        else (
                            "live_snapshot_proxy"
                            if market_conf == TruthConfidenceLevel.PROXY.value or stale_market_snapshot or stale_account_snapshot
                            else "live_snapshot_unavailable"
                        )
                    ),
                    severity=(
                        ReconciliationSeverity.INFO
                        if not stale_account_snapshot and not stale_market_snapshot and market_conf != TruthConfidenceLevel.UNAVAILABLE.value
                        else (ReconciliationSeverity.WARNING if market_conf == TruthConfidenceLevel.PROXY.value or stale_market_snapshot or stale_account_snapshot else ReconciliationSeverity.CRITICAL)
                    ),
                    action=(
                        ReconciliationAction.CONTINUE
                        if not stale_account_snapshot and not stale_market_snapshot and market_conf != TruthConfidenceLevel.UNAVAILABLE.value
                        else (ReconciliationAction.DEGRADE if market_conf == TruthConfidenceLevel.PROXY.value or stale_market_snapshot or stale_account_snapshot else ReconciliationAction.FLATTEN_ONLY)
                    ),
                    confidence=market_conf,
                    details={"stale_account_snapshot": stale_account_snapshot, "stale_market_snapshot": stale_market_snapshot},
                )
            )

        judgment = self._combine(domains)
        judgment.details.update(
            {
                "exchange_exposure": exchange_exposure,
                "internal_exposure": internal_exposure,
                "truth_confidence": None if truth_confidence is None else asdict(truth_confidence),
            }
        )
        return judgment

    def reconcile_live_report(
        self,
        exchange_exposure: float,
        internal_exposure: float,
        open_orders_state_ok: bool,
        cash_ok: bool,
        local_realized_pnl: float | None = None,
        exchange_realized_pnl: float | None = None,
        local_unrealized_pnl: float | None = None,
        exchange_unrealized_pnl: float | None = None,
        truth_confidence: TruthConfidenceSnapshot | None = None,
        stale_account_snapshot: bool = False,
        stale_market_snapshot: bool = False,
        lifecycle_snapshot: list[dict] | None = None,
        order_lifecycle_confidence: str | None = None,
    ) -> ReconciliationOutcome:
        return self._judgment_to_outcome(
            self.reconcile_live_judgment(
                exchange_exposure=exchange_exposure,
                internal_exposure=internal_exposure,
                open_orders_state_ok=open_orders_state_ok,
                cash_ok=cash_ok,
                local_realized_pnl=local_realized_pnl,
                exchange_realized_pnl=exchange_realized_pnl,
                local_unrealized_pnl=local_unrealized_pnl,
                exchange_unrealized_pnl=exchange_unrealized_pnl,
                truth_confidence=truth_confidence,
                stale_account_snapshot=stale_account_snapshot,
                stale_market_snapshot=stale_market_snapshot,
                lifecycle_snapshot=lifecycle_snapshot,
                order_lifecycle_confidence=order_lifecycle_confidence,
            )
        )

    def reconcile_live(
        self,
        exchange_exposure: float,
        internal_exposure: float,
        open_orders_state_ok: bool,
        cash_ok: bool,
    ) -> tuple[bool, str]:
        report = self.reconcile_live_report(
            exchange_exposure=exchange_exposure,
            internal_exposure=internal_exposure,
            open_orders_state_ok=open_orders_state_ok,
            cash_ok=cash_ok,
        )
        return report.ok, report.code

    def persist_report(self, run_dir: str, report: dict) -> str:
        out = Path(run_dir) / "reconciliation_report.jsonl"
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(report, sort_keys=True, default=str) + "\n")
        return str(out)
