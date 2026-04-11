#!/bin/bash
# Skill Auto-Activation Hook
# Runs on UserPromptSubmit — analyzes prompt and suggests relevant skills
# Adapted from ChrisWiles/claude-code-showcase

# Read prompt from stdin (Claude Code pipes it)
PROMPT=$(cat)

# Run the JS matching engine
RESULT=$(echo "$PROMPT" | node "$CLAUDE_PROJECT_DIR/.claude/hooks/skill-eval.js" 2>/dev/null)

# If skills matched, output as feedback (non-blocking)
if [ -n "$RESULT" ] && [ "$RESULT" != "null" ] && [ "$RESULT" != "{}" ]; then
    echo "{\"feedback\": \"$RESULT\"}"
fi

exit 0
