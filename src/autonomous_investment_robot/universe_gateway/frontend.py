from __future__ import annotations

import json


def render_command_center_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>Universe Control Center</title>
  <meta name="theme-color" content="#071018" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="apple-mobile-web-app-title" content="Universe" />
  <link rel="manifest" href="/ui/manifest.webmanifest" />
  <link rel="icon" href="/ui/assets/icon-192.png" sizes="192x192" />
  <link rel="apple-touch-icon" href="/ui/assets/apple-touch-icon.png" />
  <style>
    :root {
      --bg-0: #030710;
      --bg-1: #07111b;
      --bg-2: #0d1f31;
      --panel: rgba(7, 17, 30, 0.74);
      --panel-strong: rgba(7, 18, 32, 0.92);
      --panel-soft: rgba(8, 24, 37, 0.58);
      --line: rgba(122, 205, 255, 0.14);
      --line-strong: rgba(122, 205, 255, 0.3);
      --text: #ecf7ff;
      --muted: #8faac0;
      --accent: #67e4ff;
      --accent-2: #7efeb5;
      --accent-3: #ffbd6b;
      --danger: #ff6f82;
      --shadow: 0 26px 90px rgba(0, 0, 0, 0.38);
      --radius-xl: 28px;
      --radius-lg: 22px;
      --radius-md: 16px;
      --radius-sm: 12px;
      --display: "Iowan Old Style", "Palatino Linotype", serif;
      --sans: "Avenir Next", "Segoe UI", sans-serif;
      --mono: "SFMono-Regular", "Menlo", monospace;
      --capital-glow: 0.52;
      --risk-glow: 0.18;
      --profit-hue: 188;
      --timeline-height: 184px;
      --shell-scale: 1;
    }

    * {
      box-sizing: border-box;
      -webkit-tap-highlight-color: transparent;
    }

    html, body {
      margin: 0;
      min-height: 100%;
      background:
        radial-gradient(circle at 10% 12%, rgba(103, 228, 255, 0.18), transparent 24%),
        radial-gradient(circle at 92% 4%, rgba(255, 111, 130, 0.12), transparent 24%),
        radial-gradient(circle at 50% 100%, rgba(126, 254, 181, 0.1), transparent 28%),
        linear-gradient(180deg, var(--bg-2) 0%, var(--bg-1) 38%, var(--bg-0) 100%);
      color: var(--text);
      font-family: var(--sans);
    }

    body::before,
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      z-index: 0;
    }

    body::before {
      background-image:
        linear-gradient(rgba(255, 255, 255, 0.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
      background-size: 46px 46px;
      mask-image: radial-gradient(circle at center, black 34%, transparent 88%);
      opacity: 0.46;
    }

    body::after {
      background:
        conic-gradient(from 180deg at 50% 50%, transparent 0deg, rgba(103, 228, 255, 0.05) 88deg, transparent 180deg, rgba(126, 254, 181, 0.04) 264deg, transparent 360deg);
      animation: atmosphere-spin 26s linear infinite;
      opacity: 0.45;
    }

    body.present-mode .sidebar,
    body.present-mode .rail,
    body.present-mode .timeline {
      display: none;
    }

    body.present-mode .app-shell {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: 88px minmax(0, 1fr);
      --shell-scale: 1.02;
    }

    body.present-mode .topbar,
    body.present-mode .content-panel {
      grid-column: 1 / 2;
    }

    body.present-mode .content-panel {
      grid-row: 2 / 3;
    }

    a {
      color: inherit;
      text-decoration: none;
    }

    button,
    input,
    select {
      font: inherit;
      color: inherit;
    }

    .app-shell {
      position: relative;
      z-index: 1;
      min-height: 100vh;
      display: grid;
      grid-template-columns: 114px minmax(0, 1fr) 360px;
      grid-template-rows: 88px minmax(0, 1fr) var(--timeline-height);
      gap: 16px;
      padding: 16px;
      transform: scale(var(--shell-scale));
      transform-origin: top center;
    }

    .topbar,
    .sidebar,
    .rail,
    .timeline,
    .content-panel,
    .mobile-dock,
    .command-palette {
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      backdrop-filter: blur(20px);
    }

    .topbar,
    .sidebar,
    .rail,
    .timeline,
    .mobile-dock,
    .content-panel,
    .command-palette {
      border-radius: var(--radius-xl);
    }

    .topbar {
      grid-column: 1 / 4;
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(320px, 1fr) auto;
      align-items: center;
      gap: 18px;
      padding: 18px 22px;
    }

    .brand {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }

    .brand h1 {
      margin: 0;
      font-family: var(--display);
      font-size: clamp(28px, 3.2vw, 42px);
      letter-spacing: 0.02em;
      line-height: 1;
    }

    .brand p,
    .nav-caption,
    .section-eyebrow,
    .eyebrow,
    .command-meta {
      margin: 0;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-size: 11px;
    }

    .mission-strip {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      min-width: 0;
    }

    .mission-chip,
    .mini-card,
    .signal-card,
    .insight-card {
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.035);
      border: 1px solid rgba(255, 255, 255, 0.06);
      padding: 12px 14px;
      min-width: 0;
    }

    .mission-chip label,
    .mini-card label,
    .signal-card label,
    .insight-card label,
    .metric label,
    .mini-stat label,
    .rail-stat label,
    .timeline-card label,
    .event-card label,
    .session-card label,
    .module-card label,
    .strategy-row label,
    .table-row label,
    .field label {
      display: block;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 10px;
      margin-bottom: 8px;
    }

    .mission-chip strong,
    .mini-card strong,
    .signal-card strong,
    .insight-card strong {
      display: block;
      font-size: 18px;
      line-height: 1.1;
    }

    .mission-chip span,
    .mini-card span,
    .signal-card span,
    .insight-card span {
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }

    .topbar-right {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 10px;
      min-width: 0;
    }

    .pill,
    .soft-chip,
    .socket-pill,
    .keycap {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      min-height: 38px;
      padding: 0 14px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      font-size: 13px;
      white-space: nowrap;
    }

    .pill .dot,
    .soft-chip .dot,
    .socket-pill .dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--accent-2);
      box-shadow: 0 0 14px currentColor;
      color: var(--accent-2);
    }

    .pill.warn .dot,
    .soft-chip.warn .dot,
    .socket-pill.warn .dot {
      background: var(--accent-3);
      color: var(--accent-3);
    }

    .pill.danger .dot,
    .soft-chip.danger .dot,
    .socket-pill.danger .dot {
      background: var(--danger);
      color: var(--danger);
    }

    .button,
    .ghost-button,
    .nav-button,
    .install-button,
    .action-button {
      cursor: pointer;
      border: 0;
      transition: transform 180ms ease, border-color 180ms ease, background 180ms ease, box-shadow 180ms ease, opacity 180ms ease;
    }

    .button,
    .install-button,
    .action-button.primary {
      border-radius: 14px;
      padding: 12px 16px;
      background: linear-gradient(135deg, rgba(103, 228, 255, 0.96), rgba(126, 254, 181, 0.94));
      color: #041017;
      font-weight: 700;
      box-shadow: 0 14px 34px rgba(103, 228, 255, 0.22);
    }

    .ghost-button,
    .action-button {
      border-radius: 14px;
      padding: 12px 16px;
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }

    .button:hover,
    .ghost-button:hover,
    .nav-button:hover,
    .install-button:hover,
    .action-button:hover {
      transform: translateY(-1px);
    }

    .button:disabled,
    .ghost-button:disabled,
    .install-button:disabled,
    .action-button:disabled {
      opacity: 0.55;
      cursor: default;
      transform: none;
    }

    .sidebar {
      grid-row: 2 / 3;
      display: flex;
      flex-direction: column;
      padding: 14px 12px;
      gap: 10px;
      overflow: hidden;
    }

    .nav-stack {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .nav-button {
      width: 100%;
      text-align: left;
      padding: 12px 10px;
      border-radius: 16px;
      color: var(--muted);
      background: transparent;
      border: 1px solid transparent;
      line-height: 1.25;
      font-size: 13px;
    }

    .nav-button.active {
      color: var(--text);
      border-color: rgba(103, 228, 255, 0.28);
      background: linear-gradient(135deg, rgba(103, 228, 255, 0.12), rgba(126, 254, 181, 0.08));
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.03);
    }

    .sidebar-footer {
      margin-top: auto;
      display: grid;
      gap: 10px;
    }

    .content-panel {
      grid-column: 2 / 3;
      grid-row: 2 / 3;
      padding: 18px;
      overflow: auto;
      min-height: 0;
    }

    .view {
      display: none;
      min-height: 100%;
      animation: fade-up 280ms cubic-bezier(0.2, 0.8, 0.2, 1);
    }

    .view.active {
      display: block;
    }

    .view-grid,
    .hero-grid,
    .capital-grid,
    .brain-grid,
    .split-grid,
    .diagnostic-grid,
    .three-grid,
    .two-grid,
    .brief-grid,
    .signal-grid,
    .action-grid,
    .connection-grid {
      display: grid;
      gap: 16px;
    }

    .hero-grid {
      grid-template-columns: minmax(0, 1.18fr) minmax(340px, 0.82fr);
      align-items: stretch;
    }

    .brief-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .signal-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .action-grid,
    .connection-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .brain-grid,
    .three-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .two-grid,
    .capital-grid,
    .split-grid,
    .diagnostic-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .content-card {
      position: relative;
      overflow: hidden;
      border-radius: var(--radius-lg);
      padding: 18px;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.01)),
        linear-gradient(135deg, rgba(103, 228, 255, 0.06), rgba(255, 255, 255, 0));
      border: 1px solid rgba(255, 255, 255, 0.06);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }

    .content-card::before {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.05), transparent);
      transform: translateX(-100%);
      animation: shimmer 9s linear infinite;
      pointer-events: none;
      opacity: 0.45;
    }

    .content-card > * {
      position: relative;
      z-index: 1;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 16px;
    }

    .card-title {
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-width: 0;
    }

    .card-title h2,
    .card-title h3,
    .card-title h4,
    .scene-title h2 {
      margin: 0;
      font-size: 13px;
      line-height: 1.15;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--muted);
    }

    .card-title p,
    .scene-title p,
    .card-title strong {
      margin: 0;
      font-family: var(--display);
      line-height: 1.06;
    }

    .card-title strong {
      font-size: clamp(24px, 2.2vw, 34px);
    }

    .scene-title p {
      font-size: clamp(28px, 3.4vw, 46px);
    }

    .metric-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }

    .metric {
      padding: 14px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.05);
      min-width: 0;
    }

    .metric strong {
      display: block;
      font-size: clamp(20px, 2.6vw, 34px);
      line-height: 1;
    }

    .metric span {
      display: block;
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.45;
    }

    .core-scene {
      position: relative;
      min-height: 520px;
      padding: 24px;
      overflow: hidden;
      background:
        radial-gradient(circle at 50% 42%, rgba(103, 228, 255, calc(0.16 + var(--capital-glow) * 0.18)), transparent 22%),
        radial-gradient(circle at 50% 70%, rgba(126, 254, 181, calc(0.10 + var(--capital-glow) * 0.08)), transparent 34%),
        linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
    }

    .core-scene::after {
      content: "";
      position: absolute;
      inset: 16px;
      border-radius: 22px;
      border: 1px solid rgba(103, 228, 255, 0.08);
      pointer-events: none;
    }

    .scene-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
    }

    .scene-subcopy {
      display: grid;
      gap: 12px;
      max-width: 320px;
    }

    .scene-subcopy p {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
      font-size: 13px;
    }

    .core-stage {
      position: absolute;
      inset: 112px 20px 120px;
      display: grid;
      place-items: center;
      overflow: hidden;
    }

    .orbits,
    .orbits::before,
    .orbits::after,
    .risk-shell,
    .pulse-ring,
    .market-ring,
    .beam,
    .energy-dust,
    .energy-dust::before,
    .energy-dust::after {
      position: absolute;
      border-radius: 50%;
      pointer-events: none;
    }

    .orbits {
      width: min(60vw, 360px);
      aspect-ratio: 1;
      border: 1px solid rgba(103, 228, 255, 0.13);
      animation: orbit-spin 24s linear infinite;
    }

    .orbits::before,
    .orbits::after {
      content: "";
      inset: 0;
      border: 1px solid rgba(255,255,255,0.06);
    }

    .orbits::before {
      inset: 24px;
      animation: orbit-spin-reverse 18s linear infinite;
    }

    .orbits::after {
      inset: 58px;
      border-color: rgba(255, 189, 107, 0.18);
      animation: pulse-ring 4s ease-in-out infinite;
    }

    .risk-shell {
      width: min(66vw, 400px);
      aspect-ratio: 1;
      border: 1px solid rgba(255, 111, 130, calc(0.08 + var(--risk-glow) * 0.32));
      box-shadow: 0 0 42px rgba(255, 111, 130, calc(0.06 + var(--risk-glow) * 0.18));
      animation: shield-breathe 3.6s ease-in-out infinite;
    }

    .pulse-ring {
      width: min(72vw, 440px);
      aspect-ratio: 1;
      border: 1px solid rgba(126, 254, 181, 0.12);
      animation: pulse-ring 5s ease-in-out infinite;
    }

    .market-ring {
      width: min(80vw, 500px);
      aspect-ratio: 1;
      border: 1px dashed rgba(103, 228, 255, 0.12);
      animation: orbit-spin 38s linear infinite;
    }

    .capital-core {
      position: relative;
      width: min(42vw, 240px);
      aspect-ratio: 1;
      border-radius: 50%;
      background:
        radial-gradient(circle at 35% 30%, rgba(255,255,255,0.84), transparent 16%),
        radial-gradient(circle at 50% 50%, hsla(var(--profit-hue), 100%, 68%, calc(0.46 + var(--capital-glow) * 0.28)), rgba(7, 23, 32, 0.9) 72%);
      box-shadow:
        0 0 0 14px rgba(255, 255, 255, 0.02),
        0 0 60px rgba(103, 228, 255, calc(0.18 + var(--capital-glow) * 0.20)),
        0 0 140px rgba(126, 254, 181, calc(0.08 + var(--capital-glow) * 0.18));
      animation: core-breathe 4.4s ease-in-out infinite;
      overflow: hidden;
    }

    .capital-core::before,
    .capital-core::after {
      content: "";
      position: absolute;
      inset: 0;
      border-radius: 50%;
    }

    .capital-core::before {
      background: radial-gradient(circle at 50% 55%, transparent 35%, rgba(255,255,255,0.12) 70%, transparent 78%);
      animation: orbit-spin 12s linear infinite;
    }

    .capital-core::after {
      background: linear-gradient(180deg, rgba(255,255,255,0.14), transparent 36%, rgba(0,0,0,0.2) 100%);
      mix-blend-mode: screen;
    }

    .energy-dust,
    .energy-dust::before,
    .energy-dust::after {
      width: 8px;
      height: 8px;
      background: rgba(126, 254, 181, 0.66);
      box-shadow: 0 0 16px rgba(126, 254, 181, 0.55);
    }

    .energy-dust {
      top: 28%;
      left: 16%;
      animation: drift 11s linear infinite;
    }

    .energy-dust::before {
      content: "";
      top: 240px;
      left: 360px;
      background: rgba(103, 228, 255, 0.72);
      animation: drift 8s linear infinite reverse;
    }

    .energy-dust::after {
      content: "";
      top: 110px;
      left: 250px;
      width: 6px;
      height: 6px;
      background: rgba(255, 189, 107, 0.72);
      animation: drift 10s linear infinite;
    }

    .core-value {
      position: absolute;
      inset: auto 0 36px;
      text-align: center;
      z-index: 3;
    }

    .core-value strong {
      display: block;
      font-size: clamp(34px, 6vw, 72px);
      line-height: 0.95;
      font-family: var(--display);
    }

    .beam {
      height: 2px;
      background: linear-gradient(90deg, transparent, rgba(103, 228, 255, 0.96), rgba(126, 254, 181, 0.72), transparent);
      filter: drop-shadow(0 0 10px rgba(103, 228, 255, 0.45));
      transform-origin: left center;
      animation: beam-sweep 4.8s ease-in-out infinite;
      opacity: 0.65;
      border-radius: 999px;
    }

    .beam.beam-a {
      width: 260px;
      top: 36%;
      left: 8%;
      transform: rotate(-14deg);
    }

    .beam.beam-b {
      width: 180px;
      top: 58%;
      right: 8%;
      transform: rotate(18deg);
      animation-delay: -1.8s;
    }

    .scene-footer {
      position: absolute;
      left: 24px;
      right: 24px;
      bottom: 22px;
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      z-index: 2;
    }

    .mini-stat {
      min-width: 0;
      border-radius: 14px;
      padding: 12px 14px;
      background: rgba(5, 14, 24, 0.58);
      border: 1px solid rgba(255,255,255,0.06);
    }

    .mini-stat strong {
      display: block;
      font-size: 22px;
      line-height: 1;
    }

    .mini-stat span {
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .list-stack,
    .module-stack,
    .timeline-stream,
    .session-stack,
    .event-stack,
    .table-stack,
    .insight-stack,
    .event-lane {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .strategy-row,
    .module-card,
    .timeline-card,
    .session-card,
    .event-card,
    .table-row,
    .insight-card,
    .signal-card {
      border-radius: 16px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
      padding: 14px;
      min-width: 0;
    }

    .strategy-head,
    .row-head,
    .module-head,
    .session-head,
    .event-head,
    .signal-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-width: 0;
    }

    .progress-track,
    .bar-track,
    .health-rail {
      margin-top: 10px;
      height: 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.06);
      overflow: hidden;
    }

    .bar-fill,
    .progress-fill,
    .health-fill {
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      box-shadow: 0 0 16px rgba(103, 228, 255, 0.24);
      transform-origin: left center;
      animation: fill-rise 0.7s ease;
    }

    .badge,
    .score-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 10px;
      border-radius: 999px;
      font-size: 11px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.03);
      white-space: nowrap;
    }

    .badge.warn,
    .score-pill.warn {
      color: var(--accent-3);
      border-color: rgba(255, 189, 107, 0.22);
      background: rgba(255, 189, 107, 0.08);
    }

    .badge.danger,
    .score-pill.danger {
      color: var(--danger);
      border-color: rgba(255, 111, 130, 0.26);
      background: rgba(255, 111, 130, 0.09);
    }

    .badge.ok,
    .score-pill.ok {
      color: var(--accent-2);
      border-color: rgba(126, 254, 181, 0.2);
      background: rgba(126, 254, 181, 0.08);
    }

    .muted { color: var(--muted); }
    .mono { font-family: var(--mono); }
    .text-success { color: var(--accent-2); }
    .text-warning { color: var(--accent-3); }
    .text-danger { color: var(--danger); }

    .realtime-fabric {
      display: grid;
      gap: 10px;
    }

    .socket-pill {
      justify-content: space-between;
      width: 100%;
      min-height: 42px;
      border-radius: 16px;
    }

    .socket-pill strong {
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }

    .socket-pill span:last-child {
      font-size: 13px;
    }

    .signal-grid .signal-card strong {
      font-size: 22px;
    }

    .insight-stack .insight-card strong {
      font-family: var(--display);
      font-size: 22px;
    }

    .shield-visual {
      position: relative;
      min-height: 260px;
      display: grid;
      place-items: center;
      overflow: hidden;
      border-radius: 22px;
      background: radial-gradient(circle at center, rgba(255,111,130,0.12), transparent 38%), rgba(255,255,255,0.02);
      border: 1px solid rgba(255, 111, 130, 0.12);
    }

    .shield-visual .shield-core {
      width: 150px;
      height: 150px;
      border-radius: 38% 62% 56% 44% / 42% 48% 52% 58%;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.18), rgba(255, 111, 130, 0.22));
      border: 1px solid rgba(255,255,255,0.12);
      box-shadow: 0 0 38px rgba(255,111,130,0.16);
      animation: shield-breathe 3.2s ease-in-out infinite;
    }

    .shield-visual .shield-ring {
      position: absolute;
      width: 240px;
      height: 240px;
      border-radius: 50%;
      border: 1px solid rgba(255,111,130,0.18);
      animation: pulse-ring 5s ease-in-out infinite;
    }

    .rail {
      grid-column: 3 / 4;
      grid-row: 2 / 3;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      overflow: auto;
      min-height: 0;
    }

    .rail-card {
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
    }

    .rail-card h3 {
      margin: 0 0 12px;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.16em;
      color: var(--muted);
    }

    .rail-stats {
      display: grid;
      gap: 10px;
    }

    .rail-stat {
      border-radius: 14px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.05);
      padding: 12px 14px;
    }

    .rail-stat strong {
      display: block;
      font-size: 28px;
      line-height: 1;
    }

    .auth-grid,
    .field,
    .link-list {
      display: grid;
      gap: 10px;
    }

    .field input {
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.035);
      padding: 13px 14px;
      outline: none;
    }

    .field input:focus {
      border-color: rgba(103,228,255,0.32);
      box-shadow: 0 0 0 3px rgba(103,228,255,0.08);
    }

    .auth-actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }

    .link-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.05);
    }

    .link-row p,
    .link-row strong,
    .table-row p,
    .table-row strong,
    .timeline-card p,
    .event-card p,
    .session-card p,
    .module-card p,
    .strategy-row p,
    .insight-card p,
    .signal-card p {
      margin: 0;
    }

    .timeline {
      grid-column: 1 / 4;
      grid-row: 3 / 4;
      padding: 16px 18px;
      overflow: hidden;
    }

    .timeline-header {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 14px;
    }

    .timeline-stream {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
      height: calc(var(--timeline-height) - 66px);
      overflow: auto;
      padding-right: 4px;
    }

    .timeline-card strong,
    .event-card strong,
    .session-card strong,
    .module-card strong,
    .strategy-row strong,
    .table-row strong,
    .insight-card strong,
    .signal-card strong {
      line-height: 1.25;
    }

    .table-wrap {
      overflow: auto;
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.02);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 640px;
    }

    th,
    td {
      padding: 12px 14px;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }

    th {
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 10px;
    }

    tr:last-child td {
      border-bottom: 0;
    }

    .empty-state {
      padding: 18px;
      border-radius: 16px;
      border: 1px dashed rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.02);
      color: var(--muted);
    }

    .mobile-dock {
      display: none;
      position: sticky;
      bottom: 10px;
      z-index: 5;
      margin: 0 10px 10px;
      padding: 8px;
      gap: 8px;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      background: rgba(7, 18, 32, 0.92);
    }

    .mobile-dock button {
      border-radius: 14px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--muted);
      padding: 12px 8px;
      font-size: 11px;
    }

    .mobile-dock button.active {
      color: var(--text);
      background: linear-gradient(135deg, rgba(103, 228, 255, 0.12), rgba(126, 254, 181, 0.08));
      border-color: rgba(103, 228, 255, 0.28);
    }

    .install-hint {
      font-size: 12px;
      color: var(--muted);
      line-height: 1.55;
    }

    .command-palette {
      position: fixed;
      right: 20px;
      bottom: 20px;
      z-index: 8;
      padding: 14px;
      width: min(340px, calc(100vw - 24px));
      display: grid;
      gap: 10px;
    }

    .command-palette-header {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
    }

    .command-palette-actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .keycap {
      min-height: 30px;
      padding: 0 10px;
      font-size: 11px;
      color: var(--muted);
    }

    @keyframes fade-up {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @keyframes shimmer {
      0% { transform: translateX(-100%); }
      18%, 100% { transform: translateX(100%); }
    }

    @keyframes atmosphere-spin {
      from { transform: rotate(0deg) scale(1.1); }
      to { transform: rotate(360deg) scale(1.1); }
    }

    @keyframes orbit-spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }

    @keyframes orbit-spin-reverse {
      from { transform: rotate(360deg); }
      to { transform: rotate(0deg); }
    }

    @keyframes core-breathe {
      0%, 100% { transform: scale(0.97); }
      50% { transform: scale(1.03); }
    }

    @keyframes shield-breathe {
      0%, 100% { transform: scale(0.97); }
      50% { transform: scale(1.035); }
    }

    @keyframes pulse-ring {
      0%, 100% { transform: scale(0.92); opacity: 0.22; }
      50% { transform: scale(1.04); opacity: 0.44; }
    }

    @keyframes beam-sweep {
      0%, 100% { opacity: 0.12; transform: scaleX(0.6) rotate(-14deg); }
      50% { opacity: 0.82; transform: scaleX(1) rotate(-14deg); }
    }

    @keyframes fill-rise {
      from { transform: scaleX(0.18); opacity: 0.4; }
      to { transform: scaleX(1); opacity: 1; }
    }

    @keyframes drift {
      0% { transform: translate3d(0, 0, 0) scale(0.8); opacity: 0.2; }
      35% { transform: translate3d(30px, -36px, 0) scale(1.1); opacity: 0.8; }
      70% { transform: translate3d(-26px, 22px, 0) scale(0.9); opacity: 0.4; }
      100% { transform: translate3d(0, 0, 0) scale(0.8); opacity: 0.2; }
    }

    @media (max-width: 1520px) {
      .app-shell {
        grid-template-columns: 108px minmax(0, 1fr) 334px;
      }
      .topbar {
        grid-template-columns: minmax(0, 1.1fr) minmax(280px, 1fr) auto;
      }
      .hero-grid {
        grid-template-columns: 1fr;
      }
    }

    @media (max-width: 1180px) {
      .app-shell {
        grid-template-columns: minmax(0, 1fr);
        grid-template-rows: auto auto minmax(0, 1fr) auto auto;
        padding-bottom: 110px;
      }
      .topbar,
      .content-panel,
      .rail,
      .timeline {
        grid-column: 1 / 2;
      }
      .topbar { grid-row: 1 / 2; }
      .content-panel { grid-row: 3 / 4; }
      .rail { grid-row: 4 / 5; }
      .timeline { grid-row: 5 / 6; }
      .sidebar {
        display: none;
      }
      .mobile-dock {
        display: grid;
      }
      .topbar {
        grid-template-columns: 1fr;
        align-items: start;
      }
      .brief-grid,
      .brain-grid,
      .three-grid,
      .two-grid,
      .capital-grid,
      .split-grid,
      .diagnostic-grid,
      .metric-grid,
      .scene-footer,
      .auth-actions,
      .signal-grid,
      .action-grid,
      .connection-grid,
      .mission-strip {
        grid-template-columns: 1fr 1fr;
      }
      .command-palette {
        right: 12px;
        bottom: 80px;
      }
      body.present-mode .app-shell {
        grid-template-rows: auto minmax(0, 1fr);
      }
    }

    @media (max-width: 760px) {
      .app-shell {
        padding: 12px;
        gap: 12px;
        --timeline-height: 240px;
      }
      .topbar,
      .content-panel,
      .rail,
      .timeline {
        padding: 14px;
      }
      .topbar-right {
        justify-content: flex-start;
      }
      .brief-grid,
      .brain-grid,
      .three-grid,
      .two-grid,
      .capital-grid,
      .split-grid,
      .diagnostic-grid,
      .metric-grid,
      .scene-footer,
      .auth-actions,
      .signal-grid,
      .action-grid,
      .connection-grid,
      .mission-strip,
      .command-palette-actions {
        grid-template-columns: 1fr;
      }
      .core-scene {
        min-height: 560px;
      }
      .core-stage {
        inset: 142px 12px 150px;
      }
      .core-value strong {
        font-size: 46px;
      }
      .timeline-stream {
        grid-template-columns: 1fr;
      }
      .mobile-dock {
        margin: 0 6px 8px;
      }
      .command-palette {
        left: 12px;
        right: 12px;
        width: auto;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: 1ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 1ms !important;
        scroll-behavior: auto !important;
      }
    }
  </style>
