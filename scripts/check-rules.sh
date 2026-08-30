#!/usr/bin/env bash
set -uo pipefail

repo_dir=$(cd "$(dirname "$0")/.." && pwd)
repo_raw_prefix=https://raw.githubusercontent.com/KaylaONeal/surge-config/main/
failed=0

urls=$(
  rg --no-filename --only-matching 'https://[^,[:space:]]+\.(list|txt)' \
    "$repo_dir/surge.conf" "$repo_dir/shadowrocket.conf" |
    sort -u
)

for url in $urls; do
  if [[ "$url" == "$repo_raw_prefix"* ]]; then
    relative_path=${url#"$repo_raw_prefix"}
    if [[ -f "$repo_dir/$relative_path" ]]; then
      echo "OK $url (local)"
      continue
    fi
  fi

  status=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 25 --retry 2 "$url")
  if [[ "$status" == 200 ]]; then
    echo "OK $url"
  else
    echo "FAIL $url (HTTP $status)" >&2
    failed=1
  fi
done

exit "$failed"
