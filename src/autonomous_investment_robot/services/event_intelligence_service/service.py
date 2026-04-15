from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import (
    AdversarialNarrativeAssessment,
    AssetRelevanceAssessment,
    DataProvenanceEntry,
    EventIntelligenceReport,
    FreshnessNoveltyAssessment,
    MarketImpactAssessment,
    PricedInAssessment,
    SourceTrustAssessment,
)


class SourceTrustService:
    def evaluate(self, *, events: list[dict[str, Any]] | None) -> SourceTrustAssessment:
        events = list(events or [])
        if not events:
            return SourceTrustAssessment(source_count=0, average_trust=0.0, weak_source_ratio=0.0, trusted_sources=[], reasons=["no_event_evidence"], partial=True)
        trust_scores = [max(0.0, min(1.0, float(event.get("trust_score", 0.5)))) for event in events]
        weak = sum(1 for score in trust_scores if score < 0.4)
        trusted = [str(event.get("source", "unknown")) for event, score in zip(events, trust_scores) if score >= 0.6]
        return SourceTrustAssessment(
            source_count=len(events),
            average_trust=sum(trust_scores) / max(len(trust_scores), 1),
            weak_source_ratio=weak / max(len(trust_scores), 1),
            trusted_sources=trusted,
            reasons=[] if weak == 0 else ["weak_sources_present"],
            partial=False,
        )


class FreshnessNoveltyEngine:
    def evaluate(self, *, ts: datetime, events: list[dict[str, Any]] | None, features: dict[str, float] | None) -> FreshnessNoveltyAssessment:
        events = list(events or [])
        if not events:
            novelty_hint = 0.0 if features is None else float(features.get("event_novelty", 0.0) or 0.0)
            return FreshnessNoveltyAssessment(freshness_score=0.0, novelty_score=max(0.0, min(1.0, novelty_hint)), stale_event_ratio=0.0, reasons=["no_event_evidence"], partial=True)
        ages: list[float] = []
        novelty_scores: list[float] = []
        for event in events:
            event_ts = event.get("ts")
            if isinstance(event_ts, str):
                try:
                    event_dt = datetime.fromisoformat(event_ts)
                except Exception:
                    event_dt = ts
            elif isinstance(event_ts, datetime):
                event_dt = event_ts
            else:
                event_dt = ts
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)
            ages.append(max(0.0, (ts - event_dt).total_seconds()))
            novelty_scores.append(max(0.0, min(1.0, float(event.get("novelty", 0.5)))))
        freshness = 1.0 - min(1.0, (sum(ages) / max(len(ages), 1)) / 3600.0)
        stale_ratio = sum(1 for age in ages if age > 1800.0) / max(len(ages), 1)
        return FreshnessNoveltyAssessment(
            freshness_score=max(0.0, min(1.0, freshness)),
            novelty_score=sum(novelty_scores) / max(len(novelty_scores), 1),
            stale_event_ratio=stale_ratio,
            reasons=[] if stale_ratio < 0.5 else ["event_staleness_elevated"],
            partial=False,
        )


class AssetRelevanceMapper:
    def evaluate(self, *, symbol: str, events: list[dict[str, Any]] | None, features: dict[str, float] | None) -> AssetRelevanceAssessment:
        events = list(events or [])
        if not events:
            relevance_hint = 0.0 if features is None else float(features.get("event_relevance", 0.0) or 0.0)
            return AssetRelevanceAssessment(symbol=symbol, relevance_score=max(0.0, min(1.0, relevance_hint)), asset_overlap_score=0.0, reasons=["no_event_evidence"], partial=True)
        scores = []
        overlap_scores = []
        for event in events:
            relevance = float(event.get("relevance", 0.0) or 0.0)
            related = {str(item).upper() for item in event.get("symbols", [])}
            symbol_key = symbol.upper()
            overlap = 1.0 if symbol_key in related else max(0.0, min(1.0, float(event.get("asset_overlap", 0.0) or 0.0)))
            scores.append(max(0.0, min(1.0, relevance if overlap > 0 else relevance * 0.5)))
            overlap_scores.append(overlap)
        return AssetRelevanceAssessment(
            symbol=symbol,
            relevance_score=sum(scores) / max(len(scores), 1),
            asset_overlap_score=sum(overlap_scores) / max(len(overlap_scores), 1),
            reasons=[] if max(overlap_scores, default=0.0) > 0 else ["symbol_match_missing"],
            partial=False,
        )


