---
name: feedback-delegate-model-via-subagent
description: Route ALL work through subagents with the model I set per plan tags; never ask the user about model or to switch /model
metadata: 
  node_type: memory
  type: feedback
  originSessionId: fa81ee15-ba84-4599-81f3-33b8e8727219
---

The user wants EVERY task delegated to a subagent, with me setting the required model on each subagent myself — and to NEVER ask him which model to use or to switch `/model` again. He considers such questions a waste of time ("все делаем через субагентов сам им выставляй необходимую модель укажи это конкретно в плане, чтоб больше не задавать таких вопросов и не терять время").

This applies even to context-heavy work (e.g. Phase 2 decomposition of ED_AP.py, where services must stay consistent). For those, give the subagent a precise scope AND point it at the context files (`.claude/planning/plans/*.md`, `.claude/planning/memory/*.md`) so its cold start is cheap. Do not fall back to "do it inline on the current model" — route it through a subagent.

**Why:** I cannot change the main session's model anyway (`/model` is a user-only interactive control), and being asked to switch it, or being asked which model to pick, is friction he expects me to absorb.

**How to apply:** For every task, spawn an Agent subagent with `model` set per the plan's model tags — Sonnet for mechanical edits / code moves (Phase 1/2/5), Opus for architecture (Phase 3/4/6 — FuelState, Watchdog/state-machine, focus-loss), Haiku for trivial. After each coding subagent, run a read-only QA subagent ([[feedback-qa-subagent-before-commit]]); then I commit+push from the main session ([[feedback-commit-per-iteration]]). Never ask the user about model choice. This SUPERSEDES the old TODO delegation rule ("subagent only if self-contained; otherwise inline + switch /model") — now everything is a subagent.
