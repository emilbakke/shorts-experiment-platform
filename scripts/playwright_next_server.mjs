#!/usr/bin/env node
import { rmSync } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const port = process.env.PLAYWRIGHT_PORT || '3100';
const distDir = process.env.NEXT_DIST_DIR || `.next-test-${port}`;
const distBase = path.basename(distDir);

if (!distBase.startsWith('.next-test')) {
  console.error(`Refusing to clean unexpected Next dist dir: ${distDir}`);
  process.exit(1);
}

const frontendDir = path.join(repoRoot, 'frontend');
const fullDistPath = path.join(frontendDir, distDir);
rmSync(fullDistPath, { recursive: true, force: true });

const env = { ...process.env, NEXT_DIST_DIR: distDir, VIEWTUBE_BACKEND_MODE: 'subprocess' };
const build = spawnSync('npm', ['--prefix', 'frontend', 'run', 'build'], {
  cwd: repoRoot,
  stdio: 'inherit',
  env,
});
if (build.status !== 0) process.exit(build.status ?? 1);

const child = spawn(
  'npm',
  ['--prefix', 'frontend', 'run', 'start', '--', '--hostname', 'localhost', '--port', port],
  {
    cwd: repoRoot,
    stdio: 'inherit',
    env,
  },
);

const forward = (signal) => {
  if (!child.killed) child.kill(signal);
};
process.on('SIGINT', () => forward('SIGINT'));
process.on('SIGTERM', () => forward('SIGTERM'));
child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 0);
});
