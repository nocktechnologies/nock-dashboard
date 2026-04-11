#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

// Read prompt from stdin
let prompt = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { prompt += chunk; });
process.stdin.on('end', () => {
  const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const rulesPath = path.join(projectDir, '.claude', 'hooks', 'skill-rules.json');

  if (!fs.existsSync(rulesPath)) {
    process.exit(0);
  }

  const rules = JSON.parse(fs.readFileSync(rulesPath, 'utf8'));
  const promptLower = prompt.toLowerCase();

  // Confidence point values
  const POINTS = {
    keyword: 2,
    keywordPattern: 3,
    pathPattern: 4,
    directoryMatch: 5,
    intentPattern: 4
  };

  // Confidence threshold
  const THRESHOLD = 4;

  const matches = [];

  for (const [skillName, config] of Object.entries(rules.skills || {})) {
    let score = 0;
    const reasons = [];

    // Check exclude patterns first
    if (config.excludePatterns) {
      const excluded = config.excludePatterns.some(p => promptLower.includes(p.toLowerCase()));
      if (excluded) continue;
    }

    // Keyword matching
    if (config.triggers?.keywords) {
      for (const kw of config.triggers.keywords) {
        if (promptLower.includes(kw.toLowerCase())) {
          score += POINTS.keyword;
          reasons.push(`keyword: "${kw}"`);
        }
      }
    }

    // Keyword pattern matching (regex)
    if (config.triggers?.keywordPatterns) {
      for (const pattern of config.triggers.keywordPatterns) {
        try {
          if (new RegExp(pattern, 'i').test(prompt)) {
            score += POINTS.keywordPattern;
            reasons.push(`pattern: ${pattern}`);
          }
        } catch (e) { /* skip bad regex */ }
      }
    }

    // File path detection in prompt
    if (config.triggers?.pathPatterns) {
      for (const pattern of config.triggers.pathPatterns) {
        // Convert glob-like patterns to regex
        const regex = pattern
          .replace(/\*\*/g, '.*')
          .replace(/\*/g, '[^/]*')
          .replace(/\./g, '\\.');
        try {
          if (new RegExp(regex, 'i').test(prompt)) {
            score += POINTS.pathPattern;
            reasons.push(`path: ${pattern}`);
          }
        } catch (e) { /* skip bad regex */ }
      }
    }

    // Directory mapping
    if (config.triggers?.directories) {
      for (const dir of config.triggers.directories) {
        if (prompt.includes(dir)) {
          score += POINTS.directoryMatch;
          reasons.push(`directory: ${dir}`);
        }
      }
    }

    // Intent pattern matching
    if (config.triggers?.intentPatterns) {
      for (const pattern of config.triggers.intentPatterns) {
        try {
          if (new RegExp(pattern, 'i').test(prompt)) {
            score += POINTS.intentPattern;
            reasons.push(`intent: ${pattern}`);
          }
        } catch (e) { /* skip bad regex */ }
      }
    }

    if (score >= THRESHOLD) {
      matches.push({
        skill: skillName,
        score,
        priority: config.priority || 5,
        reasons,
        description: config.description || ''
      });
    }
  }

  if (matches.length === 0) {
    process.exit(0);
  }

  // Sort by score descending, then priority descending
  matches.sort((a, b) => b.score - a.score || b.priority - a.priority);

  // Format output
  const lines = ['SKILL ACTIVATION SUGGESTED\\n'];
  for (const m of matches) {
    const confidence = m.score >= 8 ? 'HIGH' : m.score >= 5 ? 'MEDIUM' : 'LOW';
    lines.push(`${m.skill} (${confidence} confidence)`);
    lines.push(`  → ${m.description}`);
    lines.push(`  Matched: ${m.reasons.join(', ')}`);
    lines.push(`  Read: .claude/skills/${m.skill}/SKILL.md\\n`);
  }

  process.stdout.write(lines.join('\\n'));
});
