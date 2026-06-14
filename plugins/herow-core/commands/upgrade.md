---
description: Force-update the herow marketplace and all herow plugins to the latest GitHub version
allowed-tools: Bash
effort: low
---

Update the herow plugin marketplace to the latest published version:

1. Run: `claude plugin marketplace update herow`
2. If the command reports new versions, tell the user to run `/reload-plugins` (or restart the session) so the updated plugins load.
3. If it fails because the marketplace was added from a local path, run `claude plugin marketplace list` and show the user where `herow` points; a local marketplace updates by pulling the repo instead: `git -C <local-path> pull`.
4. Suggest enabling auto-update once (`/plugin` → Marketplaces → herow → Enable auto-update) so this command is rarely needed.
