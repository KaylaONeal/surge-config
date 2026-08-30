#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "$0")/.." && pwd)
config_home=${SURGE_CONFIG_HOME:-"$HOME/.config/surge-config"}
secret_file=${1:-"$config_home/credentials.env"}
output_dir=${2:-"$repo_dir/build"}

if [[ ! -f "$secret_file" ]]; then
  echo "Missing secrets file: $secret_file" >&2
  echo "Create $config_home/credentials.env from private/secrets.example.env first." >&2
  exit 1
fi

required=(
  SURGE_MANAGED_URL
  HTTPS_USERNAME HTTPS_PASSWORD
  TUIC_USERNAME TUIC_PASSWORD TUIC_UUID
  HY2_USERNAME HY2_PASSWORD
  EDGETUNNEL_UUID
)

while IFS='=' read -r name value || [[ -n "$name" ]]; do
  [[ -z "$name" || "$name" == \#* ]] && continue

  allowed=false
  for expected in "${required[@]}"; do
    if [[ "$name" == "$expected" ]]; then
      allowed=true
      break
    fi
  done

  if [[ "$allowed" != true ]]; then
    echo "Unknown key in secrets file: $name" >&2
    exit 1
  fi

  export "$name=$value"
done < "$secret_file"

for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required secret: $name" >&2
    exit 1
  fi
done

mkdir -p "$output_dir"

render() {
  local source_file=$1
  local output_file=$2

  perl -pe '
    s/__([A-Z0-9_]+)__/
      exists $ENV{$1} ? $ENV{$1} : die "Missing environment value: $1\n"
    /gex
  ' "$source_file" > "$output_file"

  if rg -n '__[A-Z0-9_]+__' "$output_file" >/dev/null; then
    echo "Unresolved placeholder in $output_file" >&2
    exit 1
  fi

  chmod 600 "$output_file"
  echo "Rendered $output_file"
}

render "$repo_dir/surge.conf" "$output_dir/surge.conf"
render "$repo_dir/shadowrocket.conf" "$output_dir/shadowrocket.conf"
