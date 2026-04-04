# Auth Integration Requirements

## Goal
Introduce real operator identity, session persistence, and provenance for control actions and incident workflows.

## Required Capabilities

### Operator Identity
The system must support:
- operatorId: stable unique ID
- displayName: human-readable name
- role: e.g. operator, admin, observer
- authSource: e.g. local, SSO, token
- sessionId: active session identifier

### Session Lifecycle
Need:
- login/init
- session restore on app relaunch
- logout/clear session
- expiry handling
- invalid session handling

### Storage
Preferred macOS/local desktop storage:
- secure local storage or platform-safe secret storage
- session metadata available to frontend shell
- no plaintext credential leakage in repo

### Propagation
Operator identity must propagate to:
- control actions
- incident note writes
- audit records
- topbar/session display
- diagnostics context

### CLI / Bridge Propagation
Bridge/control layer must be able to pass:
- operatorId
- sessionId
- displayName or role where needed
into command execution/audit context.

## Required UI Surfaces
- topbar session display
- control center provenance display
- incident note attribution
- diagnostics auth/session visibility
- unavailable/expired session states

## Failure Modes
Must explicitly handle:
- missing session
- expired session
- invalid token/session
- local storage corruption
- auth provider unavailable

## Acceptance Criteria
- operator identity persists across relaunch
- destructive commands include operator provenance
- incident notes include operator attribution
- session state is visible and explicit
- unauthenticated control actions are blocked safely
