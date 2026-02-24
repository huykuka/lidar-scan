import { cp, readdir, rm, mkdir } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const here = process.cwd();

const distRoot = path.resolve(here, 'dist', 'web');
const distBrowserDir = path.resolve(distRoot, 'browser');
const targetDir = path.resolve(here, '..', 'app', 'static');

async function ensureDir(dir) {
  await mkdir(dir, { recursive: true });
}

async function emptyDir(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  await Promise.all(
    entries.map((e) => rm(path.join(dir, e.name), { recursive: true, force: true })),
  );
}

async function main() {
  if (process.env.DEPLOY_BACKEND_STATIC !== '1') {
    process.stdout.write(
      'Skip deploy: set DEPLOY_BACKEND_STATIC=1 to copy dist to ../app/static\n',
    );
    return;
  }

  await ensureDir(targetDir);
  await emptyDir(targetDir);

  // Angular application builder outputs to dist/<name>/browser (and /server for SSR).
  // We deploy the browser build as backend static root.
  const sourceDir = await (async () => {
    try {
      const entries = await readdir(distBrowserDir);
      return entries.length ? distBrowserDir : distRoot;
    } catch {
      return distRoot;
    }
  })();

  await cp(sourceDir, targetDir, { recursive: true });
  process.stdout.write(`Deployed ${sourceDir} -> ${targetDir}\n`);
}

main().catch((err) => {
  process.stderr.write(`${err?.stack || err}\n`);
  process.exit(1);
});
