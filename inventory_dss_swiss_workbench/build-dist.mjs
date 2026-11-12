#!/usr/bin/env node
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const builderPath = path.join(os.homedir(), '.gemini/config/skills/principal-ui-pipeline/gates/build-sandbox-app.mjs');
const { buildSandboxApp } = await import(pathToFileURL(builderPath).href);

const res = buildSandboxApp(__dirname);
console.log(JSON.stringify(res, null, 2));
if (!res.ok) process.exit(1);
