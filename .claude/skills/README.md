# Printing Press skills (vendored)

These skills were copied from the upstream Printing Press project at
https://github.com/mvanhorn/cli-printing-press (MIT licensed, by Matt Van Horn
and Trevin Chow, 2026). Their license is preserved in `UPSTREAM_LICENSE.txt`.

Why they live here:
  - so this repo carries its own toolset (no global Claude Code install required)
  - so the skills are version-pinned alongside the project

To upgrade, re-run:
  npx -y skills add mvanhorn/cli-printing-press/skills --skill '*' -g -a claude-code -y
  cp -r ~/.claude/skills/printing-press* /path/to/hunter/.claude/skills/

Skills work in any Claude Code session opened from this folder.
