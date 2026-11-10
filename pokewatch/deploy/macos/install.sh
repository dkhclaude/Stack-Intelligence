#!/usr/bin/env bash
# PokéWatch — install as background services on macOS (launchd).
#
#   cd pokewatch && ./deploy/macos/install.sh
#
# Creates three LaunchAgents for your user account:
#   com.pokewatch.worker     monitoring worker; restarts if it crashes; keeps the Mac awake while running
#   com.pokewatch.dashboard  Streamlit dashboard on http://localhost:8501
#   com.pokewatch.backup     daily 03:15 SQLite backup into data/backups (14 kept)
#
# Options:
#   --dry-run DIR   only write the .plist files into DIR (no venv, no launchctl). Used by tests.
#   --no-dashboard  don't install the dashboard service
set -euo pipefail

DRY_RUN_DIR=""
WITH_DASHBOARD=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN_DIR="$2"; shift 2 ;;
    --no-dashboard) WITH_DASHBOARD=0; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$APP_DIR/.venv"
LOG_DIR="$APP_DIR/data/logs"
AGENTS_DIR="${DRY_RUN_DIR:-$HOME/Library/LaunchAgents}"
LABEL_PREFIX="com.pokewatch"

if [[ "$APP_DIR" == *[\&\<\>]* ]]; then
  echo "The folder path contains &, < or >, which launchd plists can't hold safely: $APP_DIR" >&2
  echo "Move the pokewatch folder somewhere like ~/pokewatch and run this again." >&2
  exit 1
fi

say() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------- python + deps
if [[ -z "$DRY_RUN_DIR" ]]; then
  if [[ "$(uname)" != "Darwin" ]]; then
    echo "This installer is for macOS. On Linux use deploy/pokewatch-worker.service or Docker." >&2
    exit 1
  fi
  PY=""
  for cand in python3.13 python3.12 python3; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
      PY="$(command -v "$cand")"; break
    fi
  done
  if [[ -z "$PY" ]]; then
    echo "Python 3.12+ not found. Install it with:  brew install python@3.12" >&2
    exit 1
  fi
  say "Using $PY"
  [[ -d "$VENV" ]] || "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"
  "$VENV/bin/pip" install -q --no-deps -e "$APP_DIR"

  if [[ ! -f "$APP_DIR/.env" ]]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    say "Created $APP_DIR/.env from the template — add your keys there, then re-run this script."
  fi
  mkdir -p "$LOG_DIR" "$APP_DIR/data/backups"
  (cd "$APP_DIR" && "$VENV/bin/pokewatch" init-db)
fi
mkdir -p "$AGENTS_DIR"

# ---------------------------------------------------------------- plist writer
write_plist() {  # label, program args (one per line), extra xml
  local label="$1" args="$2" extra="$3"
  local file="$AGENTS_DIR/$label.plist"
  {
    cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>ProgramArguments</key>
  <array>
EOF
    while IFS= read -r a; do [[ -n "$a" ]] && printf '    <string>%s</string>\n' "$a"; done <<< "$args"
    cat <<EOF
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$VENV/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>JSON_LOGS</key><string>true</string>
  </dict>
  <key>StandardOutPath</key><string>$LOG_DIR/${label#$LABEL_PREFIX.}.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/${label#$LABEL_PREFIX.}.log</string>
$extra
</dict>
</plist>
EOF
  } > "$file"
  echo "$file"
}

KEEPALIVE='  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>ProcessType</key><string>Background</string>'

# caffeinate -i -s: no idle sleep (and no system sleep on AC power) while the worker runs
WORKER=$(write_plist "$LABEL_PREFIX.worker" "/usr/bin/caffeinate
-i
-s
$VENV/bin/pokewatch
worker" "$KEEPALIVE")

PLISTS=("$WORKER")
if [[ $WITH_DASHBOARD -eq 1 ]]; then
  DASH=$(write_plist "$LABEL_PREFIX.dashboard" "$VENV/bin/streamlit
run
$APP_DIR/dashboard/app.py
--server.port=8501
--server.address=127.0.0.1
--server.headless=true" "$KEEPALIVE")
  PLISTS+=("$DASH")
fi

BACKUP=$(write_plist "$LABEL_PREFIX.backup" "/bin/bash
$APP_DIR/deploy/backup_sqlite.sh
$APP_DIR/data/pokewatch.db" '  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>15</integer></dict>')
PLISTS+=("$BACKUP")

if [[ -n "$DRY_RUN_DIR" ]]; then
  printf '%s\n' "${PLISTS[@]}"
  exit 0
fi

# ---------------------------------------------------------------- load services
for p in "${PLISTS[@]}"; do
  plutil -lint "$p" >/dev/null
  label="$(basename "$p" .plist)"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$p"
  say "loaded $label"
done

cat <<EOF

PokéWatch is running in the background.
  Dashboard:   http://localhost:8501
  Status:      launchctl list | grep pokewatch
  Worker log:  tail -f "$LOG_DIR/worker.log"
  Health:      (cd "$APP_DIR" && .venv/bin/pokewatch health)
  Uninstall:   ./deploy/macos/uninstall.sh

IMPORTANT — keep the Mac awake:
  * System Settings > Energy (or Battery > Options): turn ON "Prevent automatic sleeping
    when the display is off" (on power adapter) and "Wake for network access".
  * Or from Terminal (applies on power adapter only):  sudo pmset -c sleep 0
  * MacBook: closing the lid sleeps the Mac unless it's on power with an external display.
    Keep the lid open, or see docs/DEPLOYMENT.md for the lid-closed option.
  * After a power cut: System Settings > Energy > "Start up automatically after a power failure"
    (desktop Macs), and enable automatic login so the services start without you.
EOF
