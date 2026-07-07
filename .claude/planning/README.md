# Planning snapshot (synced via git)

This folder mirrors two things Claude Code normally keeps local-only on one machine:

- `plans/` — mirrors `~/.claude/plans/*.md` (the project plan + TODO checklist).
- `memory/` — mirrors `~/.claude/projects/<project-id>/memory/*.md` (Claude's persistent
  memory about this project: decisions, environment setup, feedback).

It exists so the same context is available from any machine that clones this repo
(e.g. switching between a work PC and a home PC), instead of being stuck on whichever
machine originally created the files.

**This is a manually maintained mirror, not a live symlink.** After a session where
Claude updates the plan/TODO or writes new memory, copy the changed files here and
commit them (Claude can be asked to do this as part of wrapping up a session). When
starting a session on a different machine, tell Claude to read from here first, or
copy these files back into `~/.claude/plans/` and `~/.claude/projects/<project-id>/memory/`
before starting.

Rest of `.claude/` (settings, session transcripts, local project cache) stays
machine-local and gitignored — only this `planning/` subfolder is tracked.