class MarketImpactInterpreter:
    def evaluate(self, *, events: list[dict[str, Any]] | None, features: dict[str, float] | None, forecast: Any | None) -> MarketImpactAssessment:
        events = list(events or [])
        feature_impact = 0.0 if features is None else float(features.get("event_impact_score", 0.0) or 0.0)
        sentiment = 0.0 if features is None else float(features.get("event_sentiment", 0.0) or 0.0)
        if events:
            impacts = [max(-1.0, min(1.0, float(event.get("impact_score", 0.0) or 0.0))) for event in events]
            sentiment = sum(max(-1.0, min(1.0, float(event.get("sentiment", 0.0) or 0.0))) for event in events) / max(len(events), 1)
            feature_impact = sum(abs(score) for score in impacts) / max(len(impacts), 1)
        expected_move_bps = 0.0 if forecast is None else abs(float(getattr(forecast, "mu", 0.0) or 0.0)) * 10000.0
        return MarketImpactAssessment(
            impact_score=max(0.0, min(1.0, feature_impact)),
            sentiment_score=max(-1.0, min(1.0, sentiment)),
            expected_move_bps=expected_move_bps,
            reasons=[] if feature_impact <= 0.0 else ["event_market_impact_detected"],
            partial=not bool(events),
        )


class PricedInProbabilityEngine:
    def evaluate(self, *, features: dict[str, float] | None, impact: MarketImpactAssessment, freshness: FreshnessNoveltyAssessment) -> PricedInAssessment:
        aligned_move = 0.0 if features is None else abs(float(features.get("event_price_move_alignment", 0.0) or 0.0))
        priced_in = max(0.0, min(1.0, 0.45 * aligned_move + 0.35 * impact.impact_score + 0.2 * freshness.freshness_score))
        action = "continue"
        reasons: list[str] = []
        if priced_in >= 0.75:
            action = "no_trade"
            reasons.append("event_priced_in")
        elif priced_in >= 0.55:
            action = "trade_smaller"
            reasons.append("event_partially_priced_in")
        return PricedInAssessment(priced_in_probability=priced_in, recommended_action=action, reasons=reasons, partial=freshness.partial and impact.partial)


class AdversarialNewsFilter:
    def evaluate(self, *, events: list[dict[str, Any]] | None, source_trust: SourceTrustAssessment, freshness: FreshnessNoveltyAssessment) -> AdversarialNarrativeAssessment:
        events = list(events or [])
        manipulation_scores = [max(0.0, min(1.0, float(event.get("manipulation_risk", 0.0) or 0.0))) for event in events]
        manipulation = sum(manipulation_scores) / max(len(manipulation_scores), 1) if manipulation_scores else 0.0
        adversarial_risk = max(manipulation, min(1.0, 0.6 * source_trust.weak_source_ratio + 0.4 * freshness.novelty_score))
        action = "continue"
        reasons: list[str] = []
        if adversarial_risk >= 0.7:
            action = "no_trade"
            reasons.append("adversarial_narrative_risk_high")
        elif adversarial_risk >= 0.45:
            action = "wait"
            reasons.append("adversarial_narrative_risk_elevated")
        return AdversarialNarrativeAssessment(adversarial_risk=adversarial_risk, recommended_action=action, reasons=reasons, partial=not bool(events))


