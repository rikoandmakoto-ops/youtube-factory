#!/bin/bash
cd ~/Developer/youtube-factory
echo "=== youtube-factory cleanup ==="
git worktree prune
echo "Pruned worktrees"
git branch --merged main | grep -v '^\*' | grep -v '^  main$' | xargs git branch -d 2>/dev/null
echo "Deleted merged branches"
# Delete the WIP branch that was never completed
git branch -D claude/competent-hugle-ef6c41 2>/dev/null
echo "Deleted WIP branch"

cd ~/Developer/fanup
echo "=== fanup cleanup ==="
git branch --merged main | grep -v '^\*' | grep -v '^  main$' | xargs git branch -d 2>/dev/null
echo "Deleted merged branches"

cd ~/Developer/ai-english-coach
echo "=== ai-english-coach cleanup ==="
git worktree prune 2>/dev/null
echo "Pruned worktrees"

echo ""
echo "=== Done! ==="
read -p "Press Enter to close..."
