from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ShardReplayIdentity:
    shard_id: str
    symbol: str
    status: str
    deterministic: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "shard_id": self.shard_id,
            "symbol": self.symbol,
            "status": self.status,
            "deterministic": bool(self.deterministic),
        }


@dataclass(frozen=True)
class DistributedSimulationContract:
    contract_id: str
    deterministic: bool
    bounded_compute: bool
    timeout_s: float
    partial_failure: bool
    aggregate_identity: str
    shards: tuple[ShardReplayIdentity, ...] = field(default_factory=tuple)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    replay_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "deterministic": bool(self.deterministic),
            "bounded_compute": bool(self.bounded_compute),
            "timeout_s": float(self.timeout_s),
            "partial_failure": bool(self.partial_failure),
            "aggregate_identity": self.aggregate_identity,
            "shards": [row.to_dict() for row in self.shards],
            "reason_codes": [str(item) for item in self.reason_codes],
            "replay_metadata": dict(self.replay_metadata),
        }


class ReplayDistributedBridge:
    """Phase 47 deterministic sharded replay contract bridge."""

    def __init__(self, *, max_shards: int = 8, timeout_s: float = 2.0) -> None:
        self.max_shards = max(1, int(max_shards))
        self.timeout_s = max(0.1, float(timeout_s))

    def compile(
        self,
        *,
        run_id: str,
        symbols: list[str],
        ensemble_payload: Mapping[str, Any] | None,
        compute_health: Mapping[str, Any] | None,
        failed_symbols: list[str] | None = None,
    ) -> DistributedSimulationContract:
        ensemble = _safe_mapping(ensemble_payload)
        health = _safe_mapping(compute_health)
        ordered_symbols = sorted({str(item) for item in symbols if str(item)})[: self.max_shards]
        if not ordered_symbols:
            ordered_symbols = ["GLOBAL"]
        contract_id = _stable_hash(
            {
                "phase": 47,
                "run_id": str(run_id),
                "symbols": ordered_symbols,
                "ensemble_id": str(ensemble.get("ensemble_id", "")),
                "tree_count": int(ensemble.get("tree_limit", 0) or 0),
            }
        )[:24]
        failures = {str(item) for item in (failed_symbols or []) if str(item)}
        shards: list[ShardReplayIdentity] = []
        from autonomous_investment_robot.services.distributed.compute_bridge import deterministic_shard_identity

        for symbol in ordered_symbols:
            shard_id = deterministic_shard_identity(
                run_id=str(run_id),
                symbol=symbol,
                contract_id=contract_id,
            )
            shards.append(
                ShardReplayIdentity(
                    shard_id=shard_id,
                    symbol=symbol,
                    status="failed" if symbol in failures else "ready",
                    deterministic=True,
                )
            )
        partial_failure = any(row.status == "failed" for row in shards)
        reason_codes: list[str] = []
        backend = str(health.get("backend", "local") or "local")
        if backend != "redis_streams":
            reason_codes.append("distributed_backend_unavailable_local_fallback")
        if partial_failure:
            reason_codes.append("partial_shard_failure")
        if not reason_codes:
            reason_codes.append("distributed_contract_ready")
        aggregate_identity = _stable_hash(
            {
                "contract_id": contract_id,
                "shards": [row.shard_id for row in shards],
                "partial_failure": bool(partial_failure),
            }
        )[:24]
        metadata = {
            "ensemble_id": str(ensemble.get("ensemble_id", "")),
            "tree_count": int(len(ensemble.get("trees", []))) if isinstance(ensemble.get("trees", []), list) else 0,
            "backend": backend,
            "max_shards": self.max_shards,
        }
        return DistributedSimulationContract(
            contract_id=contract_id,
            deterministic=True,
            bounded_compute=True,
            timeout_s=self.timeout_s,
            partial_failure=partial_failure,
            aggregate_identity=aggregate_identity,
            shards=tuple(shards),
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            replay_metadata=metadata,
        )
