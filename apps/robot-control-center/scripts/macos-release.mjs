#!/usr/bin/env node

const required = [
  ["TAURI_BUNDLE_IDENTIFIER", process.env.TAURI_BUNDLE_IDENTIFIER],
  ["APPLE_TEAM_ID", process.env.APPLE_TEAM_ID],
  ["APPLE_SIGNING_IDENTITY", process.env.APPLE_SIGNING_IDENTITY],
  ["APPLE_ID", process.env.APPLE_ID],
  ["APPLE_APP_PASSWORD", process.env.APPLE_APP_PASSWORD],
  ["APPLE_PROVIDER_SHORT_NAME", process.env.APPLE_PROVIDER_SHORT_NAME],
];

const missing = required.filter(([, value]) => !value).map(([key]) => key);
const output = {
  mode: process.argv.includes("--mode=plan") ? "plan" : "run",
  status: missing.length === 0 ? "ready" : "blocked",
  missing,
  commands: [
    "npm run check",
    "npm run build",
    "npm run release:macos:verify",
    "npm run tauri:build",
    "xcrun notarytool submit <bundle> --apple-id \"$APPLE_ID\" --team-id \"$APPLE_TEAM_ID\" --password \"$APPLE_APP_PASSWORD\" --wait",
    "xcrun stapler staple <bundle>",
  ],
};

console.log(JSON.stringify(output, null, 2));

if (missing.length > 0 && !process.argv.includes("--mode=plan")) {
  process.exit(1);
}
