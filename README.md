# surge-config

Git-managed Surge configuration shared by iOS and macOS. Real node topology is
tracked; passwords and other authentication material are not.

## Routing policy

The templates reserve us1 for Claude online services. All other fixed-US
traffic uses `UX Only`, whose members must exit at `192.3.243.194`.
`ux.fallback.page`, `hy.fallback.page` and `ux1.fallback.page` name entrances
to that same server; a hostname alone does not prove a working protocol or
actual exit. Verify each selected transport before applying it.

The selected transport is `UX HY2 Direct`: `192.3.243.194:5000/udp` with
SNI `hy.fallback.page`. On 2026-11-02 UTC, mini's policy-specific probes
observed `192.3.243.194` / US; Google returned 204 and the ChatGPT robots and
IBKR public pages returned 200. These checks do not verify logged-in sessions.
The server's failed default WARP route remains in place for other consumers;
only the Hysteria service's UID uses the native route, covering both data and
DNS. Other UX protocols were not validated. Repair details and the backup
path are registered in `infra show ux-node`.

| Traffic | Policy | Default exit |
|---|---|---|
| Claude online services and API | `Claude` → `US Only` | `35.212.192.172` (us1) |
| ChatGPT / OpenAI, Google AI and other AI services | `AI` → `UX Only` | `192.3.243.194` |
| Google services | `UX Only` | `192.3.243.194` |
| Codex / Claude installers, npm and GitHub release assets | `Download` | `UX Only` first; `CF Edge Auto` selectable |
| YouTube web, API, video and thumbnails | `YouTube` → `CF Edge Auto` | CF pool only; no UX/us1 candidate |
| Named self-hosted services; Mac Cloudflare Tunnel connectors | `UX Only` | Native UX transport; no CF relay dependency |
| Bybit login, API, WebSocket and assets | `Bybit` | `KR HTTPS 01`; no cross-country fallback |
| Binance web, API, WebSocket and assets | `Binance` | `KR HTTPS 01`; no cross-country fallback |
| Telegram, X, Backpack and other common overseas services | `CF Edge Auto` | Best available CF ingress; egress can change |
| Polymarket web / CLOB / Gamma / Perps | `CF HKG Auto` | Explicit measured-HK proxyIP pool |
| Futu / moomoo domains and macOS Futu OpenD | `Futu`: `CF Edge Auto` → `DIRECT` | CF preferred; direct on failed CF health checks |
| IBKR overseas sites and trading gateways | `UX Only` in both profiles | `192.3.243.194`; no us1 fallback |
| IBKR mainland trading gateway (`*.ibllc.com.cn`) | `DIRECT` | DIRECT |
| Domestic services | literal `DIRECT` rules | DIRECT |
| Ads | `AdBlock` | REJECT, switchable to DIRECT |
| Everything unmatched | literal `FINAL,DIRECT` | DIRECT |

Precise installer rules run before the Claude and other AI rules. Claude's
seven first-party suffixes run before the mixed `ai-extra.list`: `anthropic.com`,
`claude.ai`, `claude.com`, `claudeusercontent.com`, `claude.site`,
`claudemcpclient.com` and `claudemcpcontent.com`. Shared third-party domains
are not added to the us1 allowlist. Google AI rules retain priority over broad
Google, Microsoft and Global sets. Inline entries remain usable if remote
rule lists cannot refresh.

## Separate fixed exits and the us1 budget

`Claude = select, US Only` is the only rule-facing path to us1. The us1 pool
retains its three transports:

| Member | Path to us1 | Transport |
|---|---|---|
| `US HY2 02` | direct to `us1:4444` | QUIC |
| `US HY2 01` | `139.196.52.175:36000`, DNAT'd to `us1:4444` | QUIC |
| `US HTTPS 01` | direct to `us1:443` | TCP |

Surge uses `smart` and Shadowrocket uses `url-test` within that pool.
`AI = select, UX Only` keeps other AI services on the UX exit. `Download`,
`YouTube`, `Proxy`, `Fastest` and other general groups must have no direct or
nested us1 member. Merely changing their first/default member would leave
manual selections and automatic failover able to consume us1 traffic.
The routing checks enforce both recursive group isolation and the exact
Claude rule allowlist. IBKR is deliberately included in the UX migration;
it is not an exception to Claude-only us1 routing.

