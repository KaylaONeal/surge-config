#!/usr/bin/env bash
# Verifies every RULE-SET URL referenced by the configs still resolves (HTTP 200).
# Upstream repos rename/remove lists occasionally; a dead RULE-SET silently
# drops all its rules, which is how "AI leaks to a KR node" happens.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
urls=$(grep -ho 'https://[^,]*\.\(list\|txt\)' surge.conf shadowrocket.conf | sort -u)

for u in $urls; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 25 --retry 2 "$u")
  if [ "$code" = "200" ]; then
    printf 'OK   %s\n' "$u"
  else
    printf 'FAIL %s (HTTP %s)\n' "$u" "$code"
    fail=1
  fi
done

exit $fail
