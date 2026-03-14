# Universe Control Center Apple App

Native SwiftUI shell for `macOS` and `iPhone`.

## What it does

- loads the live Universe Control Center UI in a native `WKWebView`
- stores the bearer token locally on-device
- polls gateway health and system status natively
- gives one-tap access to Grafana
- works against local gateway or a remote Universe deployment

## Generate the Xcode project

```bash
cd /Users/martinholik/Projects/fakturacny_system/apps/universe-control-center-apple
xcodegen generate
```

## Open in Xcode

```bash
open /Users/martinholik/Projects/fakturacny_system/apps/universe-control-center-apple/UniverseControlCenterApple.xcodeproj
```

## Build from terminal

```bash
/Users/martinholik/Projects/fakturacny_system/scripts/build_universe_apple_app.sh
```

## Default local targets

- gateway: `http://127.0.0.1:8081`
- grafana: `http://127.0.0.1:3000`
- default credentials: `admin / universe-admin`

## Live runtime note

The app shows the same truthful runtime state as the gateway. If the robot is configured for live but safety gates force a paper fallback, the native app will show that actual runtime mode instead of pretending it is live.

## Current blocker

If the script exits with `full Xcode not found`, this machine still has only Command Line Tools. Install the full `Xcode.app` bundle first.
