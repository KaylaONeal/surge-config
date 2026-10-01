# CF Auto native Surge selection — 2026-10-01

The user requires native Surge behavior on Mac and iPhone, without an external
client or platform adapter. `CF Edge Auto` therefore keeps Trojan over verified
TLS/WebSocket and changes its group from `url-test` to `smart`. It can score real
connections and retry another CF member; this change does not enable XHTTP/H3.

## Scope

- The same seven CF leaves retain their server, SNI, Host, path, authentication
  and `udp-relay=false` settings.
- Relative to `ff7547b`, exactly one functional template line changes:
  `CF Edge Auto`. All rules, other groups and node definitions are identical.
- The active local profile is backed up before reload; its only changed line is
  also `CF Edge Auto`.
- Shadowrocket retains its original profile. The Surge managed profile is shared
  by Mac and iOS; Smart requires Mac 5.7.0+/iOS 5.11.0+ with Smart unlocked.
- No Workers code, account, Pages deployment, KV, origin or paid plan is changed.
  Account exhaustion still stops this dedicated CF service without a business
  account fallback.

## Tradeoffs

Smart has a fixed five-minute health-test schedule, so the ineffective
`interval=7200` and `tolerance` options are removed from this group.
`evaluate-before-use=false` remains. Seven members on 288 daily rounds imply
approximately 2,016 scheduled requests per continuously testing device per day;
this is a planning estimate, excludes other traffic/retests, and is not a quota
guarantee. Region pools retain their existing two-hour tests.

Smart can choose different members for different destinations. It does not pin
the CF exit country or transparently migrate an established TCP session. The
installed Mac 5.7.6 supports basic Smart; newer three-second silent-failure
handling is not claimed. Fixed AI/download/exchange exits and DIRECT behavior
remain outside this change.

## Validation

- Local routing references, cycles, policy boundaries and 84 Surge / 81
  Shadowrocket route cases pass; all 38 local/upstream checks pass.
- Both credential-bearing profiles render successfully into ignored `build/`.
- Scope comparisons confirm only the CF group changes in the template and local
  active file, with zero functional changes to Shadowrocket.
- Local reload succeeds. The effective profile contains `CF Edge Auto = smart`
  with all seven CF members and no CF external-program policy. There is no
  remembered manual CF override; `Proxy` still uses CF Auto and `AI` uses US Only.
- At 15:41 CST, basic HTTPS trace requests through CF Auto, CT 01, CU 01 and CM
  01 return HTTP 200. CF Auto exits through the CF path; the AI probe still sees
  the fixed US exit. Request records complete without failures.
- No throughput benchmark, peak-hour test or deliberate outage is performed.
  These checks establish configuration scope and current basic connectivity,
  not a measured peak-hour speed improvement. iPhone runtime remains unobserved.

## Publication

Configuration revision: `22eabbeef15fdd3edfb33e2c5c7aa56c0d220fa1`, pushed to
`main`; [CI run 36832168275](https://github.com/KaylaONeal/surge-config/actions/runs/36832168275)
passes. From the registered US server at 15:54 CST, both protected hosted
profiles return HTTP 200 and their SHA-256 values match the committed templates
rendered with the private local credentials. Hosted Surge contains the Smart CF
group; hosted Shadowrocket remains unchanged. No protected URL, credentials or
downloaded profile text is recorded here.

Local subscription download verification encountered HTTP 403 on the ordinary
route and a proxy HTTP 503 for the Surge file on the explicit native route;
Shadowrocket succeeded on the latter. The independent US download establishes
publication, but does not establish that every client can fetch its subscription
from every network. No unrelated subscription-access routing is changed.

References: [Surge Smart group](https://manual.nssurge.com/policy-groups/smart.html),
[Surge Trojan transport](https://manual.nssurge.com/policies/trojan.html).