This reduces usage of the monthly 200 GB us1 allowance but is not a hard
quota. Claude attachments, proxy health checks, other clients and services on
the server can still consume traffic. A hard limit requires the provider's
billing period and traffic-counting rules, server-wide accounting and an
explicit cutoff policy. No monthly cutoff or new monitoring service is
installed by this routing change.

Keep Surge in rule mode. The 2026-11-01 audit found global proxy mode
selecting `US HTTPS 02`, which sent unrelated traffic to us1 despite the rules; it was
returned to rule mode. Check remembered group selections after reload and
reconnect existing sessions as needed: changing rules does not move an
already established connection. Live egress and service checks are required
before calling a new profile deployed.

## Antigravity / Gemini CLI routing

`agy` uses `daily-cloudcode-pa.googleapis.com`; Gemini CLI and other builds
also use `cloudcode-pa.googleapis.com` and the explicit sandbox endpoints in
`rules/google-ai.list`. Both profiles pin these to `AI` → `UX Only` before
the broad `googleapis.com` rule. Antigravity product and feature-control
domains (`antigravity.google`, `antigravity.goog`, `antigravity-unleash.goog`)
use the same fixed UX exit. They have no CF or us1 fallback.

Historical evidence from September 17: `agy -p 'hello'` failed with
`FAILED_PRECONDITION` while its inference request used the broad Google rule.
`CF Edge Auto` measured `104.28.163.84` / HK despite the selected node's US
label; the then-current `AI` policy measured us1 `35.212.192.172` / US.
Those measurements explain why a stable exit matters; they do not verify the
new UX path. Use policy-specific probes and actual agy request logs.

## Futu routing

