#!/usr/bin/env bash
set -uo pipefail

repo_dir=$(cd "$(dirname "$0")/.." && pwd)
repo_raw_prefix=https://raw.githubusercontent.com/KaylaONeal/surge-config/main/
failed=0

python3 "$repo_dir/scripts/check-routing.py" || failed=1

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

  # Only fetch the first byte. Some upstream rule sets are several megabytes;
  # downloading every file made this reachability check slow and flaky.
  status=$(curl -sS -o /dev/null -w '%{http_code}' --range 0-0 --max-time 25 --retry 2 "$url")
  if [[ "$status" == 200 || "$status" == 206 ]]; then
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

  if ! grep -Fqx 'FINAL,DIRECT' "$profile" || grep -Eq '^FINAL,(Fallback|Proxy|CF Edge Auto)$' "$profile"; then
    echo "FAIL $profile must hard-route unknown traffic to DIRECT" >&2
    failed=1
  fi

  if grep -Eq '^(Domestic|Fallback) = ' "$profile" || grep -Eq '^GEOIP,CN,' "$profile"; then
    echo "FAIL $profile domestic/unknown traffic must not use a remembered group or GEOIP lookup" >&2
    failed=1
  fi

  if grep -E '^AI = ' "$profile" | grep -Eq '(DIRECT|CF Edge Auto|JP Auto|KR Auto)'; then
    echo "FAIL $profile AI policy contains a non-US/direct option" >&2
    failed=1
  fi

  # AI traffic must always leave from us1, 35.212.192.172, so an AI service
  # never sees the exit IP move. Only three transports land there:
  #   US HTTPS 01  -> us1:443/tcp   (gost)
  #   US HY2 02    -> us1:4444/udp  (hysteria, direct)
  #   US HY2 01    -> 139.196.52.175:36000/udp, DNAT'd to us1:4444
  # US TUIC 01 and US HY2 Relay 01 both land on 192.3.243.194 instead, and
  # US Auto / Fastest mix the two exits, so none of them may appear here.
  for group in 'US Only' 'AI'; do
    line=$(grep -E "^${group} = " "$profile")
    if [[ -z "$line" ]]; then
      echo "FAIL $profile missing the ${group} policy group" >&2
      failed=1
      continue
    fi
    if grep -Eq '(US TUIC 01|US HY2 Relay 01|US Auto|Fastest)' <<<"$line"; then
      echo "FAIL $profile ${group} contains a member that does not exit from us1" >&2
      failed=1
    fi
  done

  # port-hopping needs a server-side redirect covering the range. us1 has none,
  # so the parameter would silently break the only direct QUIC path to it.
  if grep -E '^US HY2 02 = ' "$profile" | grep -q 'port-hopping'; then
    echo "FAIL $profile US HY2 02 uses port-hopping, which us1 does not redirect" >&2
    failed=1
  fi
done

surge_domestic_set='DOMAIN-SET,https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/ChinaMax/ChinaMax_Domain.list,DIRECT'
surge_overseas_set='DOMAIN-SET,https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Global/Global_Domain.list,CF Edge Auto'
shadowrocket_domestic_set='RULE-SET,https://raw.githubusercontent.com/Loyalsoldier/surge-rules/release/ruleset/direct.txt,DIRECT'
shadowrocket_overseas_set='RULE-SET,https://raw.githubusercontent.com/Loyalsoldier/surge-rules/release/ruleset/proxy.txt,CF Edge Auto'
if ! grep -Fqx "$surge_domestic_set" "$repo_dir/surge.conf"; then
  echo "FAIL surge.conf must use the full ChinaMax domain set as DIRECT" >&2
  failed=1
fi
if ! grep -Fqx "$surge_overseas_set" "$repo_dir/surge.conf"; then
  echo "FAIL surge.conf must use the full Global domain set through CF Edge" >&2
  failed=1
fi
if ! grep -Fqx "$shadowrocket_domestic_set" "$repo_dir/shadowrocket.conf"; then
  echo "FAIL shadowrocket.conf must use Loyalsoldier direct rules" >&2
  failed=1
fi
if ! grep -Fqx "$shadowrocket_overseas_set" "$repo_dir/shadowrocket.conf"; then
  echo "FAIL shadowrocket.conf must use Loyalsoldier proxy rules through CF Edge" >&2
  failed=1
fi

