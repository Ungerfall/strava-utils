---
name: git-skill
description: Conventions and guardrails for git operations. Use when performing any git command (diff, log, status, staging, branching) or when the user asks about commits, merges, or rebases.
---

# Git

## Instructions

- Always use `git --no-pager` to avoid hanging on interactive pager output
- Use `git --no-pager diff origin/main` to see the developing feature changes
- NEVER run `git commit`. Stage files and suggest a commit message, but let the human create the commit
- NEVER run `git merge` or `git rebase`. Inform the human and let them perform these operations themselves
