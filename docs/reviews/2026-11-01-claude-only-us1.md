# Claude-only us1 routing — 2026-11-01 (America/Los_Angeles)

The user reserves the 200 GB/month us1 allowance for Claude online traffic.
They explicitly moved IBKR to UX as well. Claude installers use Download.

## Applied routing

- Claude's seven explicit first-party suffixes → `Claude` → `US Only`.
- Other AI, Google, overseas IBKR, named services and Mac Tunnel connectors → UX.
- UX uses `UX HY2 Direct`: `192.3.243.194:5000`, TLS name `hy.fallback.page`.
- Download and YouTube default to UX, with non-us1 alternatives.
- All general groups exclude us1 recursively; retired HTTPS02, TUIC and Shanghai
  UX relay entries were removed. Binance/Bybit KR, Polymarket HK, Futu,
  domestic/system DNS and `FINAL,DIRECT` retain their routing.
- The running Mac was in global proxy mode, selecting us1 `US HTTPS 02`.
  It is now in rule mode. Remembered AI/Download/YouTube selections were reset.

## UX repair

The UX server's default route entered a WARP interface whose last handshake
was approximately 19 days old. Native source-bound requests worked. The existing
Hysteria service runs as UID 998, allowing a process-specific route exception:

- `/etc/systemd/system/hysteria-server.service.d/20-native-ux.conf` installs
  priority 11994, `uidrange 998-998 lookup main`, on service start and removes it
  on stop. Other processes keep their existing routing.
- `/etc/hysteria/config.yaml` uses native IPv4 `192.3.243.194` and an explicit
  HTTPS resolver at `1.1.1.1:443`. Hysteria's DoH transport does not inherit its
  outbound source binding, so the UID route is required for DNS too.
- Configuration is root:hysteria, mode 0640. The original is retained at
  `/etc/hysteria/config.yaml.before-native-ux-20261102T065548Z`.
- The failed global WARP path and other server proxy protocols were not changed.

## Acceptance

- Local routing: 196 Surge / 193 Shadowrocket cases passed. Each profile rejected
  39 intentional quota-isolation violations; chaining checks also passed.
- Remote rule reachability, both profile renders and `git diff --check` passed.
- Effective Mac policy groups and rules matched the source templates.
- Policy-specific traces: UX `192.3.243.194 / US`; us1 `35.212.192.172 / US`.
- Normal-rule probes and request logs: Google 204; ChatGPT robots 200;
  IBKR public site 200; npm ping 200; Claude installer stable metadata 200.
  Anthropic models returned the expected unauthenticated 401 through us1.
- Binance and Bybit public time APIs returned 200 through `KR HTTPS 01`.
- Existing IB gateway ports 4000/4001 and Tunnel port 7844 connections used
  `UX HY2 Direct` with bytes received and sent. Account/trade authorization was
  not tested. No active non-Claude us1 connections remained at inspection.
- No large binary downloads or sustained bandwidth test were performed.

## Publication and quota boundary

The local Mac profile is applied and backed up under ignored `build/local-backups`.
The user subsequently authorized publishing both subscriptions. Commit
`8ac8e0b7dd5b752e07dbf2e15975618281866f70` is published on `main`, with
[CI 41408250699](https://github.com/KaylaONeal/surge-config/actions/runs/41408250699)
successful. Both protected hosted profiles returned HTTP 200 and matched the
local rendered bytes; the Mac managed-refresh header is restored.
The Mac global-proxy default is now `UX HY2 Direct`, verified through the native
UI and CLI environment; normal operation remains in rule mode. The old app's
HTTP API did not persist the global-policy change, while the native UI did.
Phone acceptance is separate from local and hosted-profile verification.

Cloudflare rejected the default Python urllib user agent with error 1010.
Verification using a profile-client user agent succeeded; no WAF setting or
protected URL was changed or disclosed.

Routing isolation is not a provider billing cap. It does not establish the
current month's remaining allowance or stop other clients/services on us1.
No monthly cutoff or new monitoring job was installed.

Read-only us1 inspection found no vnStat/sysstat monthly database. The external
interface `ens4` only exposed cumulative kernel counters spanning a long uptime;
these cannot establish this month's usage. Google Cloud Ops Agent is installed,
but its historical metrics and the provider's billing rules were not inspected.
