from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from autonomous_investment_robot.backtest.harness import run_walk_forward_oos


@dataclass
class FeatureRegistryEntry:
    feature_version: str
    keys: list[str]
    created_at: str


class ResearchPlatformService:
    def __init__(self, run_dir: str) -> None:
        self.base = Path(run_dir) / "research"
        self.base.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.base / "feature_registry.json"
        self.experiments_path = self.base / "experiments.jsonl"
        self.nested_wf_path = self.base / "nested_walk_forward.jsonl"

    def register_feature_schema(self, feature_version: str, keys: list[str]) -> FeatureRegistryEntry:
        uniq = sorted({str(k) for k in keys})
        entry = FeatureRegistryEntry(
            feature_version=str(feature_version),
            keys=uniq,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        data = self._load_registry()
        data[entry.feature_version] = {"keys": entry.keys, "created_at": entry.created_at}
        self.registry_path.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
        return entry

    def _load_registry(self) -> dict[str, dict[str, Any]]:
        if not self.registry_path.exists():
            return {}
        try:
            raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def assert_online_offline_parity(self, feature_version: str, online_features: dict[str, float], offline_features: dict[str, float], tolerance: float = 1e-8) -> tuple[bool, list[str]]:
        registry = self._load_registry()
        expected_keys = registry.get(feature_version, {}).get("keys", sorted({*online_features.keys(), *offline_features.keys()}))
        issues: list[str] = []
        for k in expected_keys:
            if k not in online_features:
                issues.append(f"online_missing:{k}")
                continue
            if k not in offline_features:
                issues.append(f"offline_missing:{k}")
                continue
            ov = float(online_features[k])
            fv = float(offline_features[k])
            if abs(ov - fv) > tolerance:
                issues.append(f"value_mismatch:{k}")
        return len(issues) == 0, issues

    def leakage_test(self, feature_ts: datetime, label_ts: datetime) -> tuple[bool, str]:
        if feature_ts > label_ts:
            return False, "feature_leakage_detected"
        return True, "ok"

    def record_experiment(self, name: str, params: dict[str, Any], metrics: dict[str, Any], artifacts: dict[str, Any] | None = None, status: str = "completed") -> str:
        ts = datetime.now(timezone.utc).isoformat()
        payload = {
            "name": name,
            "params": params,
            "metrics": metrics,
            "artifacts": artifacts or {},
            "status": status,
            "ts": ts,
        }
        exp_id = sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        row = {"experiment_id": exp_id, **payload}
        with self.experiments_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        return exp_id

    def nested_walk_forward(
        self,
        prices: list[float],
        *,
        outer_train_ratio: float = 0.7,
        outer_test_ratio: float = 0.2,
        inner_train_ratio: float = 0.6,
        inner_test_ratio: float = 0.2,
    ) -> dict[str, Any]:
        if len(prices) < 80:
            return {
                "outer_splits": 0,
                "allowed": False,
                "reason": "insufficient_samples_nested_wf",
            }
        outer_train = max(40, int(len(prices) * outer_train_ratio))
        outer_test = max(20, int(len(prices) * outer_test_ratio))
        step = outer_test
        idx = 0
        splits: list[dict[str, Any]] = []
        while idx + outer_train + outer_test <= len(prices):
            train_slice = prices[idx : idx + outer_train]
            test_slice = prices[idx + outer_train : idx + outer_train + outer_test]
            inner_train = max(20, int(len(train_slice) * inner_train_ratio))
            inner_test = max(10, int(len(train_slice) * inner_test_ratio))
            inner = run_walk_forward_oos(train_slice, train=inner_train, test=inner_test)
            oos = run_walk_forward_oos(test_slice, train=max(10, int(len(test_slice) * 0.5)), test=max(5, int(len(test_slice) * 0.25)))
            splits.append(
                {
                    "start": idx,
                    "train_len": len(train_slice),
                    "test_len": len(test_slice),
                    "inner": inner,
                    "outer_oos": oos,
                }
            )
            idx += step
        pass_count = len([s for s in splits if bool(s.get("outer_oos", {}).get("gate", {}).get("allowed", False))])
        outer_splits = len(splits)
        pass_ratio = pass_count / max(outer_splits, 1)
        avg_deflated = 0.0
        if outer_splits:
            avg_deflated = sum(float(s.get("outer_oos", {}).get("penalty", {}).get("deflated_sharpe", 0.0)) for s in splits) / outer_splits
        out = {
            "outer_splits": outer_splits,
            "pass_ratio": pass_ratio,
            "avg_deflated_sharpe": avg_deflated,
            "splits": splits,
            "allowed": pass_ratio >= 0.5 and avg_deflated >= -0.1,
            "reason": "nested_wf_pass" if pass_ratio >= 0.5 and avg_deflated >= -0.1 else "nested_wf_fail",
        }
        with self.nested_wf_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(out, sort_keys=True, default=str) + "\n")
        return out

    def robust_oos_gate(
        self,
        nested_result: dict[str, Any],
        *,
        min_outer_splits: int = 2,
        min_pass_ratio: float = 0.5,
        min_avg_deflated_sharpe: float = -0.1,
    ) -> dict[str, Any]:
        outer = int(nested_result.get("outer_splits", 0))
        pass_ratio = float(nested_result.get("pass_ratio", 0.0))
        avg_deflated = float(nested_result.get("avg_deflated_sharpe", -1.0))
        if outer < min_outer_splits:
            return {"allowed": False, "reason": "nested_outer_splits_low", "outer_splits": outer}
        if pass_ratio < min_pass_ratio:
            return {"allowed": False, "reason": "nested_pass_ratio_low", "pass_ratio": pass_ratio}
        if avg_deflated < min_avg_deflated_sharpe:
            return {"allowed": False, "reason": "nested_deflated_sharpe_low", "avg_deflated_sharpe": avg_deflated}
        return {"allowed": True, "reason": "robust_oos_pass", "outer_splits": outer, "pass_ratio": pass_ratio, "avg_deflated_sharpe": avg_deflated}
