#!/usr/bin/env node
/**
 * Generate NockCC app icon as an SVG, then use sips/iconutil to produce:
 *   assets/icon.png      — 1024x1024 source
 *   assets/icon.icns     — macOS app icon
 *   assets/tray-icon.png — 22x22 menu bar icon (template image)
 *
 * Requirements: macOS with sips and iconutil (built-in).
 * No user input — all paths derived from __dirname.
 */

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ASSETS = path.join(__dirname, '..', 'assets');
const ICONSET = path.join(ASSETS, 'NockCC.iconset');

// SVG icon: dark rounded rect with gradient "N"
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#3B6FD4"/>
      <stop offset="100%" stop-color="#7C5CFC"/>
    </linearGradient>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0a0a0a"/>
      <stop offset="100%" stop-color="#111111"/>
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" rx="228" fill="url(#bg)"/>
  <text x="512" y="640" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif" font-size="580" font-weight="800" fill="url(#g)">N</text>
</svg>`;

// Ensure directories exist
fs.mkdirSync(ASSETS, { recursive: true });
fs.mkdirSync(ICONSET, { recursive: true });

// Write SVG
const svgPath = path.join(ASSETS, 'icon.svg');
fs.writeFileSync(svgPath, svg);

// Use qlmanage to render SVG to PNG (available on all Macs)
const pngPath = path.join(ASSETS, 'icon.png');

try {
  execFileSync('qlmanage', ['-t', '-s', '1024', '-o', ASSETS, svgPath],
    { stdio: 'pipe' });
} catch {
  // qlmanage may return non-zero but still produce output
}

// qlmanage outputs as icon.svg.png — rename it
const qlOutput = path.join(ASSETS, 'icon.svg.png');
if (fs.existsSync(qlOutput)) {
  fs.renameSync(qlOutput, pngPath);
  console.log('Created icon.png (1024x1024)');
}

if (!fs.existsSync(pngPath)) {
  console.log('Could not generate icon.png — skipping .icns and tray icon.');
  fs.unlinkSync(svgPath);
  process.exit(0);
}

// Generate iconset sizes for .icns
const sizes = [16, 32, 64, 128, 256, 512, 1024];
for (const size of sizes) {
  const outFile = path.join(ICONSET, `icon_${size}x${size}.png`);
  execFileSync('sips', ['-z', String(size), String(size), pngPath, '--out', outFile],
    { stdio: 'pipe' });

  // @2x variant
  if (size <= 512) {
    const out2x = path.join(ICONSET, `icon_${size}x${size}@2x.png`);
    const doubleSize = size * 2;
    execFileSync('sips', ['-z', String(doubleSize), String(doubleSize), pngPath, '--out', out2x],
      { stdio: 'pipe' });
  }
}

// Build .icns
const icnsPath = path.join(ASSETS, 'icon.icns');
try {
  execFileSync('iconutil', ['-c', 'icns', ICONSET, '-o', icnsPath], { stdio: 'pipe' });
  console.log('Created icon.icns');
} catch (err) {
  console.log('Warning: iconutil failed —', err.message);
}

// Generate tray icon (22x22)
const trayPath = path.join(ASSETS, 'tray-icon.png');
execFileSync('sips', ['-z', '22', '22', pngPath, '--out', trayPath], { stdio: 'pipe' });
console.log('Created tray-icon.png (22x22)');

// Cleanup
fs.rmSync(ICONSET, { recursive: true, force: true });
fs.unlinkSync(svgPath);
console.log('Done!');
