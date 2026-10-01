#!/usr/bin/env python3
"""Copy the deployed EdgeTunnel into its isolated account without logging secrets."""

import argparse
import copy
import email
import email.policy
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
import uuid


SOURCE_ACCOUNT = os.environ.get("CF_ACCOUNT_ID", "")
TARGET_ACCOUNT = os.environ.get("CLOUDFLARE_EDGETUNNEL_ACCOUNT_ID", "")
WORKER = "surge-edgetunnel"
OLD_HOST = "edge.fallback.page"


def request(account, token, path, method="GET", value=None, content_type="application/json", raw=False):
    data = None
    if value is not None:
        data = json.dumps(value).encode() if content_type == "application/json" else value
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/{path}",
        method=method, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()
            response_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        try:
            errors = json.load(error).get("errors", [])
        except (ValueError, TypeError):
            errors = []
        sensitive = [token]
        def collect(item):
            if isinstance(item, dict):
                if item.get("type") == "secret_text":
                    sensitive.extend(item.get(key) for key in ["value", "text"] if item.get(key))
                for child in item.values():
                    collect(child)
            elif isinstance(item, list):
                for child in item:
                    collect(child)
        collect(value)
        descriptions = []
        for item in errors[:3]:
            description = str(item.get("message", ""))
            for secret in sensitive:
                description = description.replace(secret, "[REDACTED]")
            descriptions.append({"code": item.get("code"), "message": description[:350]})
        raise RuntimeError(f"{method} {path}: HTTP {error.code}, errors {descriptions}") from None
    if raw:
        return response_type, body
    result = json.loads(body)
    if not result.get("success", False):
        raise RuntimeError(f"{method} {path}: unsuccessful API response")
    return result["result"]


def replace_host(value, new_host):
    if isinstance(value, str):
        return value.replace(OLD_HOST, new_host)
    if isinstance(value, dict):
        return {key: replace_host(item, new_host) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_host(item, new_host) for item in value]
    return value


