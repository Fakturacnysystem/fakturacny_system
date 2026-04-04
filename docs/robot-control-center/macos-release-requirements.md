# macOS Release Requirements

## Goal
Move from debug Tauri .app builds to proper macOS release-grade signed/notarized distribution.

## Required Inputs
- Apple Developer Team ID
- signing certificate(s)
- bundle identifier
- entitlements definition
- notarization credentials
- chosen distribution model:
  - direct distribution
  - internal distribution
  - App Store (if applicable)

## Required Build Modes
### Debug
- local dev
- unsigned acceptable

### Release
- signed
- notarized where required
- reproducible build steps
- clearly separated from debug

## Required Scripts / Automation
Need release workflow for:
- release build
- signing
- notarization submit
- notarization wait/check
- staple
- final artifact export

## Entitlements / Capabilities
Must define:
- filesystem access expectations
- network access expectations
- any Tauri/macOS specific entitlements

## Validation
Need checks for:
- codesign verification
- notarization verification
- bundle ID correctness
- entitlements correctness

## Acceptance Criteria
- release build command documented
- signing inputs consumed from environment/secrets, not hardcoded
- notarization workflow documented and scriptable
- debug and release clearly separated