class DataProvenanceLedger:
    def record(
        self,
        *,
        symbol: str,
        ts: datetime,
        events: list[dict[str, Any]] | None,
        source_trust: SourceTrustAssessment,
        freshness: FreshnessNoveltyAssessment,
        relevance: AssetRelevanceAssessment,
        impact: MarketImpactAssessment,
        priced_in: PricedInAssessment,
        adversarial: AdversarialNarrativeAssessment,
    ) -> DataProvenanceEntry:
        events = list(events or [])
        completeness = 0.0
        if events:
            completeness = max(0.0, min(1.0, 0.25 * (1.0 - source_trust.weak_source_ratio) + 0.25 * freshness.freshness_score + 0.25 * relevance.relevance_score + 0.25 * (1.0 - adversarial.adversarial_risk)))
        reasons = []
        if not events:
            reasons.append("no_event_evidence")
        if source_trust.weak_source_ratio > 0.4:
            reasons.append("weak_source_mix")
        if freshness.stale_event_ratio > 0.5:
            reasons.append("stale_event_mix")
        return DataProvenanceEntry(
            symbol=symbol,
            ts=ts,
            event_count=len(events),
            provenance_completeness=completeness,
            trusted_sources=list(source_trust.trusted_sources),
            reasons=reasons,
            partial=not bool(events),
            metadata={
                "source_trust": source_trust.__dict__,
                "freshness": freshness.__dict__,
                "relevance": relevance.__dict__,
                "impact": impact.__dict__,
                "priced_in": priced_in.__dict__,
                "adversarial": adversarial.__dict__,
            },
        )


class EventIntelligenceService:
    def __init__(self) -> None:
        self.source_trust = SourceTrustService()
        self.freshness = FreshnessNoveltyEngine()
        self.relevance = AssetRelevanceMapper()
        self.impact = MarketImpactInterpreter()
        self.priced_in = PricedInProbabilityEngine()
        self.adversarial = AdversarialNewsFilter()
        self.provenance = DataProvenanceLedger()

    def evaluate(
        self,
        *,
        symbol: str,
        ts: datetime,
        features: dict[str, float] | None,
        forecast: Any | None,
        events: list[dict[str, Any]] | None = None,
    ) -> EventIntelligenceReport:
        source_trust = self.source_trust.evaluate(events=events)
        freshness = self.freshness.evaluate(ts=ts, events=events, features=features)
        relevance = self.relevance.evaluate(symbol=symbol, events=events, features=features)
        impact = self.impact.evaluate(events=events, features=features, forecast=forecast)
        priced_in = self.priced_in.evaluate(features=features, impact=impact, freshness=freshness)
        adversarial = self.adversarial.evaluate(events=events, source_trust=source_trust, freshness=freshness)
        provenance = self.provenance.record(
            symbol=symbol,
            ts=ts,
            events=events,
            source_trust=source_trust,
            freshness=freshness,
            relevance=relevance,
            impact=impact,
            priced_in=priced_in,
            adversarial=adversarial,
        )
        trust_gap_risk = 0.0 if source_trust.source_count <= 0 else max(0.0, 1.0 - source_trust.average_trust) * 0.6
        overall_risk = max(
            priced_in.priced_in_probability,
            adversarial.adversarial_risk,
            trust_gap_risk,
        )
        recommended_action = "continue"
        recommended_size_multiplier = 1.0
        reasons: list[str] = []
        if adversarial.recommended_action == "no_trade":
            recommended_action = "no_trade"
            recommended_size_multiplier = 0.0
            reasons.extend(adversarial.reasons)
        elif priced_in.recommended_action == "no_trade":
            recommended_action = "no_trade"
            recommended_size_multiplier = 0.0
            reasons.extend(priced_in.reasons)
        elif adversarial.recommended_action == "wait":
            recommended_action = "wait"
            recommended_size_multiplier = 0.0
            reasons.extend(adversarial.reasons)
        elif priced_in.recommended_action == "trade_smaller":
            recommended_action = "trade_smaller"
            recommended_size_multiplier = 0.5
            reasons.extend(priced_in.reasons)
        elif source_trust.weak_source_ratio > 0.5:
            recommended_action = "trade_smaller"
            recommended_size_multiplier = 0.6
            reasons.append("weak_source_mix")
        partial = provenance.partial
        if partial:
            reasons.append("partial_event_intelligence")
        return EventIntelligenceReport(
            symbol=symbol,
            ts=ts,
            recommended_action=recommended_action,
            overall_risk_score=max(0.0, min(1.0, overall_risk)),
            recommended_size_multiplier=recommended_size_multiplier,
            source_trust=source_trust,
            freshness_novelty=freshness,
            asset_relevance=relevance,
            market_impact=impact,
            priced_in=priced_in,
            adversarial=adversarial,
            provenance=provenance,
            reasons=reasons,
            partial=partial,
            metadata={
                "heuristic": True,
                "event_count": 0 if events is None else len(events),
                "trust_gap_risk": trust_gap_risk,
            },
        )
