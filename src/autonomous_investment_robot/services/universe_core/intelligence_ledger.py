from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _world_fingerprint_payload(world: Any) -> dict[str, Any]:
    market = getattr(world, "market_state", None)
    venue = getattr(world, "venue_state", None)
    portfolio = getattr(world, "portfolio_state", None)
    infra = getattr(world, "infra_state", None)
    risk = getattr(world, "risk_state", None)
    return {
        "symbol": str(getattr(market, "primary_symbol", "") or ""),
        "venue": str(getattr(venue, "primary_venue", "") or ""),
        "regime": str(getattr(market, "regime", "") or ""),
        "volatility_regime": str(getattr(market, "volatility_regime", "") or ""),
        "liquidity_regime": str(getattr(market, "liquidity_regime", "") or ""),
        "panic": bool(getattr(market, "panic", False)),
        "equity_quote": round(_safe_float(getattr(portfolio, "equity_quote", 0.0), 0.0), 8),
        "free_quote": round(_safe_float(getattr(portfolio, "free_quote", 0.0), 0.0), 8),
        "exposure_quote": round(_safe_float(getattr(portfolio, "exposure_quote", 0.0), 0.0), 8),
        "drawdown_pct": round(_safe_float(getattr(portfolio, "drawdown_pct", 0.0), 0.0), 8),
        "infra_stale_feed": bool(getattr(infra, "stale_feed", False)),
        "infra_desync": bool(getattr(infra, "desync", False)),
        "risk_mode": str(getattr(risk, "mode", "") or ""),
        "risk_hard_stop": bool(getattr(risk, "hard_stop", False)),
        "risk_observe_only": bool(getattr(risk, "observe_only", False)),
    }


def _phase_sort_key(phase_key: str) -> tuple[int, str]:
    raw = str(phase_key)
    if raw.startswith("phase"):
        tail = raw[5:].split("_", 1)[0]
        if tail.isdigit():
            return (int(tail), raw)
    return (999, raw)


_VOLATILE_HASH_KEYS: set[str] = {
    "cycle_id",
    "as_of_ts",
    "source_age_s",
    "report_id",
    "bundle_id",
    "certificate_id",
    "index_id",
    "pack_id",
    "dossier_id",
    "register_id",
    "recommendation_id",
    "genome_id",
    "mutation_id",
    "mutation_seed",
    "seed",
    "path_id",
    "case_id",
    "tree_id",
    "branch_id",
    "contract_id",
    "session_id",
}


