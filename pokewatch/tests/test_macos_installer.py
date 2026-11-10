"""The macOS installer's generated launchd plists must be valid and correct (dry-run; no launchctl)."""

import plistlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_install_dry_run_writes_valid_plists(tmp_path):
    out = subprocess.run(["bash", str(ROOT / "deploy/macos/install.sh"), "--dry-run", str(tmp_path)],
                         check=True, capture_output=True, text=True).stdout.split()
    plists = {Path(p).stem: plistlib.loads(Path(p).read_bytes()) for p in out}
    assert set(plists) == {"com.pokewatch.worker", "com.pokewatch.dashboard", "com.pokewatch.backup"}

    w = plists["com.pokewatch.worker"]
    assert w["ProgramArguments"][:3] == ["/usr/bin/caffeinate", "-i", "-s"]
    assert w["ProgramArguments"][-2:] == [str(ROOT / ".venv/bin/pokewatch"), "worker"]
    assert w["KeepAlive"] is True and w["RunAtLoad"] is True
    assert w["WorkingDirectory"] == str(ROOT)

    d = plists["com.pokewatch.dashboard"]
    assert "--server.address=127.0.0.1" in d["ProgramArguments"]  # not exposed to the network

    b = plists["com.pokewatch.backup"]
    assert b["StartCalendarInterval"] == {"Hour": 3, "Minute": 15}
    assert "KeepAlive" not in b


def test_no_dashboard_option(tmp_path):
    out = subprocess.run(["bash", str(ROOT / "deploy/macos/install.sh"), "--dry-run", str(tmp_path), "--no-dashboard"],
                         check=True, capture_output=True, text=True).stdout.split()
    assert sorted(Path(p).stem for p in out) == ["com.pokewatch.backup", "com.pokewatch.worker"]
