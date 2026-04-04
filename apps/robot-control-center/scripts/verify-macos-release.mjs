#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const requiredFiles = [
  "src-tauri/tauri.conf.json",
  "src-tauri/Entitlements.plist",
  "src-tauri/Cargo.toml",
];

const missing = requiredFiles.filter((file) => !fs.existsSync(path.resolve(process.cwd(), file)));

const result = {
  status: missing.length === 0 ? "ok" : "blocked",
  missingFiles: missing,
};

console.log(JSON.stringify(result, null, 2));

if (missing.length > 0) {
  process.exit(1);
}
