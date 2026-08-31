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

# Company domains must bypass encrypted DNS and resolve through the system DNS.
surge_profile="$repo_dir/surge.conf"
expected_bypass='bypass-dns = kuaishou.com, *.kuaishou.com, *.corp.kuaishou.com, *.gifshow.com, *.kuaishoupay.com, *.kwimgs.com, *.ssrcdn.com, *.kwaitalk.com'
if ! grep -Fqx "$expected_bypass" "$surge_profile"; then
  echo "FAIL $surge_profile missing company bypass-dns configuration" >&2
  failed=1
fi

for host in \
  'corp.kuaishou.com = server:syslib' \
  '*.corp.kuaishou.com = server:syslib' \
  'kuaishou.com = server:syslib' \
  '*.kuaishou.com = server:syslib' \
  '*.gifshow.com = server:syslib' \
  '*.kwimgs.com = server:syslib' \
  '*.ssrcdn.com = server:syslib' \
  '*.kwaitalk.com = server:syslib' \
  '*.kuaishoupay.com = server:syslib'; do
  if ! grep -Fqx "$host" "$surge_profile"; then
    echo "FAIL $surge_profile missing system-DNS host mapping: $host" >&2
    failed=1
  fi
done

# Inline work rules are required before the first remote RULE-SET so a failed or
# conflicting provider cannot send intranet traffic to FINAL/Fallback.
for profile in "$repo_dir/surge.conf" "$repo_dir/shadowrocket.conf"; do
  first_remote_line=$(grep -n '^RULE-SET,https://' "$profile" | head -1 | cut -d: -f1)
  for rule in \
    'DOMAIN,adlp.corp.kuaishou.com,REJECT' \
    'DOMAIN,kepm.corp.kuaishou.com,REJECT' \
    'DOMAIN-SUFFIX,corp.kuaishou.com,DIRECT' \
    'DOMAIN-SUFFIX,kuaishou.com,DIRECT' \
    'DOMAIN-SUFFIX,gifshow.com,DIRECT' \
    'DOMAIN-SUFFIX,kuaishoupay.com,DIRECT' \
    'DOMAIN-SUFFIX,kwimgs.com,DIRECT' \
    'DOMAIN-SUFFIX,ssrcdn.com,DIRECT' \
    'DOMAIN-SUFFIX,kwaitalk.com,DIRECT'; do
    rule_line=$(grep -nF "$rule" "$profile" | head -1 | cut -d: -f1)
    if [[ -z "$rule_line" || -z "$first_remote_line" || "$rule_line" -ge "$first_remote_line" ]]; then
      echo "FAIL $profile company rule is missing or follows a remote RULE-SET: $rule" >&2
      failed=1
    fi
  done

  adlp_line=$(grep -nF 'DOMAIN,adlp.corp.kuaishou.com,REJECT' "$profile" | head -1 | cut -d: -f1)
  kepm_line=$(grep -nF 'DOMAIN,kepm.corp.kuaishou.com,REJECT' "$profile" | head -1 | cut -d: -f1)
  corp_line=$(grep -nF 'DOMAIN-SUFFIX,corp.kuaishou.com,DIRECT' "$profile" | head -1 | cut -d: -f1)
  if [[ -z "$adlp_line" || -z "$kepm_line" || -z "$corp_line" || "$adlp_line" -ge "$corp_line" || "$kepm_line" -ge "$corp_line" ]]; then
    echo "FAIL $profile explicit company rejects must precede corp DIRECT" >&2
    failed=1
  fi
done

exit "$failed"
