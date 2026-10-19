#!/usr/bin/env python3
"""Review or apply a rendered profile to this Mac's existing Surge profile."""

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
ACTIVE = Path.home() / "Library/Application Support/Surge/Profiles/surge.conf"
CLI = Path("/Applications/Surge.app/Contents/Applications/surge-cli")
REQUIRED_SECTIONS = {"General", "Proxy", "Proxy Group", "Rule"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def validate(data):
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Rendered profile is not UTF-8") from None
    if re.search(r"__[A-Z0-9_]+__", content):
        raise ValueError("Rendered profile contains unresolved placeholders")
    sections = set(re.findall(r"^\s*\[([^\]\r\n]+)\]\s*$", content, re.M))
    missing = REQUIRED_SECTIONS - sections
    if missing:
        raise ValueError("Rendered profile lacks required sections: " + ", ".join(sorted(missing)))
    for line in content.splitlines():
        for url in re.findall(r"(?:^|,\s*)(?:test-url|internet-test-url|proxy-test-url|url)\s*=\s*([^,\s]+)", line):
            if not url.startswith("http://"):
                raise ValueError("Mac 5.7.6 requires HTTP health-test URLs; use standalone scripts for HTTPS API verification")
    return content


def atomic_write(path, data):
    descriptor, temporary = tempfile.mkstemp(prefix=".surge-apply-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def reload_profile():
    # CLI diagnostics can contain protected profile URLs; never forward them.
    result = subprocess.run([str(CLI), "reload"], capture_output=True, timeout=30)
    if result.returncode or b"success" not in result.stdout.lower():
        raise RuntimeError("Surge reload failed (exit code %d)" % result.returncode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rendered", type=Path, default=ROOT / "build/surge.conf",
                        help="Already rendered input (default: build/surge.conf); no downloads or rendering")
    parser.add_argument("--apply", action="store_true", help="Back up, atomically replace, and reload the fixed local profile")
    parser.add_argument("--expected-current-sha256", help="Required with --apply: active SHA256 from the reviewed dry-run")
    args = parser.parse_args()
    if args.apply and not args.expected_current_sha256:
        parser.error("--apply requires --expected-current-sha256 from a reviewed dry-run")
    if args.expected_current_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_current_sha256):
        parser.error("--expected-current-sha256 must contain 64 hexadecimal characters")
    if not CLI.is_file() or not os.access(CLI, os.X_OK):
        raise ValueError("Expected local surge-cli executable is unavailable")
    if ACTIVE.is_symlink() or not ACTIVE.is_file():
        raise ValueError("Expected active local profile must be a regular, non-symlink file")
    candidate = args.rendered.read_bytes()
    content = validate(candidate)
    original = ACTIVE.read_bytes()
    original_sha = sha256(original)
    if args.expected_current_sha256 and original_sha != args.expected_current_sha256.lower():
        raise ValueError("Active profile changed since review; refusing to overwrite it")
    changes = list(difflib.ndiff(original.decode("utf-8-sig").splitlines(), content.splitlines()))
    result = {
        "mode": "apply" if args.apply else "dry-run",
        "active_profile": str(ACTIVE),
        "rendered_profile": str(args.rendered.resolve()),
        "cli": str(CLI),
        "active_sha256": original_sha,
        "rendered_sha256": sha256(candidate),
        "added_lines": sum(line.startswith("+ ") for line in changes),
        "removed_lines": sum(line.startswith("- ") for line in changes),
        "changed": original != candidate,
        "reloaded": False,
    }
    if not args.apply or original == candidate:
        print(json.dumps(result))
        return
    backup_root = ROOT / "build/local-backups"
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup_root.chmod(0o700)
    backup_dir = backup_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_dir.mkdir(mode=0o700)
    backup = backup_dir / "surge.conf"
    atomic_write(backup, original)
    if ACTIVE.is_symlink() or sha256(ACTIVE.read_bytes()) != original_sha:
        raise ValueError("Active profile changed before replacement; refusing to overwrite it")
    atomic_write(ACTIVE, candidate)
    try:
        reload_profile()
    except BaseException:
        # Preserve a manual edit made while reload was running.
        if ACTIVE.is_symlink() or sha256(ACTIVE.read_bytes()) != sha256(candidate):
            print(json.dumps({"error": "Reload failed; active profile changed again, so automatic rollback was refused",
                              "backup": str(backup)}), file=sys.stderr)
            return 1
        atomic_write(ACTIVE, original)
        rollback_reloaded = False
        try:
            reload_profile()
            rollback_reloaded = True
        except (OSError, RuntimeError, subprocess.SubprocessError):
            pass
        print(json.dumps({"error": "Reload failed; original profile restored", "backup": str(backup),
                          "rollback_reloaded": rollback_reloaded}), file=sys.stderr)
        return 1
    result.update({"backup": str(backup), "reloaded": True})
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, UnicodeDecodeError, subprocess.SubprocessError) as error:
        # Do not include file contents or subprocess output in errors.
        if isinstance(error, OSError):
            message = "Local file or CLI operation failed (%s)" % type(error).__name__
        elif isinstance(error, subprocess.SubprocessError):
            message = "Surge CLI operation did not complete"
        else:
            message = str(error)
        print(json.dumps({"error": message}), file=sys.stderr)
        sys.exit(1)