for profile in "$repo_dir/surge.conf" "$repo_dir/shadowrocket.conf"; do
  proxy_extra='RULE-SET,https://raw.githubusercontent.com/KaylaONeal/surge-config/main/rules/proxy-extra.list,CF Edge Auto'
  proxy_extra_line=$(grep -nF "$proxy_extra" "$profile" | head -1 | cut -d: -f1)
  first_broad_direct_line=$(grep -nE 'ChinaMax/ChinaMax_Domain\.list,DIRECT|Loyalsoldier/surge-rules/release/ruleset/direct\.txt,DIRECT' "$profile" | head -1 | cut -d: -f1)
  first_broad_proxy_line=$(grep -nE 'Global/Global_Domain\.list,CF Edge Auto|Loyalsoldier/surge-rules/release/ruleset/proxy\.txt,CF Edge Auto' "$profile" | head -1 | cut -d: -f1)
  core_ai_line=$(grep -nF 'DOMAIN-SUFFIX,openai.com,AI' "$profile" | head -1 | cut -d: -f1)
  core_cf_line=$(grep -nF 'DOMAIN-SUFFIX,google.com,CF Edge Auto' "$profile" | head -1 | cut -d: -f1)
  if [[ -z "$proxy_extra_line" || -z "$first_broad_direct_line" || -z "$first_broad_proxy_line" ||
        -z "$core_ai_line" || -z "$core_cf_line" ||
        "$core_ai_line" -ge "$first_broad_direct_line" ||
        "$core_cf_line" -ge "$first_broad_direct_line" ||
        "$proxy_extra_line" -ge "$first_broad_direct_line" ||
        "$first_broad_direct_line" -ge "$first_broad_proxy_line" ]]; then
    echo "FAIL $profile policy priority must be core AI/CF, proxy-extra, domestic, overseas" >&2
    failed=1
  fi
done

# Avoid loading two almost-identical 100k/30k rule sets in the same client.
if grep -Fq 'Loyalsoldier/surge-rules/release/ruleset/direct.txt' "$repo_dir/surge.conf" ||
   grep -Fq 'Loyalsoldier/surge-rules/release/ruleset/proxy.txt' "$repo_dir/surge.conf"; then
  echo "FAIL surge.conf must not duplicate Blackmatrix broad sets with Loyalsoldier" >&2
  failed=1
fi
if grep -Fq 'ChinaMax/ChinaMax_Domain.list' "$repo_dir/shadowrocket.conf" ||
   grep -Fq 'Global/Global_Domain.list' "$repo_dir/shadowrocket.conf"; then
  echo "FAIL shadowrocket.conf must not duplicate Loyalsoldier broad sets with Blackmatrix" >&2
  failed=1
fi

# Common overseas services must use CF Edge directly. A select group can retain
# an old JP/US choice across profile reloads, defeating the desired routing.
for profile in "$repo_dir/surge.conf" "$repo_dir/shadowrocket.conf"; do
  for service in Telegram Twitter Google Global; do
    expected="RULE-SET,https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/$service/$service.list,CF Edge Auto"
    if ! grep -Fqx "$expected" "$profile"; then
      echo "FAIL $profile must route $service through CF Edge Auto" >&2
      failed=1
    fi
  done

  for domain in google.com googleapis.com gstatic.com telegram.org t.me x.com twitter.com twimg.com; do
    if ! grep -Fqx "DOMAIN-SUFFIX,$domain,CF Edge Auto" "$profile"; then
      echo "FAIL $profile missing inline CF Edge rule for $domain" >&2
      failed=1
    fi
  done
done


# Domestic fast path: core CN domains must match by domain before any overseas
# rule set, otherwise they only match through GEOIP,CN and pay a DNS round trip.
for profile in "$repo_dir/surge.conf" "$repo_dir/shadowrocket.conf"; do
  first_overseas_line=$(grep -n 'Surge/Gemini/Gemini.list\|Surge/Telegram/Telegram.list' "$profile" | head -1 | cut -d: -f1)
  for domain in \
    qq.com weixin.qq.com wechat.com taobao.com tmall.com goofish.com \
    alipay.com jd.com meituan.com douyin.com bilibili.com xiaohongshu.com \
    pinduoduo.com weibo.com baidu.com; do
    rule_line=$(grep -n "^DOMAIN-SUFFIX,${domain//./\\.},DIRECT$" "$profile" | head -1 | cut -d: -f1)
    if [[ -z "$rule_line" || -z "$first_overseas_line" || "$rule_line" -ge "$first_overseas_line" ]]; then
      echo "FAIL $profile missing domestic fast-path rule before overseas sets: $domain" >&2
      failed=1
    fi
  done
done

# Dedicated domestic lists must be direct and precede the first overseas set.
for profile in "$repo_dir/surge.conf" "$repo_dir/shadowrocket.conf"; do
  first_overseas_line=$(grep -n 'Surge/Telegram/Telegram.list' "$profile" | head -1 | cut -d: -f1)
  for service in WeChat DiDi; do
    rule="RULE-SET,https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/$service/$service.list,DIRECT"
    rule_line=$(grep -nF "$rule" "$profile" | head -1 | cut -d: -f1)
    if [[ -z "$rule_line" || -z "$first_overseas_line" || "$rule_line" -ge "$first_overseas_line" ]]; then
      echo "FAIL $profile $service DIRECT rule missing or follows overseas rules" >&2
      failed=1
    fi
  done
