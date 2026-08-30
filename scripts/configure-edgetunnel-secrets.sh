#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "$0")/.." && pwd)
worker_config=${1:?Usage: configure-edgetunnel-secrets.sh <wrangler-config>}
secret_file="$repo_dir/private/edgetunnel.env"
wrangler_version=4.127.1

admin_value=$(openssl rand -hex 24)
key_value=$(openssl rand -hex 16)
uuid_value=$(uuidgen | tr '[:upper:]' '[:lower:]')

printf '%s' "$admin_value" | npx --yes "wrangler@$wrangler_version" secret put ADMIN --config "$worker_config"
printf '%s' "$key_value" | npx --yes "wrangler@$wrangler_version" secret put KEY --config "$worker_config"
printf '%s' "$uuid_value" | npx --yes "wrangler@$wrangler_version" secret put UUID --config "$worker_config"

umask 077
{
  printf 'EDGETUNNEL_ADMIN=%s\n' "$admin_value"
  printf 'EDGETUNNEL_KEY=%s\n' "$key_value"
  printf 'EDGETUNNEL_UUID=%s\n' "$uuid_value"
} > "$secret_file"

chmod 600 "$secret_file"
echo "Rotated EdgeTunnel credentials and saved $secret_file"
