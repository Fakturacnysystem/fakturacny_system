import type { ReleaseContract, ReleaseChecklistItem } from "@/types/contracts";

export interface MacosReleaseEnv {
  bundleId?: string;
  appleTeamId?: string;
  signingIdentity?: string;
  notarizationAppleId?: string;
  notarizationAppPassword?: string;
  notarizationProviderShortName?: string;
}

const EXACT_COMMANDS = [
  "npm run check",
  "npm run build",
  "npm run release:macos:verify",
  "npm run tauri:build",
  "APPLE_TEAM_ID=... APPLE_SIGNING_IDENTITY=... APPLE_ID=... APPLE_APP_PASSWORD=... APPLE_PROVIDER_SHORT_NAME=... TAURI_BUNDLE_IDENTIFIER=... npm run release:macos:plan",
];

function checklistItem(label: string, satisfied: boolean, detail: string): ReleaseChecklistItem {
  return { label, satisfied, detail };
}

export function evaluateMacosReleaseReadiness(env: MacosReleaseEnv): ReleaseContract {
  const checklist = [
    checklistItem(
      "Bundle identifier",
      Boolean(env.bundleId),
      env.bundleId ?? "Missing TAURI_BUNDLE_IDENTIFIER / NEXT_PUBLIC_RTC_BUNDLE_ID.",
    ),
    checklistItem(
      "Apple Team ID",
      Boolean(env.appleTeamId),
      env.appleTeamId ?? "Missing APPLE_TEAM_ID.",
    ),
    checklistItem(
      "Signing identity",
      Boolean(env.signingIdentity),
      env.signingIdentity ?? "Missing APPLE_SIGNING_IDENTITY.",
    ),
    checklistItem(
      "Notarization account",
      Boolean(env.notarizationAppleId && env.notarizationAppPassword),
      env.notarizationAppleId && env.notarizationAppPassword
        ? "Apple ID + app password configured."
        : "Missing APPLE_ID and/or APPLE_APP_PASSWORD.",
    ),
    checklistItem(
      "Notarization provider short name",
      Boolean(env.notarizationProviderShortName),
      env.notarizationProviderShortName ?? "Missing APPLE_PROVIDER_SHORT_NAME.",
    ),
  ];

  const missingInputs = checklist
    .filter((item) => !item.satisfied)
    .map((item) => item.label);

  return {
    status: missingInputs.length === 0 ? "ready" : "blocked",
    bundleId: env.bundleId ?? "com.fakturacnysystem.robotcontrolcenter",
    checklist,
    missingInputs,
    exactCommands: EXACT_COMMANDS,
  };
}

export function getPublicMacosReleaseReadiness(): ReleaseContract {
  return evaluateMacosReleaseReadiness({
    bundleId:
      process.env.NEXT_PUBLIC_RTC_BUNDLE_ID ?? process.env.TAURI_BUNDLE_IDENTIFIER,
    appleTeamId: process.env.NEXT_PUBLIC_APPLE_TEAM_ID,
  });
}