`Futu = fallback, CF Edge Auto, DIRECT` keeps CF first even if DIRECT is faster.
It refreshes stale availability results on use (two-hour interval); Surge
uses cached results while testing in the background. Recovery makes CF preferred again. This is
health-check failover, not a retry of an individual failed trade/API request:
a Futu rejection or timeout with otherwise healthy CF may not switch routes.
See Surge's [fallback semantics](https://manual.nssurge.com/policy-groups/fallback.html)
and [nested-group testing](https://manual.nssurge.com/policy-groups/overview.html).

Surge Mac matches the exact executable
`/Applications/Futu_OpenD.app/Contents/MacOS/Futu_OpenD`, including public
literal-IP connections on ports such as 443 and 9595. Enhanced Mode must be
on to capture connections that do not use the system HTTP proxy. LAN rules
remain earlier, so local OpenD clients keep connecting directly. Existing TCP
sessions keep their route until the application reconnects.

Both profiles contain inline Futu/moomoo domain rules before the domestic
fast path, sourced from the [broker-rules Futu list](https://github.com/forecho/broker-rules/blob/main/Source/broker/futu.conf)
(snapshot 2026-10-08, redundant subdomains removed). These cover `futunn.com`,
`fututrade.com`, `futufin.com`, `futuhk.com`, `futustatic.com`, `moomoo.com`
and the related first-party domains. After a phone still reported a mainland
connection, the 2026-10-08 supplement adds nine domain rules (including
`futuapi.com`, `futuin.com`, `qtlcdn.com` and specific shared SDK hosts), plus
63 Futu-labelled IP rules from [HK_Broker.list](https://github.com/LingJingMaster/Shadowrocket-Rules/blob/main/HK_Broker.list).
Shared SDK names are taken from [broker-rules _shared.conf](https://github.com/forecho/broker-rules/blob/main/Source/broker/_shared.conf).
Two additional exact hosts, `43.163.63.148/32` and `47.254.236.220/32`, were
observed receiving OpenD traffic locally. No whole cloud ASN or shared vendor
root domain is added. Listed cloud subnets can still contain other tenants;
the rules apply to any app connecting to those IPs.

The IP rules use `no-resolve` and precede `GEOIP,CN,DIRECT,no-resolve`, covering
phone connections with no domain or process identity. The [upstream traffic
audit](https://github.com/masnmarc/broker-rules/pull/1) describes Futu choosing
uncovered access-point IPs after latency probes. Endpoints rotate, so this is
a dated coverage improvement, not a guarantee that all future IPs are covered.
All additions use the existing `Futu` group: CF first, DIRECT on failed health
checks. This preserves the requested fallback, which can still produce a
mainland exit; changing that behavior is a separate policy choice.

The Futu rules leave the shared CF pool, exchange policies and
`FINAL,DIRECT` unchanged. Public HTTP probes and proxy connection logs do not validate an
authenticated order; no test order is submitted as part of routing validation.

Validation on 2026-10-08: local routing checks passed for both profiles; Mac
OpenD logs showed `Futu -> CF Edge Auto`. Futu homepage, OpenAPI and
`fututrade.com` public probes returned HTTP 200 through CF (observed SG exit).
An isolated unavailable-proxy Smart group inside an equivalent fallback group
selected DIRECT and returned HTTP 200 with the direct exit; temporary test
groups were removed afterward. The mobile supplement passed 141 Surge / 138
Shadowrocket route cases plus IP subnet-boundary checks. A literal-IP CONNECT
probe without OpenD process identity matched `124.156.234.0/24` and used
`Futu -> CF Edge Auto`. Phone trading after this supplement remains unverified.

## Installation downloads and Muse

`Download = select, UX Only, CF Edge Auto` excludes every us1 transport.
Exact inline host rules precede broad Claude, AI, Google and GitHub rules:
`persistent.oaistatic.com`, `releases.openai.com`, `downloads.claude.ai`,
`herdr.dev`, `registry.npmjs.org`, `release-assets.githubusercontent.com`,
`objects.githubusercontent.com` and `github-releases.githubusercontent.com`.
Thus Claude's installer uses the download policy while its API and online
services use `Claude`. Other AI account/API traffic uses `AI` → `UX Only`.
Shared cloud/CDN suffixes are not treated as download-only services;
`storage.googleapis.com` follows the Google route to UX.

The [September 22 measurements and review](docs/reviews/2026-09-22-routing-review.md)
describe the former us1 download setup. That selection is superseded by the
200 GB budget requirement. Short Range samples never established sustained
whole-download bandwidth. Recent large Git transfers have also exposed CF
stream failures, so UX is the default and CF remains a manual alternative.

Muse's first-party domains use the inline `DOMAIN-SUFFIX,muse.ai,AI` rule,
also maintained in `rules/ai-extra.list`. The observed sign-in chain redirects
through `auth.muse.ai`, `www.facebook.com`, `www.instagram.com` and
`auth.meta.com`, so those exact Meta hosts also use `AI` to retain the same
exit throughout sign-in. This affects other requests to these three Meta hosts
too; their entire domain/CDN suffixes are not overridden. The public redirect
chain finishes at the Muse landing page (HTTP 200); authenticated account
access is a separate check.

Unknown domains continue to use `FINAL,DIRECT`, as explicitly retained on
September 22. New services still need a maintained domain override.

## Historical us1 chaining measurements

Before the Claude/UX split, routing the US-pinned AI exit through the
Cloudflare EdgeTunnel ingress was tested as an alternative to the direct
mainland-to-US leg. It was **measured to be slower**. No such chain is
configured. Time to a completed `CONNECT` through the us1 HTTPS proxy from a
mainland home line, bypassing the local Surge tunnel (2026-09-06, 6 samples):

| Path | median | min |
|---|---:|---:|
| direct to `us1:443` | 0.68 s | 0.67 s |
| chained via CF `188.164.248.21` (SEA colo) | 1.01 s | 0.99 s |
| chained via CF `104.17.107.60` (HKG colo) | 3.23 s | 1.39 s |

Those September 6 probes measured ingress colos, not final exit countries.
The September 11 per-policy exit measurements are recorded in
[private/nodes.md](private/nodes.md): Direct/CM then exited in Singapore,
CT/CU in the US. Anycast placement and Worker exits can change over time.

For a connection that already crossed the Pacific to reach a US colo, chaining
adds no shortcut: us1 measures 6 ms to those colos, so the CF-to-us1 leg is
free, but the WebSocket handshake and the inner TLS handshake each cost another
full mainland-to-US round trip. The one Asian entry (HKG) has a fast TCP
handshake at 58-177 ms but is badly congested afterwards, with inner-TLS times
scattered between 0.5 s and 4.9 s.

Chaining would only pay off with an ingress address that reliably lands on an
Asian colo *and* stays stable under load. Re-measure before revisiting this.

## Domestic traffic and DNS

Upstream `ChinaMax.list` now ships almost no domain rules (51 TLD suffixes, 13
keywords, 8k `no-resolve` IP ranges), so domestic domains used to reach
`DIRECT` only through `GEOIP,CN`. GEOIP forces a DNS resolution before Surge can
choose a policy, which is what made domestic sites feel slow. Three safeguards
fix that:

- an inline `DIRECT` fast path for the common CN services (WeChat/QQ, Taobao,
  Tmall, Xianyu, Alipay, JD, Pinduoduo, Meituan, Douyin, Bilibili, Xiaohongshu,
  Weibo, Zhihu, Baidu, NetEase, carriers) evaluated before every overseas set;
- dedicated WeChat and DiDi rule sets plus Blackmatrix `ChinaMax_Domain.list`
  (Surge) and Loyalsoldier `direct.txt` (Shadowrocket), evaluated before broad
  overseas sets;
- literal `DIRECT` for domestic IP ranges and `FINAL`, so remembered policy-group
  selections can never send domestic or unknown traffic through a proxy.

Ad rule sets still run before the fast path, so ad and tracking subdomains of
those services stay rejected.

Company intranet names must resolve through the system resolver. Public DNS
answers `NXDOMAIN` for them, which is why they fail to open. Both profiles keep
the company domains in `bypass-dns` plus `[Host] ... = server:syslib`, and
neither profile may enable encrypted DNS. Add new company suffixes to all three
places at once.

## Probe frequency and cached configuration

Both profiles use a 7200-second (2-hour) interval for `url-test` groups and
the Futu fallback group. On 2026-10-12, Surge CF Edge Auto changed from Smart
to native url-test: Smart ignores interval and always tests every five minutes.
For seven leaves, baseline scheduled CF tests fall from 2,016 to 84 per day per
client (24 times fewer), excluding failures, network changes and manual tests.
The Claude-only `US Only` Smart group retains its existing test behavior.
CF leaves explicitly use
`test-url=http://www.gstatic.com/generate_204`: the pinned Worker synthesizes
204 responses for `cp.cloudflare.com`, so that address cannot validate external
forwarding. Shadowrocket uses its existing group-level gstatic test URL.
Surge keeps the previous selection while refreshing expired results in the
background, and `evaluate-before-use=false` avoids blocking first use on a
successful probe (first use without a result uses the first member). Network
changes and connection failures can trigger earlier tests; 2 hours is not a
hard retry limit. Shadowrocket's failure behavior remains client-controlled.

The Surge managed profile still updates daily with `strict=false`, so a failed
subscription update permits use of the last downloaded local profile. This
does not make an unavailable proxy work, and there is no claim that all-failed
node tests preserve the last successful selection indefinitely.

The [September 30 quota investigation](docs/reviews/2026-09-30-cloudflare-quota.md)
found EdgeTunnel traffic, rather than profile downloads, dominated Workers
requests. Less frequent testing reduces probe overhead but does not cap actual
proxy connections or prevent account quota exhaustion. In particular, profile
and test caches cannot restore a TCP stream terminated by a per-request CPU
limit. Live quotes and order responses are never replaced with cached data.
The [October 12 investigation and mitigation](docs/reviews/2026-10-12-futu-quote-disconnections.md)
separates probe overhead from Worker CPU failures.

## Upstream rule synchronization

The profiles reference live upstream URLs instead of checked-in snapshots:

- Surge uses Blackmatrix `ChinaMax_Domain.list` for domestic domains and
  `Global_Domain.list` plus `Global.list` for overseas domains, keywords and IPs.
- Shadowrocket uses Loyalsoldier `direct.txt` and `proxy.txt` for broad domain
  coverage, plus Blackmatrix service-specific lists.

Blackmatrix and Loyalsoldier overlap by roughly 96-98%, so loading both complete
sets in one client would add more than 130,000 duplicate rules. Splitting the
sources by client keeps future upstream additions automatic without that cost.
Rule updates take effect when Surge or Shadowrocket refreshes its remote
resources; no repository commit is needed for upstream-only changes.

For personal overrides, add domains to `rules/proxy-extra.list`. It is evaluated
before the broad domestic lists and routes matches to `CF Edge Auto`. Keep
US-pinned AI domains in `rules/ai-extra.list` and forced-direct exceptions in
`rules/direct-extra.list`.

## Repository layout

| Path | Purpose | Tracked |
|---|---|---|
| `surge.conf` | Shared Surge profile template for iOS and macOS | Yes |
| `shadowrocket.conf` | Shadowrocket profile template | Yes |
| `private/nodes.md` | Real protocol/server/port/SNI inventory | Yes |
| `private/secrets.example.env` | Empty authentication-variable template | Yes |
| `~/.config/surge-config/credentials.env` | Local passwords and authentication IDs | Outside repository |
| `rules/*.list` | Shared AI, Google AI, direct, reject and macOS process rules | Yes |
| `build/*.conf` | Rendered usable profiles containing credentials | **No** |

The raw phone export is intentionally ignored because it contains proxy
credentials, API access tokens and a complete MITM CA private key.

## Authentication boundary

These values are treated as secrets and never committed:

- proxy passwords and usernames;
- TUIC UUIDs and other authentication identifiers;
- Surge HTTP API and external-controller tokens;
- MITM/keystore private keys and their passphrases.
- protected rendered-profile URLs when they contain an access token.

The committed profiles use placeholders such as `__HTTPS_PASSWORD__`. They are
not directly usable by Surge until rendered.

Create the local credential directory and render:

```bash
mkdir -p ~/.config/surge-config
chmod 700 ~/.config/surge-config
cp private/secrets.example.env ~/.config/surge-config/credentials.env
chmod 600 ~/.config/surge-config/credentials.env
$EDITOR ~/.config/surge-config/credentials.env
./scripts/render-config.sh
```

Usable profiles are written to `build/` with mode `0600`.

## Remote loading limitation

Surge managed profiles are downloaded as final configuration text. Surge does
not substitute local environment variables into a remote profile, so a Git
file that excludes passwords cannot simultaneously be a directly usable full
profile.

There are two safe deployment choices:

1. Render locally and import `build/surge.conf`; all remote `RULE-SET` files
   continue updating independently.
2. Render in a protected deployment service and serve the result from an
   authenticated URL. The generated result must not be committed back to Git.

Making the GitHub repository private protects tracked metadata, but by itself
does not inject credentials and does not guarantee Surge can authenticate to a
private GitHub raw URL.

`SURGE_MANAGED_URL` must be the protected URL that returns the rendered
`surge.conf`. The renderer writes it into `#!MANAGED-CONFIG`, so the initial
one-click import and every later automatic update use the same endpoint.

## Applying changes to this Mac

The installed Mac 5.7.6 CLI supports `reload`, which rereads the current local
profile. It does not download a managed subscription. Mac 6.8.0+ adds
`surge-cli managed-profile update`; `external-resource update all` only refreshes
referenced resources and is not a main-profile update.

For this Mac's existing `Profiles/surge.conf`, render and review before applying:

```bash
LC_ALL=C LANG=C LC_CTYPE=C bash scripts/render-config.sh
python3 scripts/apply-local-surge.py
python3 scripts/apply-local-surge.py --apply --expected-current-sha256 <active_sha256_from_review>
```

The helper backs up the active profile under ignored `build/local-backups/`,
rejects an intervening manual edit, atomically replaces the file, and calls the
installed `surge-cli reload`. A failed reload restores the backup. This applies a
local render; it does not publish a new hosted subscription.

Mac 5.7.6 requires plain HTTP health-test URLs. Keep the standard gstatic probe;
HTTPS health tests require Mac 6.10.0+ / iOS 5.23.0+. HTTPS API/geolocation checks
run independently via `scripts/probe-polymarket-hk.js`. Routing validation and the
apply helper reject HTTPS health-test URLs before replacing the local profile.

See [the HK pool measurement and implementation](docs/reviews/2026-10-19-cf-hkg-selection.md).

## Platform-specific behavior

One Surge profile is used for both platforms. `#!IOS-ONLY` enables hotspot,
APNs and cellular handling on iOS. `#!MACOS-ONLY` applies the work/DLP process
reject list only on macOS.

The node pool assignments were imported from `surgeconf-260830.conf`. Ingress
hostnames do not prove egress country; verify every node's public exit IP before
depending on either fixed-egress guarantee. See `private/nodes.md` for the items
that still require verification.

## Validation

```bash
./scripts/check-rules.sh
```

The GitHub Action runs the same remote-rule check daily.

## One-click install service

The deployed configuration service is hosted at `config.fallback.page`. Its
unguessable path token is stored only in
`~/.config/surge-config/config-service.env`. Opening
that protected path in Safari shows buttons for Surge and Shadowrocket.

Surge Mac 6.7 or later can use the same browser install button. On older Mac
versions, use **Profiles > Download Profile from URL** and paste the protected
managed-profile URL, or update Surge first.

`edge-bcd7d61c.pages.dev` hosts EdgeTunnel as a Pages Function in the
dedicated Cloudflare account registered as `infra cloudflare-edgetunnel`.
Its Functions and KV quota is separate from the original account serving
`config.fallback.page` and other business services. CF node server names, TLS
SNI and WebSocket Host headers use this new ingress; policy groups and rules
retain their existing behavior. Pages deploys the same pinned Worker module
directly, without forwarding through the original account. Production and
preview use `fail_open=false`: when the dedicated account exhausts its free
quota, EdgeTunnel is allowed to stop until the quota resets. The old
`edge.fallback.page` ingress is retired after the new client path is verified.

Surge routes `*.argotunnel.com` through the native `UX Only` pool before
broad lists, so business Cloudflare Tunnel connectors do not depend on
EdgeTunnel's free quota. The desktop tunnel exception is intentionally not
added to the phone profile.

Authentication values remain Cloudflare Worker secrets with an ignored local
recovery copy in `~/.config/surge-config/edgetunnel.env`. Migration details and
the deployed module checksum are in [cloudflare/edgetunnel/README.md](cloudflare/edgetunnel/README.md).

Set `SURGE_CONFIG_HOME` to override this local credential directory. Keep the
directory mode at `0700` and each credential file at `0600`.

## YouTube and crypto routing

Both profiles use `YouTube = select, CF Edge Auto`. The group has one member,
so a remembered UX or KR selection cannot keep video traffic on another pool
after the profile updates. This fixes the policy, not the exit country or speed:
CF egress can change, and latency selection does not guarantee faster video.

YouTube rules run before broad Google and domestic lists, including inline
API/video/thumbnail rules when remote lists are unavailable. Thus YouTube uses
CF while other Google services retain UX. Reconnect an existing video stream
after updating the profile; account settings and YouTube's IP classification
can also affect the displayed country. X uses CF, and Futu retains CF first
with DIRECT on failed CF health checks.

`rules/proxy-extra.list` covers Backpack, OKX, Bitget,
Coinbase, Kraken, wallets, DeFi, explorers and market-data sites. The
[Backpack API](https://docs.backpack.exchange/) and WebSocket subdomains
are covered by `backpack.exchange`; wallet links use `backpack.app`.
These rules explicitly target `CF Edge Auto`, independently of the manual
`Proxy` selection. No shared CDN suffix is broadly proxied.

## Bybit IP restriction

Bybit uses the dedicated `Bybit = select, KR HTTPS 01` group in both profiles.
Inline rules cover `bybit.com`, `bybitglobal.com`, `bybit.global`, `bytick.com`,
`by-tick.com` and login assets on `bycsi.com`. They precede the general crypto
and broad domain lists, and work even when remote lists fail to refresh.
The two legacy Bybit entries in `proxy-extra.list` remain for older profiles;
current inline rules override them.

During the September 15 investigation, `CF Edge Auto` selected `CF Edge CT 02 US`.
Cloudflare trace observed `104.28.152.155` / US, and the public
`https://api.bybit.com/v5/market/time` endpoint returned HTTP 403 with
"configured to block access from your country". The same probe through
`KR HTTPS 01` observed `104.28.211.29` / KR and returned HTTP 200, `retCode: 0`.
The login HTML returned 200 through both paths, so loading the page alone does
not verify API access. Its asset URLs include `fh-static.bycsi.com`.

Bybit's [restricted-country policy](https://www.bybit.com/en/help-center/article/Service-Restricted-Countries)
includes both the US and Singapore. Do not add CF/US/DIRECT fallbacks to this
group. A KR failure should remain visible instead of silently changing country.
The KR node currently uses WARP, so its IP is an observation, not a permanently
reserved address. Recheck destination-observed country and the public API if
access fails again. Network reachability does not establish account eligibility
or verify a signed-in session.

The follow-up probe also found Binance's `/api/v3/time` returning HTTP 451
("restricted location") through CF and HTTP 200 through KR. The separate
`Binance = select, KR HTTPS 01` group covers `binance.com`, `binance.vision` and
`bnbstatic.com`, including API/WebSocket subdomains. OKX's `/api/v5/public/time`
and Backpack's `/api/v1/time` returned 200 through both CF and KR; their routing
is unchanged. Public API success does not test authenticated product access.

`CF SG Auto` also measured as **US** during this investigation (trace exit
`104.28.158.203`, LAX), and failed the Bybit/Binance probes. Its historical SG
name must not be treated as a country guarantee.

## Local HTTP API

Surge's HTTP API exposes the request log and policy state, which is how routing
problems get diagnosed from another machine. Two things are easy to get wrong:

- **It is a TLS listener.** Plain `http://` requests are accepted and then closed
  immediately with no error, which looks exactly like a firewall drop. Use
  `https://` and `-k` (the certificate is self-signed).
- **Repeated failed attempts get the client IP banned** by Surge's brute-force
  protection (`Too many unauthorized access from <ip>. The IP address was banned.`).

```sh
curl -sk -H "X-Key: $HTTP_API_KEY" https://<device-ip>:6171/v1/requests/recent
curl -sk -H "X-Key: $HTTP_API_KEY" https://<device-ip>:6171/v1/outbound
```

`/v1/outbound` returns the outbound mode. `{"mode":"rule"}` is the intended
state; `{"mode":"proxy"}` bypasses the entire rule set and sends *everything*,
domestic traffic included, through the global policy. Check this first when
domestic apps feel slow.

The `http-api` lines in `surge.conf` are commented out. Enabling them requires
an `HTTP_API_KEY` secret on the config-service Worker first, because
`render()` throws on any placeholder it cannot resolve and would take the whole
profile endpoint down with a 503. Deploy the secret, then re-add the placeholder
and uncomment. Until then, enable the API from Surge's own settings UI.

## QUIC

`block-quic = on`. Every Cloudflare EdgeTunnel node is trojan-over-WebSocket with
`udp-relay=false`, and `udp-policy-not-supported-behaviour = REJECT`, so a QUIC
attempt to a proxied domain could only fail — but it failed on a timeout rather
than immediately. Blocking QUIC makes the TCP fallback instant.

## Outbound mode is the first thing to check

Historical measurement on one iPhone, same WeChat session, minutes apart (Surge HTTP API
`/v1/requests/recent`, n=180 rule-mode requests, n=50 proxy-mode requests):

| | `mode: rule` (DIRECT) | `mode: proxy` (global `Fastest` -> us1) |
|---|---:|---:|
| request duration p50 | 131.7 ms | 583 ms |
| request duration p90 | 210.6 ms | 3279 ms |
| request duration max | 2126 ms | 6510 ms |
| downstream throughput | 3.83 Mbps | 0.20 Mbps |

In global proxy mode every request logs `rule: None` and
`[Rule] Global proxy outbound mode`, and domestic traffic crosses the Pacific
twice. The us1 line then showed roughly 10% packet loss, and a 3.7 KB WeChat
video chunk took 6.5 s. Rule matching itself is not the bottleneck in either mode:
on fresh connections it measures p50 8.6 ms, max 28 ms across the full rule set.

To route one app through a proxy, add a rule for it. Do not switch the outbound
mode globally.

2026-10-24 arbitrage repair: `morpho.org` explicitly uses `CF Edge Auto`. The previous route failed TLS; the original GraphQL reader now returns a complete 169-market, two-page result and the forum RSS succeeds. The active Mac profile was backed up and changed by these two lines only; unrelated source changes were preserved and not published. Policy-specific external IP measured Singapore, despite the selected member label containing US. Preserve this exception in the next managed-profile publication.
