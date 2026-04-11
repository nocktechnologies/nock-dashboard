const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  canonicalizePath,
  isPathWithinRoots,
  sanitizeDevRoots,
} = require('../electron/security-utils');

function makeSandbox() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nock-terminal-'));
  test.after(() => {
    fs.rmSync(dir, { recursive: true, force: true });
  });
  return dir;
}

test('isPathWithinRoots rejects sibling prefix matches', () => {
  const sandbox = makeSandbox();
  const allowedRoot = path.join(sandbox, 'work');
  const sibling = `${allowedRoot}-outside`;

  fs.mkdirSync(allowedRoot, { recursive: true });
  fs.mkdirSync(sibling, { recursive: true });

  const siblingFile = path.join(sibling, 'notes.txt');
  fs.writeFileSync(siblingFile, 'nope', 'utf8');

  assert.equal(isPathWithinRoots(siblingFile, [allowedRoot]), false);
});

test('isPathWithinRoots resolves symlink escapes before allowing access', { skip: process.platform === 'win32' }, () => {
  const sandbox = makeSandbox();
  const allowedRoot = path.join(sandbox, 'work');
  const outsideRoot = path.join(sandbox, 'outside');
  const linkPath = path.join(allowedRoot, 'linked');
  const escapedFile = path.join(linkPath, 'secret.txt');

  fs.mkdirSync(allowedRoot, { recursive: true });
  fs.mkdirSync(outsideRoot, { recursive: true });
  fs.writeFileSync(path.join(outsideRoot, 'secret.txt'), 'classified', 'utf8');
  fs.symlinkSync(outsideRoot, linkPath, 'dir');

  assert.equal(isPathWithinRoots(escapedFile, [allowedRoot]), false);
});

test('sanitizeDevRoots removes unsafe entries and deduplicates valid directories', () => {
  const sandbox = makeSandbox();
  const projectRoot = path.join(sandbox, 'projects');
  fs.mkdirSync(projectRoot, { recursive: true });

  const sanitized = sanitizeDevRoots([
    path.parse(projectRoot).root,
    os.homedir(),
    projectRoot,
    canonicalizePath(projectRoot),
    path.join(projectRoot, 'missing'),
  ]);

  assert.deepEqual(sanitized, [canonicalizePath(projectRoot)]);
});
