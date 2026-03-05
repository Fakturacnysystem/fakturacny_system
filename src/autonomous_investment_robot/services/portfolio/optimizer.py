from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OptimizationResult:
    weights: dict[str, float]
    turnover: float
    cluster_exposure: dict[str, float]
    score_by_symbol: dict[str, float]


class PortfolioOptimizerService:
    def _correlation_haircut(self, symbol: str, corr: dict[str, dict[str, float]]) -> float:
        row = corr.get(symbol, {})
        if not row:
            return 1.0
        vals = [abs(float(v)) for k, v in row.items() if k != symbol]
        if not vals:
            return 1.0
        avg_corr = sum(vals) / len(vals)
        return max(0.25, 1.0 - min(0.75, avg_corr * 0.8))

    def _score_symbol(
        self,
        *,
        edge_bps: float,
        realized_vol: float,
        spread_bps: float,
        depth_notional: float,
        liquidity_score: float,
        corr_haircut: float,
    ) -> float:
        edge = max(0.0, float(edge_bps))
        vol_bps = max(0.5, float(realized_vol) * 10000.0)
        spread = max(0.0, float(spread_bps))
        depth_bonus = min(1.6, (max(0.0, depth_notional) ** 0.5) / 800.0)
        liq = max(0.2, min(2.0, float(liquidity_score)))
        risk_adjusted = (edge / (vol_bps + 2.0)) * liq
        spread_penalty = 1.0 + spread / 25.0
        return max(0.0, risk_adjusted * (1.0 + depth_bonus) * corr_haircut / spread_penalty)

    def _apply_cluster_caps(
        self,
        weights: dict[str, float],
        *,
        candidates: dict[str, dict[str, float | str]],
        cluster_caps: dict[str, float],
    ) -> dict[str, float]:
        constrained = dict(weights)
        cluster_exposure: dict[str, float] = {}
        for symbol, w in constrained.items():
            cluster = str(candidates[symbol].get("cluster", "default") or "default")
            cluster_exposure[cluster] = cluster_exposure.get(cluster, 0.0) + w
        for cluster, exposure in cluster_exposure.items():
            cap = float(cluster_caps.get(cluster, 1.0))
            if cap <= 0.0:
                for symbol in constrained:
                    if str(candidates[symbol].get("cluster", "default") or "default") == cluster:
                        constrained[symbol] = 0.0
                continue
            if exposure > cap:
                scale = cap / max(exposure, 1e-9)
                for symbol in constrained:
                    if str(candidates[symbol].get("cluster", "default") or "default") == cluster:
                        constrained[symbol] *= scale

        # Re-distribute residual weight only into clusters with available cap headroom.
        for _ in range(4):
            total = sum(constrained.values())
            residual = max(0.0, 1.0 - total)
            if residual <= 1e-9:
                break
            cluster_exposure = {}
            for symbol, w in constrained.items():
                cluster = str(candidates[symbol].get("cluster", "default") or "default")
                cluster_exposure[cluster] = cluster_exposure.get(cluster, 0.0) + w
            eligible: list[str] = []
            for symbol in constrained:
                cluster = str(candidates[symbol].get("cluster", "default") or "default")
                cap = float(cluster_caps.get(cluster, 1.0))
                if cluster_exposure.get(cluster, 0.0) < cap - 1e-9:
                    eligible.append(symbol)
            if not eligible:
                break
            base = sum(max(constrained[s], 1e-6) for s in eligible)
            for symbol in eligible:
                cluster = str(candidates[symbol].get("cluster", "default") or "default")
                cap = float(cluster_caps.get(cluster, 1.0))
                headroom = max(0.0, cap - cluster_exposure.get(cluster, 0.0))
                alloc = min(residual * (max(constrained[symbol], 1e-6) / max(base, 1e-9)), headroom)
                constrained[symbol] += alloc

        total = sum(constrained.values())
        if total > 1.0 + 1e-9:
            constrained = {k: max(0.0, v / total) for k, v in constrained.items()}
        return constrained

    def optimize(
        self,
        candidates: dict[str, dict[str, float | str]],
        *,
        corr: dict[str, dict[str, float]] | None = None,
        current_weights: dict[str, float] | None = None,
        turnover_penalty: float = 0.35,
        cluster_caps: dict[str, float] | None = None,
    ) -> OptimizationResult:
        corr = corr or {}
        current_weights = current_weights or {}
        cluster_caps = cluster_caps or {}
        turnover_penalty = max(0.0, min(0.95, float(turnover_penalty)))

        raw_scores: dict[str, float] = {}
        for symbol, row in candidates.items():
            corr_haircut = self._correlation_haircut(symbol, corr)
            raw_scores[symbol] = self._score_symbol(
                edge_bps=float(row.get("edge_bps", 0.0) or 0.0),
                realized_vol=float(row.get("realized_vol", 0.0) or 0.0),
                spread_bps=float(row.get("spread_bps", 0.0) or 0.0),
                depth_notional=float(row.get("depth_notional", 0.0) or 0.0),
                liquidity_score=float(row.get("liquidity_score", 1.0) or 1.0),
                corr_haircut=corr_haircut,
            )

        total_score = sum(raw_scores.values())
        if total_score <= 0.0:
            weights = {k: 0.0 for k in candidates}
            return OptimizationResult(weights=weights, turnover=0.0, cluster_exposure={}, score_by_symbol=raw_scores)

        base_weights = {k: v / total_score for k, v in raw_scores.items()}

        # Risk budgeting by inverse volatility to avoid concentration in noisy symbols.
        inv_vol: dict[str, float] = {}
        for symbol, row in candidates.items():
            rv = max(1e-6, float(row.get("realized_vol", 0.0) or 0.0))
            inv_vol[symbol] = min(12.0, 1.0 / rv)
        total_inv = sum(base_weights[s] * inv_vol[s] for s in base_weights)
        risk_budgeted = {
            s: 0.0 if total_inv <= 0.0 else (base_weights[s] * inv_vol[s]) / total_inv
            for s in base_weights
        }

        constrained = self._apply_cluster_caps(risk_budgeted, candidates=candidates, cluster_caps=cluster_caps)

        # Turnover penalty smooths transitions against current allocation.
        blended = {}
        for symbol, new_w in constrained.items():
            prev_w = float(current_weights.get(symbol, 0.0) or 0.0)
            blended[symbol] = (1.0 - turnover_penalty) * new_w + turnover_penalty * prev_w

        norm = sum(blended.values())
        if norm > 0.0:
            blended = {k: max(0.0, v / norm) for k, v in blended.items()}

        blended = self._apply_cluster_caps(blended, candidates=candidates, cluster_caps=cluster_caps)

        turnover = sum(abs(float(current_weights.get(s, 0.0) or 0.0) - blended.get(s, 0.0)) for s in set(current_weights) | set(blended))
        cluster_out: dict[str, float] = {}
        for symbol, w in blended.items():
            cluster = str(candidates[symbol].get("cluster", "default") or "default")
            cluster_out[cluster] = cluster_out.get(cluster, 0.0) + w

        return OptimizationResult(
            weights=blended,
            turnover=turnover,
            cluster_exposure=cluster_out,
            score_by_symbol=raw_scores,
        )
