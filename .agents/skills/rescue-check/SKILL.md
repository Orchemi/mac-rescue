---
name: rescue-check
description: Validate mac-rescue changes to process collection, stop safeguards, native bridge, UI, settings, or installation. Use for Rescue development checks, not for killing real user processes or general Mac cleanup.
---

Read AGENTS.md and docs/development.md from the repository root.

Run `bash scripts/verify.sh` from that root. For Swift, native bridge, or build changes,
run `python3 scripts/build-check.py`; this compiles without updating the user's installed app.
Do not substitute `install-rescue.py` for a build check. Installation needs a user installation request.

For process-stop changes, inspect the preview/execute boundary in `rescue_gui.py` and the identity
checks in `mac-rescue.py`. Tests must cover expired plans, PID reuse/identity changes, foreign owners,
and protected processes as appropriate to the change. Never run group-stop tests on existing user work.

For Swift/bridge changes, verify the method names, JSON shape, pipe framing and error paths on both sides.
A compile pass alone does not prove the real GUI flow. Use owned fixtures for any destructive UI test.

Report the changed behavior, checks run, failures and any unverified runtime behavior.
Do not claim that source checks updated the installed app or that high RSS alone proves a leak.
