---
name: feedback-delegate-model-via-subagent
description: "For non-default-model work, launch a model-specific subagent yourself — don't tell the user to switch /model"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: fa81ee15-ba84-4599-81f3-33b8e8727219
---

When a task should run on a different model than the main session (e.g. Sonnet for mechanical code edits per the delegation rules in [[edap-cleanup-project]]), launch a subagent with that model set — do NOT ask the user to run `/model` manually. The user found being told to switch himself annoying ("как дурак должен что-то переключать") and expected me to handle model selection via subagents.

**Why:** I cannot change the main session's model (that's a user-only interactive control), but I *can* spawn subagents on any model. Pushing the manual switch onto the user is friction he expected me to absorb.

**How to apply:** For self-contained mechanical work tagged Sonnet/Haiku, run it via an Agent subagent with `model` set (e.g. `model: "sonnet"`); I orchestrate/commit from the main session. Only consider asking the user to switch when the work genuinely must run inline with heavy shared context (Phase 2 decomposition) AND model cost matters — and even then, prefer just proceeding on the current model over blocking on him. Supersedes the "switch /model for INLINE tasks" wording in the TODO's delegation rule.