def multipart(metadata, modules):
    boundary = "edgetunnel-migration-" + uuid.uuid4().hex
    parts = []
    parts.append(("metadata", None, "application/json", json.dumps(metadata).encode()))
    parts.extend(modules)
    body = bytearray()
    for name, filename, content_type, content in parts:
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"'
        body.extend(f"--{boundary}\r\n{disposition}\r\nContent-Type: {content_type}\r\n\r\n".encode())
        body.extend(content)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Deploy into the isolated account")
    args = parser.parse_args()
    source_token = os.environ["cloudflare_api_dns"]
    target_token = os.environ["CLOUDFLARE_EDGETUNNEL_TOKEN"]
    configured_account = os.environ.get("CLOUDFLARE_EDGETUNNEL_ACCOUNT_ID", TARGET_ACCOUNT)
    if (configured_account != TARGET_ACCOUNT or SOURCE_ACCOUNT == TARGET_ACCOUNT
            or not re.fullmatch(r"[a-f0-9]{32}", SOURCE_ACCOUNT)
            or not re.fullmatch(r"[a-f0-9]{32}", TARGET_ACCOUNT)):
        raise RuntimeError("Account isolation guard failed")
    subdomain = request(TARGET_ACCOUNT, target_token, "workers/subdomain")["subdomain"]
    new_host = f"{WORKER}.{subdomain}.workers.dev"
    settings = request(SOURCE_ACCOUNT, source_token, f"workers/scripts/{WORKER}/settings")
    source_kv = next(binding["namespace_id"] for binding in settings["bindings"] if binding["type"] == "kv_namespace")
    content_type, content = request(SOURCE_ACCOUNT, source_token, f"workers/scripts/{WORKER}/content/v2", raw=True)
    message = email.message_from_bytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + content,
        policy=email.policy.default,
    )
    if not message.is_multipart():
        raise RuntimeError("Expected deployed multipart Worker modules")
    modules = []
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename() or name
        if name != "metadata":
            modules.append((name, filename, part.get_content_type(), part.get_payload(decode=True)))
    if len(modules) != 1 or modules[0][1] != "_worker.js":
        raise RuntimeError("Unexpected deployed Worker module layout; review before copying")
    digest = hashlib.sha256(modules[0][3]).hexdigest()
    recovery_path = Path(os.environ.get("SURGE_CONFIG_HOME", str(Path.home() / ".config/surge-config"))) / "edgetunnel.env"
    recovery = dict(re.findall(r"^([A-Z_]+)=(.*)$", recovery_path.read_text(), re.M))
    required = {"ADMIN": "EDGETUNNEL_ADMIN", "KEY": "EDGETUNNEL_KEY", "UUID": "EDGETUNNEL_UUID"}
    if any(not recovery.get(key) for key in required.values()):
        raise RuntimeError("Missing local recovery secrets")
    keys = request(SOURCE_ACCOUNT, source_token, f"storage/kv/namespaces/{source_kv}/keys")
    key_names = {item["name"] for item in keys}
    if key_names != {"config.json", "cf.json", "tg.json"}:
        raise RuntimeError("Unexpected source KV keys; review before migrating")
    kv_values = {}
    for name in sorted(key_names):
        _, value = request(SOURCE_ACCOUNT, source_token, f"storage/kv/namespaces/{source_kv}/values/{name}", raw=True)
        kv_values[name] = replace_host(json.loads(value), new_host)
    config = kv_values["config.json"]
    if config.get("UUID") != recovery["EDGETUNNEL_UUID"]:
        raise RuntimeError("Source KV UUID does not match recovery credentials")
    config["HOST"] = new_host
    config["HOSTS"] = [new_host]
    # Account-specific API credentials must never be inherited from the business account.
    for cf_config in [config.get("CF", {}), kv_values["cf.json"]]:
        for key in ["Email", "GlobalAPIKey", "APIToken", "UsageAPI"]:
            cf_config[key] = ""
        cf_config["AccountID"] = TARGET_ACCOUNT
    inventory = request(TARGET_ACCOUNT, target_token, "workers/scripts")
    if any(item["id"] == WORKER for item in inventory):
        raise RuntimeError("Target Worker already exists; refusing to overwrite")
    print(json.dumps({"source_account": SOURCE_ACCOUNT, "target_account": TARGET_ACCOUNT,
                      "worker": WORKER, "hostname": new_host, "module_sha256": digest,
                      "kv_keys": sorted(key_names), "apply": args.apply}))
    if not args.apply:
        return
    namespaces = request(TARGET_ACCOUNT, target_token, "storage/kv/namespaces")
    if any(item.get("title") == "surge-edgetunnel-kv" for item in namespaces):
        raise RuntimeError("Target KV namespace already exists; refusing to overwrite")
    target_kv = request(TARGET_ACCOUNT, target_token, "storage/kv/namespaces", "POST", {"title": "surge-edgetunnel-kv"})["id"]
    for name, value in kv_values.items():
        request(TARGET_ACCOUNT, target_token, f"storage/kv/namespaces/{target_kv}/values/{name}", "PUT", value)
    bindings = []
    for binding in settings["bindings"]:
        binding = copy.deepcopy(binding)
        if binding["type"] == "kv_namespace":
            binding["namespace_id"] = target_kv
        elif binding["type"] == "secret_text":
            if binding["name"] not in required:
                raise RuntimeError("Unexpected secret binding")
            binding["text"] = recovery[required[binding["name"]]]
        elif binding["type"] != "plain_text":
            raise RuntimeError("Unexpected binding type")
        bindings.append(binding)
    metadata = {"main_module": "_worker.js", "bindings": bindings,
                "compatibility_date": settings["compatibility_date"],
                "compatibility_flags": settings["compatibility_flags"],
                "observability": {"enabled": False}, "logpush": False,
                "tags": ["isolated-edgetunnel-migration-20261001"]}
    body, content_type = multipart(metadata, modules)
    request(TARGET_ACCOUNT, target_token, f"workers/scripts/{WORKER}", "PUT", body, content_type)
    request(TARGET_ACCOUNT, target_token, f"workers/scripts/{WORKER}/subdomain", "POST",
            {"enabled": True, "previews_enabled": False})
    target_settings = request(TARGET_ACCOUNT, target_token, f"workers/scripts/{WORKER}/settings")
    actual_kv = next(item["namespace_id"] for item in target_settings["bindings"] if item["type"] == "kv_namespace")
    if actual_kv != target_kv:
        raise RuntimeError("Target KV binding readback mismatch")
    for name, expected in kv_values.items():
        _, value = request(TARGET_ACCOUNT, target_token, f"storage/kv/namespaces/{target_kv}/values/{name}", raw=True)
        if json.loads(value) != expected:
            raise RuntimeError("Target KV content readback mismatch")
    deployed = request(TARGET_ACCOUNT, target_token, "workers/scripts")
    if not any(item["id"] == WORKER for item in deployed):
        raise RuntimeError("Target Worker inventory readback failed")
    print(json.dumps({"deployed": True, "target_account": TARGET_ACCOUNT, "worker": WORKER,
                      "hostname": new_host, "kv_namespace_id": target_kv,
                      "bindings_verified": len(target_settings["bindings"]), "kv_values_verified": len(kv_values)}))


if __name__ == "__main__":
    main()
