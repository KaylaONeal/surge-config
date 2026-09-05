# surge-config

Git-managed Surge configuration shared by iOS and macOS. Real node topology is
tracked; passwords and other authentication material are not.

## Routing policy

| Traffic | Policy | Default exit |
|---|---|---|
| AI / LLM services (except Google) | `AI` | US-only fallback pool |
| Google, Telegram, X and common overseas services | `CF Edge Auto` | Best mainland CF ingress |
| Domestic services | literal `DIRECT` rules | DIRECT |
| IBKR overseas sites and trading gateways | `CF Edge Auto` | Best mainland CF ingress |
| IBKR mainland trading gateway (`*.ibllc.com.cn`) | `DIRECT` | DIRECT |
| Ads | `AdBlock` | REJECT, switchable to DIRECT |
| Cloudflare fallback | `CF Edge Auto` | Best of direct/CT/CU/CM EdgeTunnel ingress |
| Everything unmatched | literal `FINAL,DIRECT` | DIRECT |

AI rules are evaluated before Google, Microsoft and Global rule sets. The
`US Only` group never falls back to JP or KR. Google AI is deliberately outside
the `AI` policy and uses `CF Edge Auto` together with the rest of Google.

## Why AI traffic is not chained through Cloudflare

Routing the US-pinned AI exit through the Cloudflare EdgeTunnel ingress looks
attractive, because it would keep the egress IP on us1 while replacing the slow
mainland-to-US leg. It was tried and **measured to be slower**, so it is not in
this profile. Time to a completed `CONNECT` through the us1 HTTPS proxy, from a
mainland home line, bypassing the local Surge tunnel (2026-09-06, 6 samples):

| Path | median | min |
|---|---:|---:|
| direct to `us1:443` | 0.68 s | 0.67 s |
| chained via CF `188.164.248.21` (SEA colo) | 1.01 s | 0.99 s |
| chained via CF `104.17.107.60` (HKG colo) | 3.23 s | 1.39 s |

The reason is that the Cloudflare ingress addresses in `CF Edge Auto` do not
anycast to a nearby colo. Queried from the mainland, `188.164.248.21`,
`104.26.0.109` and `172.67.66.108` land on **SEA**, `8.35.211.67` on **LAX** and
`8.35.211.67`/`104.17.107.60` on **SJC**/**HKG**. Only one of six is in Asia.

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

## Platform-specific behavior

One Surge profile is used for both platforms. `#!IOS-ONLY` enables hotspot,
APNs and cellular handling on iOS. `#!MACOS-ONLY` applies the work/DLP process
reject list only on macOS.

The node pool assignments were imported from `surgeconf-260830.conf`. Ingress
hostnames do not prove egress country; verify every node's public exit IP before
depending on the `AI` US-only guarantee. See `private/nodes.md` for the items
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

`edge.fallback.page` hosts the separately deployed EdgeTunnel Worker. Its
authentication values are Cloudflare Worker secrets with an ignored local
recovery copy in `~/.config/surge-config/edgetunnel.env`.

Set `SURGE_CONFIG_HOME` to override this local credential directory. Keep the
directory mode at `0700` and each credential file at `0600`.
