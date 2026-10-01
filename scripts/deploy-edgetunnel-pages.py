#!/usr/bin/env python3
"""Deploy the verified EdgeTunnel module as isolated Pages Functions."""

import argparse
import email
import email.policy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import uuid


ACCOUNT = os.environ.get("CLOUDFLARE_EDGETUNNEL_ACCOUNT_ID", "")
PROJECT = "edge-bcd7d61c"
WORKER = "surge-edgetunnel"
EXPECTED_SHA = "c104ee5b19f2bfefdf27c2af5f9d3ff222d46dd8104b2fa8e87ac829d7b0f945"


def form(parts):
    boundary = "edgetunnel-pages-" + uuid.uuid4().hex
    result = bytearray()
    for name, filename, content_type, content in parts:
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"'
        result.extend(f"--{boundary}\r\n{disposition}\r\nContent-Type: {content_type}\r\n\r\n".encode())
        result.extend(content)
        result.extend(b"\r\n")
    result.extend(f"--{boundary}--\r\n".encode())
    return bytes(result), f"multipart/form-data; boundary={boundary}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("migration", Path(__file__).with_name("migrate-edgetunnel-account.py"))
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    token = os.environ["CLOUDFLARE_EDGETUNNEL_TOKEN"]
    if not re.fullmatch(r"[a-f0-9]{32}", ACCOUNT):
        raise RuntimeError("Target account guard failed")
    def api(path, method="GET", value=None, content_type="application/json", raw=False):
        return migration.request(ACCOUNT, token, path, method, value, content_type, raw)
    settings = api(f"workers/scripts/{WORKER}/settings")
    content_type, body = api(f"workers/scripts/{WORKER}/content/v2", raw=True)
    message = email.message_from_bytes(f"Content-Type: {content_type}\r\n\r\n".encode() + body, policy=email.policy.default)
    parts = list(message.iter_parts())
    if len(parts) != 1 or parts[0].get_filename() != "_worker.js":
        raise RuntimeError("Unexpected source module layout")
    module = parts[0].get_payload(decode=True)
    if hashlib.sha256(module).hexdigest() != EXPECTED_SHA:
        raise RuntimeError("Deployed module checksum changed; review required")
    recovery = dict(re.findall(r"^([A-Z_]+)=(.*)$", (Path.home() / ".config/surge-config/edgetunnel.env").read_text(), re.M))
    secrets = {"ADMIN": "EDGETUNNEL_ADMIN", "KEY": "EDGETUNNEL_KEY", "UUID": "EDGETUNNEL_UUID"}
    env_vars = {}
    kv_namespaces = {}
    for binding in settings["bindings"]:
        name, kind = binding["name"], binding["type"]
        if kind == "plain_text":
            env_vars[name] = {"type": "plain_text", "value": binding["text"]}
        elif kind == "secret_text" and name in secrets:
            env_vars[name] = {"type": "secret_text", "value": recovery[secrets[name]]}
        elif kind == "kv_namespace":
            kv_namespaces[name] = {"namespace_id": binding["namespace_id"]}
        else:
            raise RuntimeError("Unsupported binding")
    env_vars["HOST"] = {"type": "plain_text", "value": f"{PROJECT}.pages.dev"}
    production = {"compatibility_date": settings["compatibility_date"],
                  "compatibility_flags": settings["compatibility_flags"],
                  "env_vars": env_vars, "kv_namespaces": kv_namespaces,
                  "fail_open": False}
    projects = api("pages/projects")
    existing = next((project for project in projects if project["name"] == PROJECT), None)
    if existing:
        actual = existing.get("deployment_configs", {}).get("production", {}).get("kv_namespaces", {}).get("KV", {})
        if actual.get("namespace_id") != kv_namespaces["KV"]["namespace_id"]:
            raise RuntimeError("Existing project is not the isolated EdgeTunnel deployment")
    print(json.dumps({"account": ACCOUNT, "project": PROJECT, "module_sha256": EXPECTED_SHA,
                      "kv_binding_names": list(kv_namespaces), "env_binding_names": list(env_vars), "apply": args.apply}))
    if not args.apply:
        return
    if existing:
        project = api(f"pages/projects/{PROJECT}", "PATCH", {"deployment_configs": {"production": production, "preview": {"fail_open": False}}})
    else:
        project = api("pages/projects", "POST", {"name": PROJECT, "production_branch": "main",
                      "deployment_configs": {"production": production, "preview": {"fail_open": False}}, "build_config": {"build_command": "", "destination_dir": ""}})
    hostname = project["subdomain"]
    if hostname != f"{PROJECT}.pages.dev":
        raise RuntimeError("Unexpected Pages hostname; review before publishing")
    body, content_type = form([
        ("manifest", None, "application/json", b"{}"),
        ("branch", None, "text/plain", b"main"),
        ("commit_message", None, "text/plain", b"Isolated EdgeTunnel Pages ingress"),
        ("_worker.js", "_worker.js", "application/javascript+module", module),
        ("_routes.json", "_routes.json", "application/json", b'{"version":1,"include":["/*"],"exclude":[]}'),
    ])
    deployment = api(f"pages/projects/{PROJECT}/deployments", "POST", body, content_type)
    print(json.dumps({"deployed": True, "account": ACCOUNT, "project": PROJECT,
                      "hostname": hostname, "deployment_id": deployment["id"],
                      "latest_stage": deployment.get("latest_stage"), "fail_open": False}))


if __name__ == "__main__":
    main()
