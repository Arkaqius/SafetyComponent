import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const frontend = fileURLToPath(new URL('..', import.meta.url));
const repository = path.dirname(frontend);
const base = process.env.FRONTEND_FORMAT_BASE || 'HEAD';
const git = (...args) => execFileSync('git', args, { cwd: repository, encoding: 'utf8' });
git('rev-parse', '--verify', `${base}^{commit}`);
const changed = git('diff', '--name-only', '--diff-filter=ACMR', '-z', base, '--', 'frontend');
const untracked = git('ls-files', '--others', '--exclude-standard', '-z', '--', 'frontend');
const files = [...new Set(`${changed}${untracked}`.split('\0'))]
  .filter(file => file.startsWith('frontend/') && /\.(?:tsx?|json)$/.test(file))
  .map(file => path.relative(frontend, path.join(repository, file)))
  .filter(file => existsSync(path.join(frontend, file)));

if (files.length === 0) {
  console.log('No changed frontend TypeScript/JSON files to format-check.');
} else {
  execFileSync(process.execPath, [path.join(frontend, 'node_modules/prettier/bin/prettier.cjs'), '--check', ...files], {
    cwd: frontend,
    stdio: 'inherit',
  });
}
