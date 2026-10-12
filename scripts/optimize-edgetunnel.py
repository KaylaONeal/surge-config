#!/usr/bin/env python3
"""Apply a bounded, reproducible patch to the checksum-pinned upstream module."""
import hashlib
from pathlib import Path

BASE_SHA = 'c104ee5b19f2bfefdf27c2af5f9d3ff222d46dd8104b2fa8e87ac829d7b0f945'
ROOT = Path(__file__).resolve().parent.parent

def optimize(module):
    if hashlib.sha256(module).hexdigest() != BASE_SHA:
        raise ValueError('Unreviewed EdgeTunnel source; refusing to patch')
    text = module.decode()
    start = text.index('async function connectStreams(')
    end = text.index('__name(connectStreams, "connectStreams");', start)
    relay = (ROOT / 'cloudflare/edgetunnel/stream-relay.mjs').read_text().replace('export async function', 'async function', 1)
    text = text[:start] + relay + '\n' + text[end:]
    # env.UUID is already the sole WebSocket authentication identity when valid.
    # Move derivation after validation and skip only the otherwise-unused hash.
    original = '    const userIDMD5 = await MD5MD5('
    line = next(x for x in text.splitlines() if x.startswith(original))
    text = text.replace(line + '\n', '', 1)
    env_line = next(x for x in text.splitlines() if x.strip() == 'const envUUID = env.UUID || env.uuid;')
    derived = line.replace('await MD5MD5(', '(upgradeHeader === "websocket" && envUUID && uuidRegex.test(envUUID)) ? null : await MD5MD5(')
    text = text.replace(env_line, env_line + '\n' + derived, 1)
    return text.encode()

if __name__ == '__main__':
    import sys
    output = optimize(Path(sys.argv[1]).read_bytes())
    dest = Path(sys.argv[2]); dest.write_bytes(output); dest.chmod(0o600)
    print('optimized sha256:', hashlib.sha256(output).hexdigest())