done

# Encrypted DNS answers NXDOMAIN for company intranet names.
if grep -Eq '^encrypted-dns-server[[:space:]]*=' "$repo_dir/shadowrocket.conf"; then
  echo "FAIL shadowrocket.conf encrypted DNS can break company DNS" >&2
  failed=1
fi

for profile in "$repo_dir/surge.conf" "$repo_dir/shadowrocket.conf"; do
  if ! grep -Fq 'corp.kuaishou.com = server:syslib' "$profile"; then
    echo "FAIL $profile missing system-DNS host mapping for company domains" >&2
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
  'gifshow.com = server:syslib' \
  '*.gifshow.com = server:syslib' \
  'kwimgs.com = server:syslib' \
  '*.kwimgs.com = server:syslib' \
  'ssrcdn.com = server:syslib' \
  '*.ssrcdn.com = server:syslib' \
  'kwaitalk.com = server:syslib' \
  '*.kwaitalk.com = server:syslib' \
  'kuaishoupay.com = server:syslib' \
  '*.kuaishoupay.com = server:syslib'; do
  if ! grep -Fqx "$host" "$surge_profile"; then
    echo "FAIL $surge_profile missing system-DNS host mapping: $host" >&2
    failed=1
  fi
done

if grep -Eq '^(encrypted-dns-server|encrypted-dns-follow-outbound-mode|hijack-dns)[[:space:]]*=' "$surge_profile"; then
  echo "FAIL $surge_profile public/encrypted DNS interception can break company DNS" >&2
  failed=1
fi

if grep -Eq '^DOMAIN-SUFFIX,(corp\.)?kuaishou\.com$|^DOMAIN-SUFFIX,kuaishoupay\.com$' "$repo_dir/rules/direct-extra.list"; then
  echo "FAIL direct-extra.list must not duplicate inline company rules" >&2
  failed=1
fi

worker_source="$repo_dir/cloudflare/config-service/src/worker.js"
if grep -Fq 'cacheEverything: true' "$worker_source" || ! grep -Fq 'cache: "no-store"' "$worker_source"; then
  echo "FAIL config service template fetch must bypass stale edge caches" >&2
  failed=1
fi

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

# IBKR public domains in upstream Global.list would use Proxy/JP, while TWS
# overseas gateways (*.ibllc.com) are absent upstream and fall through to
# DIRECT. Keep both on CF Edge, but leave the mainland gateway direct.
for profile in "$repo_dir/surge.conf" "$repo_dir/shadowrocket.conf"; do
  ibkr_rule='RULE-SET,https://raw.githubusercontent.com/KaylaONeal/surge-config/main/rules/ibkr.list,CF Edge Auto'
  ibkr_line=$(grep -nF "$ibkr_rule" "$profile" | head -1 | cut -d: -f1)
  global_line=$(grep -n 'ios_rule_script/master/rule/Surge/Global/Global.list,CF Edge Auto' "$profile" | head -1 | cut -d: -f1)
  mainland_line=$(grep -nF 'DOMAIN-SUFFIX,ibllc.com.cn,DIRECT' "$profile" | head -1 | cut -d: -f1)

  if [[ -z "$ibkr_line" || -z "$global_line" || "$ibkr_line" -ge "$global_line" ]]; then
    echo "FAIL $profile IBKR CF Edge rule missing or follows Global.list" >&2
    failed=1
  fi
  if [[ -z "$mainland_line" || -z "$ibkr_line" || "$mainland_line" -ge "$ibkr_line" ]]; then
    echo "FAIL $profile IBKR mainland DIRECT rule must precede CF Edge rule" >&2
    failed=1
  fi
done

for required_ibkr_rule in \
  'DOMAIN-SUFFIX,ibllc.com' \
  'DOMAIN-SUFFIX,ibkr.com' \
  'DOMAIN-SUFFIX,interactivebrokers.com'; do
  if ! grep -Fxq "$required_ibkr_rule" "$repo_dir/rules/ibkr.list"; then
    echo "FAIL rules/ibkr.list missing $required_ibkr_rule" >&2
    failed=1
  fi
done

if grep -Fqx 'DOMAIN-SUFFIX,ibllc.com.cn' "$repo_dir/rules/ibkr.list"; then
  echo "FAIL rules/ibkr.list must not proxy mainland trading gateway" >&2
  failed=1
fi

exit "$failed"