</head>
<body>
  <div class="app-shell" id="app-shell">
    <header class="topbar">
      <div class="brand">
        <h1>Universe Control Center</h1>
        <p>Capital Core / Autonomous Trading Intelligence / Realtime Operating Surface</p>
      </div>

      <div class="mission-strip">
        <div class="mission-chip">
          <label>Mission</label>
          <strong id="mission-strip-title">Operator visibility stabilizing</strong>
          <span id="mission-strip-body">Connect to the gateway to hydrate the live model, realtime channels and capital surface.</span>
        </div>
        <div class="mission-chip">
          <label>System Truth</label>
          <strong id="truth-score">0 live feeds</strong>
          <span id="truth-score-note">REST and websocket truth matrix is not online yet.</span>
        </div>
        <div class="mission-chip">
          <label>Live Focus</label>
          <strong id="focus-line">Awaiting runtime telemetry</strong>
          <span id="focus-line-note">When data arrives, this strip will summarize the highest-signal operator context.</span>
        </div>
      </div>

      <div class="topbar-right">
        <div class="pill" id="mode-pill"><span class="dot"></span><span>Mode: loading</span></div>
        <div class="pill" id="health-pill"><span class="dot"></span><span>Health: loading</span></div>
        <div class="pill" id="sync-pill"><span class="dot"></span><span>Sync: booting</span></div>
        <div class="pill"><span class="dot"></span><span id="clock-pill">--:--:-- UTC</span></div>
        <button class="ghost-button" id="present-button">Present Mode</button>
      </div>
    </header>

    <aside class="sidebar">
      <div class="nav-caption">Navigation</div>
      <div class="nav-stack">
        <button class="nav-button active" data-view="command">Command Center</button>
        <button class="nav-button" data-view="brain">Brain</button>
        <button class="nav-button" data-view="shield">Shield</button>
        <button class="nav-button" data-view="execution">Execution</button>
        <button class="nav-button" data-view="capital">Capital</button>
        <button class="nav-button" data-view="simulation">Simulation</button>
        <button class="nav-button" data-view="audit">Audit</button>
      </div>
      <div class="sidebar-footer">
        <div class="mini-card">
          <label>Keyboard</label>
          <strong>1-7 navigate</strong>
          <span>R refreshes, C connects, P toggles present mode.</span>
        </div>
        <div class="mini-card">
          <label>Session</label>
          <strong id="sidebar-session">Stored token absent</strong>
          <span id="sidebar-session-note">Authenticate to unlock live contract views.</span>
        </div>
      </div>
    </aside>

    <main class="content-panel">
      <section class="view active" data-view-panel="command">
        <div class="hero-grid">
          <article class="content-card core-scene">
            <div class="scene-header">
              <div class="scene-title">
                <h2>Capital Core</h2>
                <p id="core-headline">Truthful telemetry under live system load.</p>
              </div>
              <div class="scene-subcopy">
                <div class="score-pill" id="mission-pill">Mission syncing</div>
                <p id="command-summary">This surface never invents state. It only amplifies what the robot has actually emitted.</p>
              </div>
            </div>
            <div class="core-stage">
              <div class="beam beam-a"></div>
              <div class="beam beam-b"></div>
              <div class="pulse-ring"></div>
              <div class="risk-shell"></div>
              <div class="market-ring"></div>
              <div class="orbits"></div>
              <div class="energy-dust"></div>
              <div class="capital-core"></div>
              <div class="core-value">
                <label>Equity</label>
                <strong id="capital-equity">$0.00</strong>
              </div>
            </div>
            <div class="scene-footer">
              <div class="mini-stat"><label>Profit</label><strong id="capital-profit">$0.00</strong><span id="capital-profit-note">No realized edge yet.</span></div>
              <div class="mini-stat"><label>Drawdown</label><strong id="capital-drawdown">0.00%</strong><span id="capital-drawdown-note">Shield standing by.</span></div>
              <div class="mini-stat"><label>Survivability</label><strong id="capital-survivability">100.0</strong><span id="capital-survivability-note">Capital shell intact.</span></div>
              <div class="mini-stat"><label>Exposure</label><strong id="capital-allocation">0.00</strong><span id="capital-allocation-note">No live exposure.</span></div>
            </div>
          </article>

          <div class="view-grid">
            <article class="content-card">
              <div class="card-header">
                <div class="card-title">
                  <h2>Mission Brief</h2>
                  <strong id="mission-brief-title">System is waiting for operator sign-in.</strong>
                  <p id="mission-brief-body">Once authenticated, this card condenses the highest-value narrative from capital, decision, risk and execution state.</p>
                </div>
                <div class="badge" id="command-brief-badge">standby</div>
              </div>
              <div class="brief-grid">
                <div class="mini-card">
                  <label>Best Current Read</label>
                  <strong id="brief-best-read">No live edge yet</strong>
                  <span id="brief-best-read-note">Connect REST and websocket surfaces.</span>
                </div>
                <div class="mini-card">
                  <label>Risk Posture</label>
                  <strong id="brief-risk-posture">Unknown</strong>
                  <span id="brief-risk-note">Audit state not hydrated yet.</span>
                </div>
                <div class="mini-card">
                  <label>Execution Lane</label>
                  <strong id="brief-execution-posture">Cold</strong>
                  <span id="brief-execution-note">No submission telemetry in memory.</span>
                </div>
                <div class="mini-card">
                  <label>Confidence Window</label>
                  <strong id="brief-confidence">0.00</strong>
                  <span id="brief-confidence-note">Decision confidence pending.</span>
                </div>
              </div>
            </article>

            <article class="content-card">
              <div class="card-header">
                <div class="card-title">
                  <h2>Latest Decision</h2>
                  <p id="decision-title">Waiting for authenticated decision telemetry.</p>
                </div>
                <div class="score-pill" id="decision-confidence-pill">0.00</div>
              </div>
              <div class="list-stack">
                <div class="strategy-row">
                  <label>Action</label>
                  <div class="row-head">
                    <strong id="decision-action">No decision packet received yet.</strong>
                    <div class="badge" id="decision-strategy-badge">strategy pending</div>
                  </div>
                  <p class="muted" id="decision-reason">Connect and authenticate to load runtime telemetry plus websocket state.</p>
                </div>
                <div class="metric-grid">
                  <div class="metric"><label>Provider</label><strong id="provider-value">unknown</strong><span id="provider-note">No runtime provider</span></div>
                  <div class="metric"><label>Decision ticks</label><strong id="decision-tick-count">0</strong><span id="decision-tick-note">Waiting for snapshot</span></div>
                  <div class="metric"><label>Reject rate</label><strong id="reject-rate">0%</strong><span id="reject-rate-note">Execution baseline</span></div>
                </div>
              </div>
            </article>

            <article class="content-card">
              <div class="card-header">
                <div class="card-title">
                  <h2>Live Signal Board</h2>
                  <p>Fast operator readout optimized for sub-2-second scanning</p>
                </div>
                <div class="badge" id="runtime-symbol-badge">symbol pending</div>
              </div>
              <div class="signal-grid">
                <div class="signal-card"><label>Mode</label><strong id="summary-mode">Paper</strong><span id="summary-mode-note">staging</span></div>
                <div class="signal-card"><label>Orders</label><strong id="summary-orders">0</strong><span id="summary-orders-note">submitted</span></div>
                <div class="signal-card"><label>Fills</label><strong id="summary-fills">0</strong><span id="summary-fills-note">confirmed</span></div>
                <div class="signal-card"><label>Latency</label><strong id="summary-latency">0.0 ms</strong><span id="summary-latency-note">execution p50</span></div>
                <div class="signal-card"><label>Risk Gate</label><strong id="summary-gate">unknown</strong><span id="summary-gate-note">audit gate</span></div>
                <div class="signal-card"><label>Simulation</label><strong id="summary-scenarios">0</strong><span id="summary-scenarios-note">scenarios</span></div>
              </div>
            </article>

            <article class="content-card">
              <div class="card-header">
                <div class="card-title">
                  <h2>Strategy Arena</h2>
                  <p>Published runtime allocations and confidence bands</p>
                </div>
                <div class="badge" id="strategy-count-badge">0 rows</div>
              </div>
              <div class="list-stack" id="strategy-stack">
                <div class="empty-state">No runtime strategy parliament votes have been published yet.</div>
              </div>
            </article>
          </div>
        </div>

        <div class="two-grid" style="margin-top:16px;">
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Operator Insights</h2>
                <p>Derived from current truthful runtime state, not fabricated forecasts</p>
              </div>
              <div class="badge" id="insight-count-badge">0 signals</div>
            </div>
            <div class="insight-stack" id="insight-stack">
              <div class="empty-state">Connect to produce live operator insights.</div>
            </div>
          </article>
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Command Actions</h2>
                <p>Useful operator shortcuts without leaving the control surface</p>
              </div>
              <div class="badge" id="command-action-badge">ready</div>
            </div>
            <div class="action-grid">
              <button class="action-button primary" id="action-refresh">Refresh Read Models</button>
              <button class="action-button" id="action-reconnect">Reconnect Sockets</button>
              <button class="action-button" id="action-grafana">Open Grafana</button>
              <button class="action-button" id="action-raw-api">Open Raw Telemetry</button>
            </div>
            <div style="margin-top:14px;" class="install-hint" id="command-action-note">Actions stay read-only unless the underlying backend endpoint performs a safe read.</div>
          </article>
        </div>
      </section>

      <section class="view" data-view-panel="brain">
        <div class="split-grid">
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Cognitive Modules</h2>
                <p>Influence and confidence mapped from live runtime state</p>
              </div>
              <div class="badge" id="brain-updated-badge">waiting</div>
            </div>
            <div class="module-stack" id="brain-module-stack">
              <div class="empty-state">No module diagnostics loaded yet.</div>
            </div>
          </article>
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Decision Pulse</h2>
                <p>How the robot is currently thinking</p>
              </div>
              <div class="score-pill" id="brain-score-pill">0.00</div>
            </div>
            <div class="list-stack">
              <div class="strategy-row">
                <label>Current stance</label>
                <div class="row-head">
                  <strong id="brain-current-strategy">No active strategy published.</strong>
                  <div class="badge" id="brain-current-action">hold</div>
                </div>
                <p class="muted" id="brain-current-reason">Awaiting runtime decision event.</p>
              </div>
              <div class="strategy-row">
                <label>Deep diagnostics</label>
                <p class="muted" id="brain-deep-diagnostics">Module health, governance confidence and simulation pressure will aggregate here once the read models hydrate.</p>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="view" data-view-panel="shield">
        <div class="split-grid">
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Shield Layer</h2>
                <p>Capital protection, readiness and invariant integrity</p>
              </div>
              <div class="badge" id="shield-status-badge">unknown</div>
            </div>
            <div class="shield-visual">
              <div class="shield-ring"></div>
              <div class="shield-core"></div>
            </div>
          </article>
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Risk / Governance</h2>
                <p>Directly tied to runtime audit state</p>
              </div>
              <div class="badge" id="audit-stage-badge">staging</div>
            </div>
            <div class="metric-grid">
              <div class="metric"><label>System</label><strong id="audit-system-state">unknown</strong><span id="audit-system-note">runtime state</span></div>
              <div class="metric"><label>Invariants</label><strong id="audit-invariants">unknown</strong><span id="audit-invariants-note">hard checks</span></div>
              <div class="metric"><label>Drift</label><strong id="audit-drift">unknown</strong><span id="audit-drift-note">state drift</span></div>
              <div class="metric"><label>Gate</label><strong id="audit-gate">unknown</strong><span id="audit-gate-note">release gate</span></div>
              <div class="metric"><label>Readiness</label><strong id="audit-stage">unknown</strong><span id="audit-stage-note">operational stage</span></div>
              <div class="metric"><label>Survival</label><strong id="shield-survival">100.0</strong><span id="shield-survival-note">capital survivability</span></div>
            </div>
          </article>
        </div>
        <div class="split-grid" style="margin-top:16px;">
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Telemetry Distribution</h2>
                <p>Most frequent live event families</p>
              </div>
            </div>
            <div class="list-stack" id="telemetry-distribution-stack">
              <div class="empty-state">No telemetry distribution yet.</div>
            </div>
          </article>
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Compliance / Harmony</h2>
                <p>Guardrail configuration surfaced from live reports</p>
              </div>
            </div>
            <div class="list-stack">
              <div class="strategy-row"><label>Compliance</label><strong id="compliance-state">unknown</strong><p class="muted" id="compliance-reason">No compliance report loaded.</p></div>
              <div class="strategy-row"><label>Harmony</label><strong id="harmony-mode">unknown</strong><p class="muted" id="harmony-note">No harmony report loaded.</p></div>
            </div>
          </article>
        </div>
      </section>

      <section class="view" data-view-panel="execution">
        <div class="two-grid">
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Execution Radar</h2>
                <p>Submission, fills, latency and slippage</p>
              </div>
              <div class="badge" id="execution-health-badge">monitoring</div>
            </div>
            <div class="metric-grid">
              <div class="metric"><label>Submitted</label><strong id="exec-submitted">0</strong><span id="exec-submitted-note">orders</span></div>
              <div class="metric"><label>Filled</label><strong id="exec-filled">0</strong><span id="exec-filled-note">fills</span></div>
              <div class="metric"><label>Blocked</label><strong id="exec-blocked">0</strong><span id="exec-blocked-note">blocked</span></div>
              <div class="metric"><label>Rejected</label><strong id="exec-rejected">0</strong><span id="exec-rejected-note">rejected</span></div>
              <div class="metric"><label>Latency</label><strong id="exec-latency">0.0 ms</strong><span id="exec-latency-note">p50/p95 runtime</span></div>
              <div class="metric"><label>Slippage</label><strong id="exec-slippage">0.00 bps</strong><span id="exec-slippage-note">modeled vs realized</span></div>
            </div>
          </article>
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Order Flow</h2>
                <p>Latest submission surface</p>
              </div>
            </div>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Reason</th><th>Notional</th></tr></thead>
                <tbody id="orders-table-body"><tr><td colspan="5" class="muted">No order telemetry yet.</td></tr></tbody>
              </table>
            </div>
          </article>
        </div>
        <article class="content-card" style="margin-top:16px;">
          <div class="card-header">
            <div class="card-title">
              <h2>Fill Tape</h2>
              <p>Confirmed fills from the trading ledger</p>
            </div>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Fee</th></tr></thead>
              <tbody id="fills-table-body"><tr><td colspan="6" class="muted">No fills recorded.</td></tr></tbody>
            </table>
          </div>
        </article>
      </section>

      <section class="view" data-view-panel="capital">
        <div class="two-grid">
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Capital Ledger</h2>
                <p>Equity, pnl and live allocation envelope</p>
              </div>
            </div>
            <div class="metric-grid">
              <div class="metric"><label>Equity</label><strong id="capital-view-equity">$0.00</strong><span id="capital-view-equity-note">latest report row</span></div>
              <div class="metric"><label>PnL</label><strong id="capital-view-pnl">$0.00</strong><span id="capital-view-pnl-note">net after fees</span></div>
              <div class="metric"><label>Drawdown</label><strong id="capital-view-dd">0.00%</strong><span id="capital-view-dd-note">signed / report</span></div>
              <div class="metric"><label>Exposure</label><strong id="capital-view-exposure">0.00</strong><span id="capital-view-exposure-note">notional quote</span></div>
            </div>
          </article>
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Performance Readout</h2>
                <p>Operator-level financial posture</p>
              </div>
            </div>
            <div class="list-stack">
              <div class="strategy-row"><label>Performance note</label><strong id="capital-performance-headline">Capital core stable.</strong><p class="muted" id="capital-performance-note">Waiting for stronger live PnL movement.</p></div>
              <div class="strategy-row"><label>Position count</label><strong id="capital-position-count">0 open positions</strong><p class="muted" id="capital-position-note">Exposure details below.</p></div>
            </div>
          </article>
        </div>
        <article class="content-card" style="margin-top:16px;">
          <div class="card-header">
            <div class="card-title">
              <h2>Position State</h2>
              <p>Directly from the trading ledger</p>
            </div>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Time</th><th>Symbol</th><th>Qty</th><th>Entry</th><th>Mark</th><th>Unrealized</th><th>Realized</th></tr></thead>
              <tbody id="positions-table-body"><tr><td colspan="7" class="muted">No positions in ledger.</td></tr></tbody>
            </table>
          </div>
        </article>
      </section>

      <section class="view" data-view-panel="simulation">
        <div class="two-grid">
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Future Simulation</h2>
                <p>Scenario tree inferred from current capital and risk posture</p>
              </div>
              <div class="badge" id="scenario-count-badge">0 scenarios</div>
            </div>
            <div class="list-stack" id="scenario-stack">
              <div class="empty-state">No scenario graph is available yet.</div>
            </div>
          </article>
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Replay Lab</h2>
                <p>Deterministic sessions available for inspection</p>
              </div>
            </div>
            <div class="session-stack" id="replay-session-stack">
              <div class="empty-state">No replay sessions found in this run directory.</div>
            </div>
          </article>
        </div>
      </section>

      <section class="view" data-view-panel="audit">
        <div class="two-grid">
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Governance State</h2>
                <p>Readiness, gates and invariant posture</p>
              </div>
            </div>
            <div class="list-stack">
              <div class="strategy-row"><label>Runtime</label><strong id="audit-view-system">unknown</strong><p class="muted" id="audit-view-system-note">No runtime audit yet.</p></div>
              <div class="strategy-row"><label>Gate</label><strong id="audit-view-gate">unknown</strong><p class="muted" id="audit-view-gate-note">Release gate state</p></div>
              <div class="strategy-row"><label>Readiness</label><strong id="audit-view-stage">unknown</strong><p class="muted" id="audit-view-stage-note">Operational posture</p></div>
            </div>
          </article>
          <article class="content-card">
            <div class="card-header">
              <div class="card-title">
                <h2>Configuration / Diagnostics</h2>
                <p>Runtime diagnostics from distributed and LLM layers</p>
              </div>
            </div>
            <div class="list-stack">
              <div class="strategy-row"><label>Distributed runtime</label><strong id="distributed-state">unknown</strong><p class="muted" id="distributed-note">Waiting for diagnostics.</p></div>
              <div class="strategy-row"><label>Meta intelligence</label><strong id="llm-state">unknown</strong><p class="muted" id="llm-note">Waiting for diagnostics.</p></div>
            </div>
          </article>
        </div>
        <article class="content-card" style="margin-top:16px;">
          <div class="card-header">
            <div class="card-title">
              <h2>Recent Audit / Telemetry Events</h2>
              <p>Latest archived events rendered for operators and analysts</p>
            </div>
          </div>
          <div class="event-stack" id="audit-event-stack">
            <div class="empty-state">No audit events loaded yet.</div>
          </div>
        </article>
      </section>
    </main>

    <aside class="rail">
      <section class="rail-card">
        <h3>Operator Access</h3>
        <div class="auth-grid">
          <div class="soft-chip" id="auth-state-pill"><span class="dot"></span><span id="auth-state">Not signed in</span></div>
          <div class="field"><label for="auth-user">Username</label><input id="auth-user" type="text" value="admin" autocomplete="username" /></div>
          <div class="field"><label for="auth-pass">Password</label><input id="auth-pass" type="password" value="universe-admin" autocomplete="current-password" /></div>
          <div class="auth-actions">
            <button class="button" id="connect-button">Connect</button>
            <button class="ghost-button" id="refresh-button">Refresh</button>
          </div>
          <div class="install-hint" id="auth-hint">Bearer token is stored only in browser local storage for this device.</div>
        </div>
      </section>

      <section class="rail-card">
        <h3>Realtime Fabric</h3>
        <div class="realtime-fabric">
          <div class="socket-pill warn" id="socket-capital"><div><strong>Capital WS</strong></div><div><span class="dot"></span><span id="socket-capital-text">offline</span></div></div>
          <div class="socket-pill warn" id="socket-decisions"><div><strong>Decision WS</strong></div><div><span class="dot"></span><span id="socket-decisions-text">offline</span></div></div>
          <div class="socket-pill warn" id="socket-execution"><div><strong>Execution WS</strong></div><div><span class="dot"></span><span id="socket-execution-text">offline</span></div></div>
          <div class="socket-pill warn" id="socket-risk"><div><strong>Risk WS</strong></div><div><span class="dot"></span><span id="socket-risk-text">offline</span></div></div>
          <div class="socket-pill warn" id="socket-telemetry"><div><strong>Telemetry WS</strong></div><div><span class="dot"></span><span id="socket-telemetry-text">offline</span></div></div>
          <div class="socket-pill warn" id="socket-simulation"><div><strong>Simulation WS</strong></div><div><span class="dot"></span><span id="socket-simulation-text">offline</span></div></div>
        </div>
      </section>

      <section class="rail-card">
        <h3>Diagnostics Rail</h3>
        <div class="rail-stats">
          <div class="rail-stat"><label>Execution</label><strong id="rail-execution">0 / 0</strong><span class="muted" id="rail-execution-note">filled / submitted</span></div>
          <div class="rail-stat"><label>Latency</label><strong id="rail-latency">0.0 ms</strong><span class="muted" id="rail-latency-note">slippage 0.00 bps</span></div>
          <div class="rail-stat"><label>Shield</label><strong id="rail-shield">unknown</strong><span class="muted" id="rail-shield-note">readiness unknown</span></div>
          <div class="rail-stat"><label>Simulation</label><strong id="rail-simulation">0</strong><span class="muted" id="rail-simulation-note">branches pending</span></div>
        </div>
      </section>

      <section class="rail-card">
        <h3>Install App</h3>
        <div class="install-hint" id="install-hint">This interface is installable on macOS and iPhone as a web app. Use the button below or Safari's Add to Dock / Add to Home Screen.</div>
        <div style="margin-top:12px;"><button class="install-button" id="install-button">Install Universe App</button></div>
      </section>

      <section class="rail-card">
        <h3>Live Links</h3>
        <div class="link-list">
          <a class="link-row" href="http://127.0.0.1:3000" target="_blank" rel="noreferrer"><div><strong>Grafana</strong><p class="muted">Prometheus-backed runtime dashboard</p></div><span class="badge">Open</span></a>
          <a class="link-row" href="http://127.0.0.1:9090" target="_blank" rel="noreferrer"><div><strong>Prometheus</strong><p class="muted">Raw scrape targets and time-series inspection</p></div><span class="badge">Open</span></a>
          <a class="link-row" href="http://127.0.0.1:9011" target="_blank" rel="noreferrer"><div><strong>MinIO Console</strong><p class="muted">Replay bundles and long-horizon artifacts</p></div><span class="badge">Open</span></a>
        </div>
      </section>
    </aside>

    <section class="timeline">
      <div class="timeline-header">
        <div class="card-title">
          <h3>Bottom Timeline</h3>
          <p>Event Stream</p>
        </div>
        <a class="badge" href="http://127.0.0.1:8081/api/telemetry/events" target="_blank" rel="noreferrer">Open raw telemetry API</a>
      </div>
      <div class="timeline-stream" id="timeline-stream">
        <div class="timeline-card">
          <label>Bootstrapping</label>
          <strong>Waiting for authenticated state pull and realtime subscriptions.</strong>
          <p class="muted">The system will populate once REST and websocket channels are online.</p>
          <div class="badge">/api/* + /ws/*</div>
        </div>
      </div>
    </section>
  </div>

  <nav class="mobile-dock" id="mobile-dock">
    <button class="active" data-view="command">Command</button>
    <button data-view="brain">Brain</button>
    <button data-view="shield">Shield</button>
    <button data-view="execution">Exec</button>
    <button data-view="capital">Capital</button>
  </nav>

  <section class="command-palette" id="command-palette">
    <div class="command-palette-header">
      <div>
        <div class="command-meta">Quick Controls</div>
        <strong id="command-palette-title">Fast operator actions</strong>
      </div>
      <div class="keycap">P present</div>
    </div>
    <div class="command-palette-actions">
      <button class="action-button primary" id="palette-refresh">Refresh</button>
      <button class="action-button" id="palette-connect">Reconnect</button>
      <button class="action-button" id="palette-grafana">Grafana</button>
      <button class="action-button" id="palette-api">Raw API</button>
    </div>
  </section>

  <script>
    const state = {
      token: localStorage.getItem("universe.token") || "",
      currentView: "command",
      sockets: {},
      socketStatus: {
        capital: "offline",
        decisions: "offline",
        execution: "offline",
        risk: "offline",
        telemetry: "offline",
        simulation: "offline"
      },
      timeline: [],
      deferredInstall: null,
      data: {
        status: null,
        system: null,
        environment: null,
        capital: null,
        decision: null,
        modules: [],
        strategies: [],
        execution: null,
        orders: [],
        fills: [],
        positions: [],
        telemetryEvents: [],
        telemetryDist: [],
        audit: null,
        scenarios: [],
        replaySessions: [],
        compliance: null,
        harmony: null,
        distributed: null,
        llm: null
      }
    };

    const $ = (id) => document.getElementById(id);
    const els = {
      modePill: $("mode-pill"),
      healthPill: $("health-pill"),
      syncPill: $("sync-pill"),
      clock: $("clock-pill"),
      authState: $("auth-state"),
      authStatePill: $("auth-state-pill"),
      authHint: $("auth-hint"),
      strategyStack: $("strategy-stack"),
      brainModuleStack: $("brain-module-stack"),
      telemetryDistributionStack: $("telemetry-distribution-stack"),
      ordersTableBody: $("orders-table-body"),
      fillsTableBody: $("fills-table-body"),
      positionsTableBody: $("positions-table-body"),
      scenarioStack: $("scenario-stack"),
      replaySessionStack: $("replay-session-stack"),
      auditEventStack: $("audit-event-stack"),
      timelineStream: $("timeline-stream"),
      insightStack: $("insight-stack")
    };

    const navButtons = [...document.querySelectorAll("[data-view]")];
    const viewPanels = [...document.querySelectorAll("[data-view-panel]")];
    const appShell = $("app-shell");
    const body = document.body;

    const authHeaders = () => (state.token ? { Authorization: `Bearer ${state.token}` } : {});

    const parseTime = (value) => {
      if (value === null || value === undefined || value === "") return null;
      if (typeof value === "number") return new Date(value < 1e12 ? value * 1000 : value);
      if (/^\\d+(\\.\\d+)?$/.test(String(value))) {
        const num = Number(value);
        return new Date(num < 1e12 ? num * 1000 : num);
      }
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? null : date;
    };

    const fmtTime = (value) => {
      const parsed = parseTime(value);
      if (!parsed) return String(value || "no timestamp");
      return parsed.toLocaleString();
    };

    const fmtMoney = (value) => {
      const num = Number(value || 0);
      return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(num);
    };

    const fmtCompact = (value) => {
      const num = Number(value || 0);
      return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 2 }).format(num);
    };

    const fmtPct = (value) => `${Number(value || 0).toFixed(2)}%`;
    const fmtNum = (value, digits = 2) => Number(value || 0).toFixed(digits);
    const text = (id, value) => { const el = $(id); if (el) el.textContent = value; };

    const setTone = (element, tone, textValue) => {
      if (!element) return;
      element.classList.remove("warn", "danger", "ok");
      if (tone) element.classList.add(tone);
      const span = element.querySelector("span:last-child") || element.lastElementChild;
      if (span && textValue !== undefined) span.textContent = textValue;
    };

    const statusTone = (value) => {
      const raw = String(value || "unknown").toLowerCase();
      if (["ok", "healthy", "running", "operational", "open", "clean", "connected", "online", "authorized"].includes(raw)) return "ok";
      if (["blocked", "error", "fatal", "tripped", "danger", "failed", "offline"].includes(raw)) return "danger";
      if (["warn", "warning", "staging", "fallback", "degraded", "unknown", "waiting", "idle"].includes(raw)) return "warn";
      return "";
    };

    const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

    const truthCount = () => Object.values(state.socketStatus).filter((value) => value === "online").length + (state.token ? 1 : 0);

    const timelinePush = (item) => {
      state.timeline.unshift(item);
      state.timeline = state.timeline.slice(0, 16);
      renderTimeline();
    };

    const renderTimeline = () => {
      if (!state.timeline.length) {
        els.timelineStream.innerHTML = '<div class="timeline-card"><label>Idle</label><strong>No timeline events yet.</strong><p class="muted">The system is waiting for refresh cycles or websocket frames.</p><div class="badge">standby</div></div>';
        return;
      }
      els.timelineStream.innerHTML = state.timeline.map((item) => `
        <div class="timeline-card">
          <label>${item.channel}</label>
          <strong>${item.title}</strong>
          <p class="muted">${item.body}</p>
          <div class="badge ${item.tone || ""}">${item.when}</div>
        </div>
      `).join("");
    };

    const setView = (view) => {
      state.currentView = view;
      navButtons.forEach((button) => button.classList.toggle("active", button.dataset.view === view));
      viewPanels.forEach((panel) => panel.classList.toggle("active", panel.dataset.viewPanel === view));
    };

    const fetchJson = async (path) => {
      const response = await fetch(path, { headers: authHeaders() });
      if (!response.ok) throw new Error(`${path} -> ${response.status}`);
      return response.json();
    };

    const summarizeTelemetry = (row) => {
      const eventType = row.event_type || row.type || "telemetry";
      const reason = row.reason || row.message || row.payload?.reason || row.payload?.status || "";
      return { eventType, reason };
    };

    const setSocketState = (name, status) => {
      state.socketStatus[name] = status;
      const tone = statusTone(status);
      const pill = $(`socket-${name}`);
      if (pill) {
        pill.classList.remove("warn", "danger", "ok");
        if (tone) pill.classList.add(tone);
      }
      text(`socket-${name}-text`, status);
      text("truth-score", `${truthCount()} live feeds`);
      text("truth-score-note", `${Object.values(state.socketStatus).filter((value) => value === "online").length} websocket lanes online${state.token ? " plus authenticated REST" : ""}.`);
    };

    const renderStrategies = () => {
      const rows = state.data.strategies || [];
      text("strategy-count-badge", `${rows.length} rows`);
      if (!rows.length) {
        els.strategyStack.innerHTML = '<div class="empty-state">No published runtime strategy allocations. This view is truthful and stays empty until the robot emits strategy ranking data.</div>';
        return;
      }
      els.strategyStack.innerHTML = rows.map((row) => {
        const confidence = clamp(Number(row.confidence || 0), 0, 1);
        const alloc = clamp(Number(row.allocation_share || 0), 0, 1);
        const votes = clamp(Number(row.vote_weight || 0), 0, 1);
        return `
          <div class="strategy-row">
            <div class="strategy-head">
              <div>
                <strong>${row.strategy_id || "unknown"}</strong>
                <p class="muted">allocation ${fmtPct(alloc * 100)} / votes ${fmtPct(votes * 100)}</p>
              </div>
              <div class="score-pill ${statusTone(row.status)}">${fmtNum(confidence, 2)}</div>
            </div>
            <div class="bar-track"><div class="bar-fill" style="width:${Math.max(10, confidence * 100)}%;"></div></div>
          </div>
        `;
      }).join("");
    };

    const renderModules = () => {
      const rows = state.data.modules || [];
      const first = rows[0];
      text("brain-updated-badge", first ? `updated ${fmtTime(first.last_update)}` : "waiting");
      if (!rows.length) {
        els.brainModuleStack.innerHTML = '<div class="empty-state">No module diagnostics available.</div>';
        return;
      }
      els.brainModuleStack.innerHTML = rows.map((row) => {
        const confidence = clamp(Number(row.confidence || 0), 0, 1);
        const influence = clamp(Number(row.influence || 0), 0, 1);
        return `
          <div class="module-card">
            <div class="module-head">
              <div>
                <label>${row.source || "runtime"}</label>
                <strong>${row.module_name || "Unknown Module"}</strong>
                <p class="muted">confidence ${fmtNum(confidence, 2)} / influence ${fmtNum(influence, 2)} / ${fmtTime(row.last_update)}</p>
              </div>
              <div class="badge ${statusTone(row.status)}">${row.status || "unknown"}</div>
            </div>
            <div class="bar-track"><div class="bar-fill" style="width:${Math.max(10, influence * 100)}%;"></div></div>
          </div>
        `;
      }).join("");
    };

    const renderTelemetryDistribution = () => {
      const rows = state.data.telemetryDist || [];
      if (!rows.length) {
        els.telemetryDistributionStack.innerHTML = '<div class="empty-state">No telemetry distribution yet.</div>';
        return;
      }
      els.telemetryDistributionStack.innerHTML = rows.slice(0, 8).map((row) => `
        <div class="strategy-row">
          <div class="strategy-head">
            <div>
              <strong>${row.event_type}</strong>
              <p class="muted">frequency ${fmtCompact(row.frequency)}</p>
            </div>
            <div class="badge">${fmtCompact(row.frequency)}</div>
          </div>
          <div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, Number(row.frequency || 0) * 14)}%;"></div></div>
        </div>
      `).join("");
    };

    const renderOrders = () => {
      const rows = state.data.orders || [];
      if (!rows.length) {
        els.ordersTableBody.innerHTML = '<tr><td colspan="5" class="muted">No order telemetry yet.</td></tr>';
        return;
      }
      els.ordersTableBody.innerHTML = rows.slice(0, 12).map((row) => `
        <tr>
          <td>${fmtTime(row.ts)}</td>
          <td>${row.symbol || "-"}</td>
          <td><span class="badge ${statusTone(row.status)}">${row.status || "unknown"}</span></td>
          <td>${row.reason || "-"}</td>
          <td>${fmtMoney(row.notional_quote || 0)}</td>
        </tr>
      `).join("");
    };

    const renderFills = () => {
      const rows = state.data.fills || [];
      if (!rows.length) {
        els.fillsTableBody.innerHTML = '<tr><td colspan="6" class="muted">No fills recorded.</td></tr>';
        return;
      }
      els.fillsTableBody.innerHTML = rows.slice(0, 12).map((row) => `
        <tr>
          <td>${fmtTime(row.ts)}</td>
          <td>${row.symbol || "-"}</td>
          <td>${row.side || "-"}</td>
          <td>${fmtNum(row.qty || 0, 6)}</td>
          <td>${fmtMoney(row.price || 0)}</td>
          <td>${fmtMoney(row.fee_quote || 0)}</td>
        </tr>
      `).join("");
    };

    const renderPositions = () => {
      const rows = state.data.positions || [];
      if (!rows.length) {
        els.positionsTableBody.innerHTML = '<tr><td colspan="7" class="muted">No positions in ledger.</td></tr>';
        return;
      }
      els.positionsTableBody.innerHTML = rows.slice(0, 16).map((row) => `
        <tr>
          <td>${fmtTime(row.ts)}</td>
          <td>${row.symbol || "-"}</td>
          <td>${fmtNum(row.signed_qty || 0, 6)}</td>
          <td>${fmtMoney(row.avg_entry_price || 0)}</td>
          <td>${fmtMoney(row.mark_price || 0)}</td>
          <td>${fmtMoney(row.unrealized_pnl_quote || 0)}</td>
          <td>${fmtMoney(row.realized_pnl_quote || 0)}</td>
        </tr>
      `).join("");
    };

    const renderScenarios = () => {
      const rows = state.data.scenarios || [];
      text("scenario-count-badge", `${rows.length} scenarios`);
      text("summary-scenarios", String(rows.length));
      text("rail-simulation", String(rows.length));
      if (!rows.length) {
        els.scenarioStack.innerHTML = '<div class="empty-state">No scenario graph is available yet.</div>';
        text("rail-simulation-note", "branches pending");
        return;
      }
      const best = rows[0];
      text("summary-scenarios-note", `top branch ${fmtPct((best.branch_probability || 0) * 100)}`);
      text("rail-simulation-note", `top branch ${fmtPct((best.branch_probability || 0) * 100)} / expected ${fmtMoney(best.expected_pnl || 0)}`);
      els.scenarioStack.innerHTML = rows.map((row) => `
        <div class="strategy-row">
          <div class="strategy-head">
            <div>
              <strong>${fmtPct((row.branch_probability || 0) * 100)} probability</strong>
              <p class="muted">expected ${fmtMoney(row.expected_pnl || 0)} / risk ${fmtNum(row.risk_score || 0, 1)}</p>
            </div>
            <div class="badge ${Number(row.expected_pnl || 0) < 0 ? "danger" : "ok"}">${fmtMoney(row.expected_pnl || 0)}</div>
          </div>
          <div class="bar-track"><div class="bar-fill" style="width:${Math.max(10, Number(row.branch_probability || 0) * 100)}%;"></div></div>
        </div>
      `).join("");
    };

    const renderReplaySessions = () => {
      const rows = state.data.replaySessions || [];
      if (!rows.length) {
        els.replaySessionStack.innerHTML = '<div class="empty-state">No replay sessions found in this run directory.</div>';
        return;
      }
      els.replaySessionStack.innerHTML = rows.map((row) => `
        <div class="session-card">
          <label>Replay session</label>
          <div class="session-head">
            <div>
              <strong>${row.session_id || "unknown"}</strong>
              <p class="muted mono">${row.path || ""}</p>
            </div>
            <div class="badge">ready</div>
          </div>
        </div>
      `).join("");
    };

    const renderAuditEvents = () => {
      const rows = state.data.telemetryEvents || [];
      if (!rows.length) {
        els.auditEventStack.innerHTML = '<div class="empty-state">No audit events loaded yet.</div>';
        return;
      }
      els.auditEventStack.innerHTML = rows.slice(0, 14).map((row) => {
        const summary = summarizeTelemetry(row);
        return `
          <div class="event-card">
            <label>${summary.eventType}</label>
            <div class="event-head">
              <strong>${summary.eventType}</strong>
              <div class="badge">${fmtTime(row.timestamp)}</div>
            </div>
            <p class="muted">${summary.reason || "no reason published"}</p>
          </div>
        `;
      }).join("");
    };

    const renderInsights = () => {
      const insights = [];
      const capital = state.data.capital;
      const decision = state.data.decision;
      const audit = state.data.audit;
      const execution = state.data.execution;
      const scenarios = state.data.scenarios || [];

      if (capital) {
        const profit = Number(capital.profit || 0);
        insights.push({
          title: profit >= 0 ? "Capital core is at or above baseline." : "Capital core is under recovery pressure.",
          body: `Equity ${fmtMoney(capital.equity || 0)} with ${fmtPct(capital.drawdown_pct || 0)} drawdown and survivability ${fmtNum(capital.survivability_score || 0, 1)}.`
        });
      }
      if (decision) {
        insights.push({
          title: `${String(decision.action || "hold").toUpperCase()} posture via ${decision.strategy || "unknown"}.`,
          body: `Confidence ${fmtNum(decision.confidence || 0, 2)} on ${decision.symbol || "N/A"}. ${decision.reason || "No decision reason published."}`
        });
      }
      if (audit) {
        insights.push({
          title: `Governance is ${audit.gate_status || "unknown"} with ${audit.readiness_stage || "unknown"} readiness.`,
          body: `Invariants ${audit.hard_invariants_status || "unknown"}, drift ${audit.drift_status || "unknown"}, manual gate ${audit.manual_gate_status || "unknown"}.`
        });
      }
      if (execution) {
        insights.push({
          title: `${execution.filled_orders || 0} fills against ${execution.submitted_orders || 0} submitted orders.`,
          body: `${execution.blocked_orders || 0} blocked, ${execution.rejected_orders || 0} rejected, latency ${fmtNum(execution.latency || 0, 1)} ms.`
        });
      }
      if (scenarios.length) {
        const best = scenarios[0];
        insights.push({
          title: `Top scenario implies ${fmtMoney(best.expected_pnl || 0)} expected outcome.`,
          body: `Branch probability ${fmtPct((best.branch_probability || 0) * 100)} with risk score ${fmtNum(best.risk_score || 0, 1)}.`
        });
      }

      text("insight-count-badge", `${insights.length} signals`);
      if (!insights.length) {
        els.insightStack.innerHTML = '<div class="empty-state">Connect to produce live operator insights.</div>';
        return;
      }
      els.insightStack.innerHTML = insights.slice(0, 4).map((item) => `
        <div class="insight-card">
          <label>Operator signal</label>
          <strong>${item.title}</strong>
          <p class="muted">${item.body}</p>
        </div>
      `).join("");
    };

    const updateNarrative = () => {
      const capital = state.data.capital;
      const decision = state.data.decision;
      const audit = state.data.audit;
      const execution = state.data.execution;
      const environment = state.data.environment;

      const profit = Number(capital?.profit || 0);
      const drawdown = Number(capital?.drawdown_pct || 0);
      const confidence = Number(decision?.confidence || 0);
      const filled = Number(execution?.filled_orders || 0);
      const submitted = Number(execution?.submitted_orders || 0);

      const bestRead = decision
        ? `${String(decision.action || "hold").toUpperCase()} ${decision.symbol || "N/A"}`
        : "No live decision packet";
      const bestReadNote = decision
        ? `${decision.strategy || "unknown strategy"} / confidence ${fmtNum(confidence, 2)}`
        : "Authenticate to hydrate the brain view.";
      text("brief-best-read", bestRead);
      text("brief-best-read-note", bestReadNote);
      text("brief-confidence", fmtNum(confidence, 2));
      text("brief-confidence-note", decision ? `Source ${decision.source_module || "runtime"}` : "Decision channel not active.");

      const riskPosture = audit?.gate_status || audit?.system_state || "unknown";
      text("brief-risk-posture", riskPosture);
      text("brief-risk-note", audit ? `${audit.readiness_stage || "unknown"} / invariants ${audit.hard_invariants_status || "unknown"}` : "Audit lane not hydrated.");

      const execPosture = submitted > 0 ? `${filled}/${submitted} flowing` : "Cold";
      text("brief-execution-posture", execPosture);
      text("brief-execution-note", execution ? `${execution.blocked_orders || 0} blocked / latency ${fmtNum(execution.latency || 0, 1)} ms` : "Execution lane idle.");

      const missionTitle = decision
        ? `${String(decision.action || "hold").toUpperCase()} posture on ${decision.symbol || environment?.symbol || "N/A"}`
        : environment?.runtime_mode
          ? `Runtime ${environment.runtime_mode} is visible`
          : "System is waiting for operator sign-in.";
      const missionBody = audit
        ? `Gate ${audit.gate_status || "unknown"}, readiness ${audit.readiness_stage || "unknown"}, system ${audit.system_state || "unknown"}.`
        : "Once authenticated, this card condenses the highest-value narrative from capital, decision, risk and execution state.";
      text("mission-brief-title", missionTitle);
      text("mission-brief-body", missionBody);
      text("command-brief-badge", audit?.gate_status || (decision ? "live" : "standby"));
      $("command-brief-badge").className = `badge ${statusTone(audit?.gate_status || (decision ? "ok" : "warn"))}`;

      text("mission-strip-title", decision ? `${String(decision.action || "hold").toUpperCase()} ${decision.symbol || "N/A"}` : "Operator visibility stabilizing");
      text("mission-strip-body", decision?.reason || (environment?.resolved_run_dir ? `Run ${environment.resolved_run_dir}` : "Connect to the gateway to hydrate the live model, realtime channels and capital surface."));
      text("focus-line", capital ? `${fmtMoney(capital.equity || 0)} equity / ${fmtPct(drawdown)} drawdown` : "Awaiting runtime telemetry");
      text("focus-line-note", execution ? `${filled} fills, ${submitted} submitted, latency ${fmtNum(execution.latency || 0, 1)} ms.` : "When data arrives, this strip will summarize the highest-signal operator context.");
      text("command-summary", capital ? `Profit ${fmtMoney(profit)} with survivability ${fmtNum(capital.survivability_score || 0, 1)}. Risk posture ${riskPosture}.` : "This surface never invents state. It only amplifies what the robot has actually emitted.");
      text("sidebar-session", state.token ? "Authenticated read contract active" : "Stored token absent");
      text("sidebar-session-note", state.token ? `${truthCount()} live feeds currently visible.` : "Authenticate to unlock live contract views.");
      text("command-palette-title", decision ? `${decision.strategy || "Runtime"} / ${String(decision.action || "hold").toUpperCase()}` : "Fast operator actions");
      text("command-action-note", state.token ? `Session active for ${environment?.run_id || "current run"}. Use reconnect if websocket lanes go stale.` : "Actions stay read-only unless the underlying backend endpoint performs a safe read.");
    };

    const applyCapital = (capital) => {
      if (!capital) return;
      state.data.capital = capital;
      const profit = Number(capital.profit || 0);
      const drawdown = Number(capital.drawdown_pct || 0);
      const survivability = Number(capital.survivability_score || 0);
      const allocation = Number(capital.allocation || 0);
      text("capital-equity", fmtMoney(capital.equity || 0));
      text("capital-profit", fmtMoney(profit));
      text("capital-drawdown", fmtPct(drawdown));
      text("capital-survivability", fmtNum(survivability, 1));
      text("capital-allocation", fmtNum(allocation, 2));
      text("capital-view-equity", fmtMoney(capital.equity || 0));
      text("capital-view-pnl", fmtMoney(profit));
      text("capital-view-dd", fmtPct(drawdown));
      text("capital-view-exposure", fmtNum(allocation, 2));
      text("shield-survival", fmtNum(survivability, 1));
      text("shield-survival-note", survivability >= 80 ? "Capital shell intact" : "Protection tightening");
      text("capital-profit-note", profit >= 0 ? "Core brightness rising." : "Cooling effect detected.");
      text("capital-drawdown-note", drawdown <= 2 ? "Shield stable." : "Risk shell engaged.");
      text("capital-survivability-note", survivability >= 80 ? "Capital shell intact." : "Reduced survivability margin.");
      text("capital-allocation-note", `${capital.positions_open || 0} open positions`);
      text("capital-position-count", `${capital.positions_open || 0} open positions`);
      text("capital-position-note", `${fmtNum(allocation, 2)} notional quote exposure`);
      text("capital-performance-headline", profit >= 0 ? "Capital core stable or growing." : "Capital is under recovery pressure.");
      text("capital-performance-note", drawdown <= 0 ? "No active drawdown." : `Signed drawdown ${fmtPct(drawdown)}.`);

      const glow = clamp(0.5 + profit / 50, 0.2, 1.0);
      const riskGlow = clamp(Math.abs(drawdown) / 12, 0.08, 0.95);
      appShell.style.setProperty("--capital-glow", glow.toFixed(3));
      appShell.style.setProperty("--risk-glow", riskGlow.toFixed(3));
      appShell.style.setProperty("--profit-hue", profit >= 0 ? "188" : "356");
      updateNarrative();
      renderInsights();
    };

    const applyDecision = (decision) => {
      if (!decision) return;
      state.data.decision = decision;
      const confidence = Number(decision.confidence || 0);
      text("decision-title", `${decision.strategy || "unknown"} / ${decision.symbol || "N/A"} / confidence ${fmtNum(confidence, 2)}`);
      text("decision-action", `${String(decision.action || "hold").toUpperCase()} via ${decision.strategy || "unknown"}`);
      text("decision-reason", decision.reason || "no runtime reason");
      text("decision-strategy-badge", decision.strategy || "unknown");
      text("decision-confidence-pill", fmtNum(confidence, 2));
      text("brain-score-pill", fmtNum(confidence, 2));
      text("brain-current-strategy", decision.strategy || "unknown");
      text("brain-current-action", decision.action || "hold");
      text("brain-current-reason", decision.reason || "no runtime reason");
      text("brain-deep-diagnostics", `Symbol ${decision.symbol || "N/A"} / source ${decision.source_module || "query_service"} / ${fmtTime(decision.timestamp || null)}`);
      text("runtime-symbol-badge", decision.symbol || "symbol pending");
      timelinePush({ channel: "decision", title: `${String(decision.action || "hold").toUpperCase()} ${decision.symbol || ""}`.trim(), body: decision.reason || "runtime decision refreshed", when: fmtTime(decision.timestamp || Date.now()) });
      updateNarrative();
      renderInsights();
    };

    const applyExecution = (execution) => {
      if (!execution) return;
      state.data.execution = execution;
      const submitted = Number(execution.submitted_orders || 0);
      const filled = Number(execution.filled_orders || 0);
      const blocked = Number(execution.blocked_orders || 0);
      const rejected = Number(execution.rejected_orders || 0);
      const latency = Number(execution.latency || 0);
      const slippage = Number(execution.slippage || 0);
      text("exec-submitted", String(submitted));
      text("exec-filled", String(filled));
      text("exec-blocked", String(blocked));
      text("exec-rejected", String(rejected));
      text("exec-latency", `${fmtNum(latency, 1)} ms`);
      text("exec-slippage", `${fmtNum(slippage, 2)} bps`);
      text("summary-orders", String(submitted));
      text("summary-fills", String(filled));
      text("summary-latency", `${fmtNum(latency, 1)} ms`);
      text("rail-execution", `${filled} / ${submitted}`);
      text("rail-execution-note", `${blocked} blocked / ${rejected} rejected`);
      text("rail-latency", `${fmtNum(latency, 1)} ms`);
      text("rail-latency-note", `slippage ${fmtNum(slippage, 2)} bps`);
      text("exec-submitted-note", submitted ? "orders submitted" : "quiet cycle");
      text("exec-filled-note", filled ? "fills confirmed" : "fill tape idle");
      text("exec-blocked-note", blocked ? "guardrail blocks" : "no blocks");
      text("exec-rejected-note", rejected ? "venue rejects" : "no rejects");
      text("exec-latency-note", latency > 0 ? "runtime median" : "no live fills yet");
      text("exec-slippage-note", slippage > 0 ? "modeled vs realized" : "no slippage yet");
      text("execution-health-badge", rejected > 0 ? "degraded" : "stable");
      $("execution-health-badge").className = `badge ${rejected > 0 ? "warn" : "ok"}`;
      const rejectRate = submitted > 0 ? (rejected / submitted) * 100 : 0;
      text("reject-rate", fmtPct(rejectRate));
      text("reject-rate-note", rejected > 0 ? `${rejected} rejects observed` : "clean submit lane");
      updateNarrative();
      renderInsights();
    };

    const applyAudit = (audit) => {
      if (!audit) return;
      state.data.audit = audit;
      const stage = audit.readiness_stage || "unknown";
      const gateLine = [audit.gate_status || "unknown", audit.manual_gate_status || "unknown", audit.operator_approval_status || "unknown"].join(" / ");
      text("audit-system-state", audit.system_state || "unknown");
      text("audit-invariants", audit.hard_invariants_status || "unknown");
      text("audit-drift", audit.drift_status || "unknown");
      text("audit-gate", audit.gate_status || "unknown");
      text("audit-stage", stage);
      text("audit-stage-badge", stage);
      text("audit-view-system", audit.system_state || "unknown");
      text("audit-view-system-note", `runtime ${audit.runtime_mode || "unknown"} / target ${audit.target_mode || "unknown"} / updated ${fmtTime(audit.updated_at || Date.now())}`);
      text("audit-view-gate", audit.gate_status || "unknown");
      text("audit-view-gate-note", `${gateLine} / ${audit.hard_invariants_status || "unknown"} invariants`);
      text("audit-view-stage", stage);
      text("audit-view-stage-note", `${audit.drift_status || "unknown"} drift / ${audit.config_freeze_status || "unknown"} config / ${audit.promotion_status || "unknown"} promotion`);
      text("summary-gate", audit.gate_status || "unknown");
      text("summary-gate-note", `${stage} / ${audit.manual_gate_status || "unknown"}`);
      text("rail-shield", audit.system_state || "unknown");
      text("rail-shield-note", `${stage} / ${gateLine}`);
      text("shield-status-badge", audit.hard_invariants_status || "unknown");
      ["audit-stage-badge", "shield-status-badge"].forEach((id) => {
        const el = $(id);
        el.className = `badge ${statusTone(stage === "blocked" ? "blocked" : audit.gate_status || audit.system_state || "unknown")}`;
      });
      updateNarrative();
      renderInsights();
    };

    const applyStatus = (statusPayload) => {
      if (!statusPayload) return;
      state.data.status = statusPayload;
      const runtime = statusPayload.runtime_health || {};
      const snapshot = statusPayload.dashboard_snapshot || {};
      const groups = snapshot.groups || {};
      const decision = groups.decision || {};
      const execution = groups.execution || {};
      const harmony = groups.harmony || {};
      state.data.compliance = runtime;
      state.data.harmony = harmony;
      text("provider-value", runtime.provider || runtime.reason || "unknown");
      text("provider-note", runtime.reason || runtime.provider || "runtime state");
      text("decision-tick-count", fmtCompact(decision.decision_tick_total || 0));
      text("decision-tick-note", decision.decision_tick_skip_total ? `${fmtCompact(decision.decision_tick_skip_total)} skipped` : "no skips published");
      text("summary-mode", runtime.mode || "Paper");
      text("summary-mode-note", runtime.provider || "staging");
      text("core-headline", `${String((state.data.decision && state.data.decision.action) || runtime.status || "hold").toUpperCase()} ${runtime.symbol || "N/A"} with confidence ${fmtNum((state.data.decision && state.data.decision.confidence) || 0, 2)}`);
      text("mission-pill", `Mission ${runtime.status || "unknown"} / ${runtime.version || "v0.1.0"}`);
      text("compliance-state", runtime.compliance_allowed === false ? "blocked" : "authorized");
      text("compliance-reason", runtime.reason || runtime.compliance_reason || "runtime health reason unavailable");
      text("harmony-mode", harmony.harmony_guards_mode || "strict");
      text("harmony-note", harmony.harmony_order_cadence_s ? `order cadence ${harmony.harmony_order_cadence_s}s / min quote ${harmony.harmony_effective_min_order_quote}` : "No harmony snapshot.");
      text("distributed-state", runtime.distributed_enabled ? "distributed" : (runtime.allow_local_fallback ? "local fallback" : "local"));
      text("distributed-note", `${runtime.node_role || "live"} node / provider ${runtime.provider || "unknown"}`);
      text("llm-state", runtime.provider || "disabled");
      text("llm-note", runtime.compliance_reason || runtime.reason || "No LLM advisory status.");
      text("summary-orders-note", execution.orders_submitted_total ? `${fmtCompact(execution.orders_submitted_total)} submitted snapshot` : "submitted");
      text("summary-fills-note", execution.fills_confirmed_total ? `${fmtCompact(execution.fills_confirmed_total)} confirmed snapshot` : "confirmed");
      if (runtime.symbol) text("runtime-symbol-badge", runtime.symbol);
      updateNarrative();
    };

    const applyEnvironment = (environment) => {
      if (!environment) return;
      state.data.environment = environment;
      setTone(els.modePill, statusTone(environment.mode), `Mode: ${environment.mode || "Paper"}`);
      const syncText = `Sync: ${environment.environment || "staging"} / ${environment.run_id || "latest"} / ${environment.runtime_mode || environment.mode || "unknown"}`;
      setTone(els.syncPill, environment.distributed_enabled ? "ok" : "warn", syncText);
      text("distributed-note", `${environment.node_role || "live"} node / ${environment.target_mode || "auto"} target / ${environment.resolved_run_dir || "run pending"}`);
      updateNarrative();
    };

    const renderInstallState = () => {
      const button = $("install-button");
      if (state.deferredInstall) {
        button.disabled = false;
        button.textContent = "Install Universe App";
      } else {
        button.disabled = false;
        button.textContent = "Install Universe App";
      }
    };

    const refreshAll = async () => {
      if (!state.token) {
        updateNarrative();
        renderInsights();
        return;
      }
      try {
        const [statusPayload, positionsPayload, systemStatus, environment, capital, decision, modules, strategies, execution, orders, fills, telemetryEvents, telemetryDist, audit, replaySessions, scenarios] = await Promise.all([
          fetchJson("/status"),
          fetchJson("/positions"),
          fetchJson("/api/system/status"),
          fetchJson("/api/system/environment"),
          fetchJson("/api/capital/state"),
          fetchJson("/api/brain/decision"),
          fetchJson("/api/brain/modules"),
          fetchJson("/api/strategies/ranking"),
          fetchJson("/api/execution/stats"),
          fetchJson("/api/execution/orders?limit=12"),
          fetchJson("/api/execution/fills?limit=12"),
          fetchJson("/api/telemetry/events?limit=16"),
          fetchJson("/api/telemetry/distribution"),
          fetchJson("/api/audit/runtime"),
          fetchJson("/api/replay/sessions"),
          fetchJson("/api/simulation/scenarios")
        ]);

        state.data.system = systemStatus;
        state.data.positions = positionsPayload.positions || [];
        state.data.modules = modules.rows || [];
        state.data.strategies = strategies.rows || [];
        state.data.orders = orders.rows || [];
        state.data.fills = fills.rows || [];
        state.data.telemetryEvents = telemetryEvents.rows || [];
        state.data.telemetryDist = telemetryDist.rows || [];
        state.data.replaySessions = replaySessions.rows || [];
        state.data.scenarios = scenarios.rows || [];

        applyStatus(statusPayload);
        applyEnvironment(environment);
        applyCapital(capital);
        applyDecision(decision);
        applyExecution(execution);
        applyAudit(audit);
        renderStrategies();
        renderModules();
        renderTelemetryDistribution();
        renderOrders();
        renderFills();
        renderPositions();
        renderScenarios();
        renderReplaySessions();
        renderAuditEvents();
        renderInsights();
        setTone(els.healthPill, statusTone(systemStatus.health), `Health: ${systemStatus.health || "unknown"}`);
        setTone(els.authStatePill, "ok", "Signed in");
        text("auth-state", `Connected as ${systemStatus.provider || "runtime"}`);
        text("auth-hint", `Authenticated read access against ${environment.run_id || "latest"}.`);
        timelinePush({ channel: "refresh", title: "Read models refreshed", body: `${systemStatus.mode || "Paper"} / ${systemStatus.provider || "provider unknown"}`, when: new Date().toLocaleTimeString(), tone: statusTone(systemStatus.health) });
      } catch (error) {
        setTone(els.healthPill, "danger", "Health: auth / fetch error");
        timelinePush({ channel: "refresh", title: "Refresh failed", body: String(error), when: new Date().toLocaleTimeString(), tone: "danger" });
      }
    };

    const closeSockets = () => {
      Object.entries(state.sockets).forEach(([name, socket]) => {
        try { socket.close(); } catch (_error) {}
        setSocketState(name, "offline");
      });
      state.sockets = {};
    };

    const connectSocket = (name, onMessage) => {
      if (!state.token) return;
      const protocol = location.protocol === "https:" ? "wss" : "ws";
      const url = `${protocol}://${location.host}/ws/${name}?token=${encodeURIComponent(state.token)}`;
      setSocketState(name, "connecting");
      const socket = new WebSocket(url);
      socket.onopen = () => {
        setSocketState(name, "online");
        timelinePush({ channel: `ws/${name}`, title: "Realtime channel online", body: "Subscription accepted by gateway.", when: new Date().toLocaleTimeString(), tone: "ok" });
      };
      socket.onclose = () => {
        setSocketState(name, "offline");
        timelinePush({ channel: `ws/${name}`, title: "Realtime channel closed", body: "Gateway closed the stream or the token expired.", when: new Date().toLocaleTimeString(), tone: "warn" });
      };
      socket.onerror = () => {
        setSocketState(name, "error");
        timelinePush({ channel: `ws/${name}`, title: "Realtime channel error", body: "WebSocket stream reported an error.", when: new Date().toLocaleTimeString(), tone: "danger" });
      };
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          onMessage(message);
        } catch (error) {
          timelinePush({ channel: `ws/${name}`, title: "Unreadable frame", body: String(error), when: new Date().toLocaleTimeString(), tone: "danger" });
        }
      };
      state.sockets[name] = socket;
    };

    const connectSockets = () => {
      closeSockets();
      connectSocket("capital", (message) => {
        if (message.payload && typeof message.payload === "object") {
          applyCapital({ ...(state.data.capital || {}), ...(message.payload || {}) });
          timelinePush({ channel: "ws/capital", title: message.event_type || "capital", body: fmtMoney(message.payload.equity || message.payload.profit || 0), when: fmtTime(message.timestamp || Date.now()) });
        }
      });
      connectSocket("decisions", (message) => {
        if (message.payload && typeof message.payload === "object") {
          applyDecision({ ...(state.data.decision || {}), ...(message.payload || {}), timestamp: message.timestamp || Date.now(), confidence: message.confidence ?? message.payload.confidence });
        }
      });
      connectSocket("execution", async (message) => {
        if (message.payload && typeof message.payload === "object") {
          timelinePush({ channel: "ws/execution", title: message.event_type || "execution", body: JSON.stringify(message.payload).slice(0, 160), when: fmtTime(message.timestamp || Date.now()) });
          await refreshAll();
        }
      });
      connectSocket("risk", (message) => {
        if (message.payload && typeof message.payload === "object") {
          applyAudit({ ...(state.data.audit || {}), ...(message.payload || {}), updated_at: message.timestamp || Date.now() });
          timelinePush({ channel: "ws/risk", title: message.event_type || "risk", body: message.payload.status || message.payload.reason || "risk update", when: fmtTime(message.timestamp || Date.now()) });
        }
      });
      connectSocket("simulation", (message) => {
        if (Array.isArray(message.payload?.scenarios)) {
          state.data.scenarios = message.payload.scenarios;
          renderScenarios();
          renderInsights();
          timelinePush({ channel: "ws/simulation", title: "Scenario graph updated", body: `${message.payload.scenarios.length} branches`, when: fmtTime(message.timestamp || Date.now()) });
        }
      });
      connectSocket("telemetry", (message) => {
        const events = message.payload?.events || [];
        if (Array.isArray(events) && events.length) {
          const mapped = events.map((event) => ({
            event_type: event.event_type || message.event_type || "telemetry",
            reason: event.payload?.reason || event.payload?.status || event.reason || "",
            timestamp: event.timestamp || event.ts || message.timestamp || Date.now()
          }));
          state.data.telemetryEvents = [...mapped, ...(state.data.telemetryEvents || [])].slice(0, 16);
          renderAuditEvents();
          const first = mapped[0];
          timelinePush({ channel: "ws/telemetry", title: first.event_type, body: first.reason || `${events.length} telemetry events`, when: fmtTime(first.timestamp || Date.now()) });
        }
      });
    };

    const authenticate = async () => {
      const username = $("auth-user").value.trim();
      const password = $("auth-pass").value;
      try {
        const response = await fetch("/api/auth/token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password })
        });
        if (!response.ok) throw new Error(`auth -> ${response.status}`);
        const payload = await response.json();
        state.token = payload.access_token;
        localStorage.setItem("universe.token", state.token);
        setTone(els.authStatePill, "ok", "Signed in");
        text("auth-state", `Signed in as ${payload.username} (${payload.role})`);
        text("auth-hint", `Realtime and REST access are active for ${payload.role}.`);
        text("sidebar-session", `Signed in as ${payload.username}`);
        text("sidebar-session-note", `${payload.role} role session active.`);
        await refreshAll();
        connectSockets();
      } catch (error) {
        state.token = "";
        localStorage.removeItem("universe.token");
        setTone(els.authStatePill, "danger", "Auth failed");
        text("auth-state", "Authentication failed");
        text("auth-hint", String(error));
        timelinePush({ channel: "auth", title: "Authentication failed", body: String(error), when: new Date().toLocaleTimeString(), tone: "danger" });
        updateNarrative();
      }
    };

    const installApp = async () => {
      if (state.deferredInstall) {
        state.deferredInstall.prompt();
        await state.deferredInstall.userChoice.catch(() => null);
        state.deferredInstall = null;
        renderInstallState();
        return;
      }
      text("auth-hint", "On iPhone: Safari -> Share -> Add to Home Screen. On Mac: Safari -> File -> Add to Dock.");
      timelinePush({ channel: "install", title: "Install instructions", body: "Safari Add to Home Screen / Add to Dock is available for this PWA.", when: new Date().toLocaleTimeString(), tone: "ok" });
    };

    const togglePresentMode = () => {
      body.classList.toggle("present-mode");
      $("present-button").textContent = body.classList.contains("present-mode") ? "Exit Present" : "Present Mode";
      timelinePush({ channel: "present", title: body.classList.contains("present-mode") ? "Present mode enabled" : "Present mode disabled", body: body.classList.contains("present-mode") ? "Sidebar, diagnostics rail and timeline collapsed." : "Full operator surface restored.", when: new Date().toLocaleTimeString(), tone: "ok" });
    };

    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      state.deferredInstall = event;
      renderInstallState();
    });

    $("connect-button").addEventListener("click", authenticate);
    $("refresh-button").addEventListener("click", refreshAll);
    $("install-button").addEventListener("click", installApp);
    $("present-button").addEventListener("click", togglePresentMode);
    $("action-refresh").addEventListener("click", refreshAll);
    $("action-reconnect").addEventListener("click", connectSockets);
    $("action-grafana").addEventListener("click", () => window.open("http://127.0.0.1:3000", "_blank", "noopener"));
    $("action-raw-api").addEventListener("click", () => window.open("/api/telemetry/events?limit=50", "_blank", "noopener"));
    $("palette-refresh").addEventListener("click", refreshAll);
    $("palette-connect").addEventListener("click", () => state.token ? connectSockets() : authenticate());
    $("palette-grafana").addEventListener("click", () => window.open("http://127.0.0.1:3000", "_blank", "noopener"));
    $("palette-api").addEventListener("click", () => window.open("/api/telemetry/events?limit=50", "_blank", "noopener"));
    navButtons.forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));

    window.addEventListener("keydown", (event) => {
      if (["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
      const numericView = { "1": "command", "2": "brain", "3": "shield", "4": "execution", "5": "capital", "6": "simulation", "7": "audit" }[event.key];
      if (numericView) {
        setView(numericView);
        return;
      }
      if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        refreshAll();
      }
      if (event.key.toLowerCase() === "c") {
        event.preventDefault();
        state.token ? connectSockets() : authenticate();
      }
      if (event.key.toLowerCase() === "p") {
        event.preventDefault();
        togglePresentMode();
      }
    });

    setInterval(() => { text("clock-pill", new Date().toLocaleTimeString([], { hour12: false, timeZoneName: "short" })); }, 1000);
    text("clock-pill", new Date().toLocaleTimeString([], { hour12: false, timeZoneName: "short" }));
    renderInstallState();
    renderTimeline();
    updateNarrative();
    renderInsights();

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/ui/sw.js", { scope: "/ui/" }).catch(() => null);
    }

    if (state.token) {
      setTone(els.authStatePill, "ok", "Stored session");
      text("auth-state", "Stored session detected");
      text("auth-hint", "Refreshing from stored bearer token.");
      text("sidebar-session", "Stored token detected");
      text("sidebar-session-note", "Refreshing from local session state.");
      refreshAll().then(connectSockets).catch(() => null);
    }
  </script>
</body>
</html>
"""


def render_pwa_manifest() -> str:
    return json.dumps(
        {
            "name": "Universe Control Center",
            "short_name": "Universe",
            "description": "Realtime operating interface for the Universe autonomous trading robot.",
            "start_url": "/ui",
            "scope": "/",
            "display": "standalone",
            "background_color": "#071018",
            "theme_color": "#071018",
            "icons": [
                {"src": "/ui/assets/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "/ui/assets/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        }
    )


def render_service_worker() -> str:
    return """const CACHE = 'universe-control-center-v3';
const SHELL = ['/ui', '/ui/manifest.webmanifest', '/ui/assets/icon-192.png', '/ui/assets/icon-512.png', '/ui/assets/apple-touch-icon.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  if (!event.request.url.includes('/ui')) return;
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(event.request, copy));
      return response;
    }).catch(() => caches.match('/ui')))
  );
});
"""
