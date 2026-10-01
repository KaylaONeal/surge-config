#!/usr/bin/env python3
"""Probe verified TLS and WebSocket ingress; no authentication values are logged."""

import argparse
import base64
import hashlib
import json
import os
import socket
import ssl
import time


def probe(address, port, sni, host, timeout):
    started = time.monotonic()
    stage = "tcp"
    result = {"address": address, "port": port, "sni": sni, "host": host}
    connection = None
    try:
        raw = socket.create_connection((address, port), timeout=timeout)
        stage = "tls"
        connection = ssl.create_default_context().wrap_socket(raw, server_hostname=sni)
        connection.settimeout(timeout)
        result["tls"] = connection.version()
        stage = "websocket"
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: Upgrade\r\n"
            f"Upgrade: websocket\r\nSec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Key: {key}\r\n\r\n"
        )
        connection.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response and len(response) < 16384:
            block = connection.recv(4096)
            if not block:
                break
            response += block
        header = response.split(b"\r\n\r\n", 1)[0].decode("latin-1")
        result["http"] = header.split("\r\n", 1)[0]
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        result["upgrade_valid"] = " 101 " in result["http"] and expected.lower() in header.lower()
    except Exception as error:
        result["failed_stage"] = stage
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        if connection:
            connection.close()
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="edge-bcd7d61c.pages.dev")
    parser.add_argument("--address", action="append", required=True)
    parser.add_argument("--sni", action="append")
    parser.add_argument("--port", type=int, action="append")
    parser.add_argument("--timeout", type=float, default=4)
    args = parser.parse_args()
    for address in args.address:
        for port in args.port or [443]:
            for sni in args.sni or [args.host]:
                print(json.dumps(probe(address, port, sni, args.host, args.timeout)), flush=True)


if __name__ == "__main__":
    main()