def _normalize_for_hash(value: Any, key: str = "") -> Any:
    key_norm = str(key).strip().lower()
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for raw_key in sorted(value.keys(), key=lambda item: str(item)):
            key_str = str(raw_key)
            key_l = key_str.lower()
            if key_l in _VOLATILE_HASH_KEYS:
                continue
            if key_l.endswith("_id") or key_l == "id":
                continue
            if key_l.endswith("_ts"):
                continue
            out[key_str] = _normalize_for_hash(value.get(raw_key), key=key_str)
        return out
    if isinstance(value, list):
        return [_normalize_for_hash(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [_normalize_for_hash(item, key=key) for item in value]
    if isinstance(value, float):
        return round(float(value), 2)
    return value


@dataclass(frozen=True)
class LedgerPhaseEntry:
    phase_key: str
    payload_hash: str
    safety_relevant: bool
    veto: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_key": self.phase_key,
            "payload_hash": self.payload_hash,
            "safety_relevant": bool(self.safety_relevant),
            "veto": bool(self.veto),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class IntelligenceLedgerRecord:
    schema: str
    cycle_id: str
    ledger_id: str
    world_fingerprint: str
    phase_hash_chain: tuple[str, ...] = field(default_factory=tuple)
    entries: tuple[LedgerPhaseEntry, ...] = field(default_factory=tuple)
    veto_chain: tuple[str, ...] = field(default_factory=tuple)
    integrity_score: float = 0.0
    bounded_compute: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "cycle_id": self.cycle_id,
            "ledger_id": self.ledger_id,
            "world_fingerprint": self.world_fingerprint,
            "phase_hash_chain": [str(item) for item in self.phase_hash_chain],
            "entries": [row.to_dict() for row in self.entries],
            "veto_chain": [str(item) for item in self.veto_chain],
            "integrity_score": float(self.integrity_score),
            "bounded_compute": bool(self.bounded_compute),
        }


class DeterministicIntelligenceLedger:
    """Phase 36 deterministic chain of advanced-intelligence outputs."""

    REQUIRED_PHASE_KEYS: tuple[str, ...] = (
        "phase26_global_market_state",
        "phase27_horizon_alignment",
        "phase28_market_energy",
        "phase29_future_simulation",
        "phase30_cross_reality_signal",
        "phase31_personality_trace",
        "phase32_survival_doctrine",
        "phase33_evolutionary_research",
        "phase34_fund_brain",
        "phase35_institutional_readiness",
    )

    def compile(
        self,
        *,
        cycle_id: str,
        world: Any,
        advanced_intelligence: Mapping[str, Any],
    ) -> IntelligenceLedgerRecord:
        intelligence = _safe_mapping(advanced_intelligence)
        world_fp = _stable_hash(_world_fingerprint_payload(world))[:24]
        phase_keys = sorted(intelligence.keys(), key=_phase_sort_key)
        entries: list[LedgerPhaseEntry] = []
        phase_hash_chain: list[str] = []
        veto_chain: list[str] = []
        chain_cursor = "genesis"
        for phase_key in phase_keys:
            payload = intelligence.get(phase_key)
            payload_map = _safe_mapping(payload)
            payload_hash = _stable_hash(
                {
                    "phase_key": str(phase_key),
                    "payload": self._stable_phase_payload(phase_key=str(phase_key), payload=payload_map),
                }
            )
            veto, veto_reason = self._extract_veto(phase_key=phase_key, payload=payload_map)
            reason_codes = tuple(str(item) for item in payload_map.get("reason_codes", []) if str(item)) if isinstance(payload_map.get("reason_codes", []), list) else tuple()
            safety_relevant = phase_key in {
                "phase32_survival_doctrine",
                "phase34_fund_brain",
                "phase35_institutional_readiness",
            }
            if veto and veto_reason:
                veto_chain.append(veto_reason)
            entry = LedgerPhaseEntry(
                phase_key=str(phase_key),
                payload_hash=payload_hash,
                safety_relevant=safety_relevant,
                veto=veto,
                reason_codes=reason_codes,
            )
            entries.append(entry)
            chain_cursor = _stable_hash(
                {
                    "prev": chain_cursor,
                    "phase_key": entry.phase_key,
                    "payload_hash": entry.payload_hash,
                    "veto": entry.veto,
                }
            )[:24]
            phase_hash_chain.append(chain_cursor)

        present_required = len([key for key in self.REQUIRED_PHASE_KEYS if key in intelligence])
        missing_required = len(self.REQUIRED_PHASE_KEYS) - present_required
        integrity_score = _clamp(1.0 - (missing_required * 0.10), 0.0, 1.0)
        ledger_id = _stable_hash(
            {
                "world_fingerprint": world_fp,
                "chain_head": chain_cursor,
                "entries": len(entries),
                "veto_chain": veto_chain,
            }
        )[:24]
        return IntelligenceLedgerRecord(
            schema="phase36_intelligence_ledger_v1",
            cycle_id=str(cycle_id),
            ledger_id=ledger_id,
            world_fingerprint=world_fp,
            phase_hash_chain=tuple(phase_hash_chain),
            entries=tuple(entries),
            veto_chain=tuple(veto_chain),
            integrity_score=integrity_score,
            bounded_compute=True,
        )

    def _stable_phase_payload(self, *, phase_key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if phase_key == "phase27_horizon_alignment":
            conflicts_raw = payload.get("conflicts", [])
            conflicts: list[dict[str, Any]] = []
            if isinstance(conflicts_raw, list):
                for row in conflicts_raw:
                    row_map = _safe_mapping(row)
                    conflicts.append(
                        {
                            "between": [str(item) for item in row_map.get("between", [])] if isinstance(row_map.get("between", []), list) else [],
                            "reason": str(row_map.get("reason", "") or ""),
                            "severity": round(_safe_float(row_map.get("severity", 0.0), 0.0), 2),
                        }
                    )
            return {
                "dominant_horizon": str(payload.get("dominant_horizon", "") or ""),
                "recommendation_safe": bool(payload.get("recommendation_safe", False)),
                "conflicts": conflicts,
                "reason_codes": [str(item) for item in payload.get("reason_codes", []) if str(item)] if isinstance(payload.get("reason_codes", []), list) else [],
            }
        if phase_key == "phase33_evolutionary_research":
            extinction = _safe_mapping(payload.get("extinction", {}))
            return {
                "promotion_gate": _normalize_for_hash(_safe_mapping(payload.get("promotion_gate", {})), key="promotion_gate"),
                "safety_envelope": _normalize_for_hash(_safe_mapping(payload.get("safety_envelope", {})), key="safety_envelope"),
                "extinction": {
                    "extinct": bool(extinction.get("extinct", False)),
                    "reason_codes": [str(item) for item in extinction.get("reason_codes", []) if str(item)] if isinstance(extinction.get("reason_codes", []), list) else [],
                },
            }
        return _normalize_for_hash(payload, key=phase_key)

    def _extract_veto(self, *, phase_key: str, payload: Mapping[str, Any]) -> tuple[bool, str]:
        if phase_key == "phase32_survival_doctrine":
            if bool(payload.get("safety_veto", False)):
                return True, "phase32_safety_veto"
            return False, ""
        if phase_key == "phase34_fund_brain":
            bundle = _safe_mapping(payload.get("bundle", {}))
            if bool(bundle.get("safety_veto", payload.get("safety_veto", False))):
                return True, "phase34_committee_veto"
            return False, ""
        if phase_key == "phase35_institutional_readiness":
            deployment = _safe_mapping(payload.get("deployment_certification", {}))
            stage = str(deployment.get("rollout_stage", deployment.get("stage", "")) or "").lower()
            if stage == "blocked":
                return True, "phase35_rollout_blocked"
            return False, ""
        return False, ""
