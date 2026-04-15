# Runtime API Requirements

## Goal
Promote Robot Control Center from artifact/journal-derived desktop state to authoritative backend runtime APIs.

## Required Endpoints

### GET /runtime/summary
Returns top-level runtime state.

Response fields:
- providerId: string
- mode: string
- runId: string
- startedAt: string
- uptimeSec: number
- equityEur: number
- freeCashEur: number
- openPositions: number
- openOrders: number
- avgLatencyMs: number
- wsConnected: boolean
- restHealthy: boolean
- stateKind: "healthy" | "stale" | "degraded" | "partial" | "unavailable" | "error"
- reasonCode?: string
- reasonText?: string
- lastUpdatedAt: string

### GET /runtime/symbols
Returns live symbol/market monitor surface.

Response fields:
- items: array of
  - symbol: string
  - venue: string
  - bid: number
  - ask: number
  - spreadBps: number
  - latencyMs: number
  - qualityScore: number
  - stale: boolean
  - ts: string
- stateKind
- lastUpdatedAt
- reasonCode?
- reasonText?

### GET /runtime/decisions
Returns decision intelligence feed.

Response fields:
- items: array of
  - id: string
  - symbol: string
  - ts: string
  - intent: string
  - confidence: number
  - expectedEdgeBps: number
  - blockers: string[]
  - topReasons: string[]
  - riskVerdict: "allow" | "watch" | "block"
  - lastAction: string
- stateKind
- lastUpdatedAt
- reasonCode?
- reasonText?

### GET /runtime/alerts
Returns alert feed.

Response fields:
- items: array of
  - id: string
  - severity: "info" | "warn" | "critical"
  - module: string
  - message: string
  - ts: string
- stateKind
- lastUpdatedAt

### GET /runtime/health
Returns system/bridge/runtime health.

Response fields:
- status: "good" | "warn" | "danger"
- bridgeHealthy: boolean
- backendHealthy: boolean
- artifactFallbackActive: boolean
- lastUpdatedAt: string
- warnings: string[]
- details: array of
  - label: string
  - value: string
  - severity: "good" | "warn" | "info"

### GET /runtime/integrity
Returns doctrine/risk/integrity surface.

Response fields:
- doctrineStatus: string
- capabilityConfidence: string
- blockers: string[]
- unlockActions: string[]
- warnings: string[]
- degradationState: string
- details: array of
  - label: string
  - value: string
  - severity: "good" | "warn" | "info"
- lastUpdatedAt: string
- stateKind: string

### GET /runtime/replay/:runId
Returns replay contract for selected run.

Response fields:
- runId: string
- timeline: array
- incidents: array
- analogMatches: array
- counterfactuals: array
- pnlAttribution: array
- notes: array
- stateKind: string
- lastUpdatedAt: string

### POST /runtime/control/pause
### POST /runtime/control/resume
### POST /runtime/control/freeze
### POST /runtime/control/flatten
All control endpoints must return:
- accepted: boolean
- rejected: boolean
- status: string
- reasonCode?: string
- operatorMessage: string
- auditReference?: string
- effectiveState: string
- operatorId?: string
- ts: string

### POST /runtime/incident-note
Request:
- runId: string
- operatorId: string
- note: string
- severity?: string
- tags?: string[]

Response:
- accepted: boolean
- noteId?: string
- auditReference?: string
- operatorMessage: string
- ts: string

## Auth Requirement
All POST control and note-writing endpoints require authenticated operator identity.

## Freshness
Every response must include:
- lastUpdatedAt
- stateKind
- reasonCode/reasonText when degraded/unavailable

## Source of Truth
Once these APIs exist, frontend/Tauri bridge should prefer them over artifact-derived fallback paths.
