#!/usr/bin/env bash
set -uo pipefail

repo_dir=$(cd "$(dirname "$0")/.." && pwd)
repo_raw_prefix=https://raw.githubusercontent.com/KaylaONeal/surge-config/main/
failed=0

urls=$(
  grep -hEo 'https://[^,[:space:]]+\.(list|txt)' \
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

# AI routing must remain safe even when every external RULE-SET is unavailable.
for profile in "$repo_dir/surge.conf" "$repo_dir/shadowrocket.conf"; do
  for domain in \
    openai.com chatgpt.com oaistatic.com oaiusercontent.com sora.com \
    anthropic.com claude.ai claude.com claudeusercontent.com claude.site \
    claudemcpclient.com claudemcpcontent.com; do
    if ! grep -Eq "^DOMAIN-SUFFIX,${domain//./\\.},AI$" "$profile"; then
      echo "FAIL $profile missing inline AI rule for $domain" >&2
      failed=1
    fi
  done

  if ! grep -Eq '^RULE-SET,https://raw\.githubusercontent\.com/KaylaONeal/surge-config/main/rules/ai-extra\.list,AI$' "$profile"; then
    echo "FAIL $profile does not use the maintained AI rule list" >&2
    failed=1
  fi

  if ! grep -Eq '^Fallback = select, DIRECT,' "$profile"; then
    echo "FAIL $profile must keep DIRECT as the default fallback" >&2
    failed=1
  fi

  if grep -E '^AI = ' "$profile" | grep -Eq '(DIRECT|CF Edge Auto|JP Auto|KR Auto)'; then
    echo "FAIL $profile AI policy contains a non-US/direct option" >&2
    failed=1
  fi
done


for broad_domain in auth0.com stripe.com sentry.io intercom.io segment.io statsigapi.net; do
  if grep -Eq "^DOMAIN-SUFFIX,${broad_domain//./\\.}$" "$repo_dir/rules/ai-extra.list"; then
    echo "FAIL AI rules contain broad shared-vendor domain: $broad_domain" >&2
    failed=1
  fi
done

exit "$failed"
