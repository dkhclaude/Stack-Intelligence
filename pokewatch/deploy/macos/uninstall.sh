#!/usr/bin/env bash
# Stop and remove the PokéWatch LaunchAgents. Your data (data/pokewatch.db, backups, .env) is kept.
set -euo pipefail
for label in com.pokewatch.worker com.pokewatch.dashboard com.pokewatch.backup; do
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  plist="$HOME/Library/LaunchAgents/$label.plist"
  if [[ -f "$plist" ]]; then
    rm -- "$plist"
    echo "removed $label"
  fi
done
echo "PokéWatch services removed. Data in data/ was not touched."
