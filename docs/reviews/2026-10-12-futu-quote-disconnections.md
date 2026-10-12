# OpenD quote connection instability — 2026-10-12

Status: the CF CPU termination mechanism was diagnosed, then the user authorized
cache/probe-frequency and Worker CPU optimizations. The optimized Pages module
was deployed at 14:17:18 CST. OpenD stays on CF; no OpenD restart, native-exit
cutover, extra gateway or paid-plan change was made. See the mitigation below.

## Verified observations

- mini's OpenD PID is 537. Its process rule currently uses `Futu -> CF Edge Auto`,
  with live connections on CF Edge CU 01/02. No OpenD restart or login action
  was performed.
- Count only `GTWLog.Main` lines containing
  `Quote ConnectionDisconnected,Reconnecting`. The API notification repeats
  each event, so counting both doubles the result. The first observed event
  is October 11 at 17:48:05 CST, not simply 17:00.
- October 6–10: no matching quote-disconnection event. October 11: 111 events.
  October 12 complete hourly buckets: 09:00–09:59 = 147; 10:00–10:59 = 500;
  11:00–11:59 = 431; 12:00–12:59 = 5. After 13:00, failures resume during the
  trading session, including 13:06 = 16, 13:08 = 10 and 13:09 = 13 events.
- The October 10 `106.55.66.56-HK` and similar lines are **Trade Connection1**.
  Comparing them with October 11 **Quote Connection: ConnNN-CN** mixes two
  connection types. It does not establish a quote-server HK-to-CN migration,
  and a server label does not establish the client's public exit country.
- `Network interruption.` responses affect snapshots, option expirations,
  option chains, positions, funds and historical bars. Login state and the
  local listening port are insufficient health checks.

## Routing and external evidence

At approximately 13:10 CST, Surge policy-specific read-only public probes:

| Policy | Observed exit | Cloudflare trace | Futu OpenAPI landing page |
|---|---|---|---|
| CF Edge Auto | 45.77.33.228, SG | 200 | 200 |
| KR HTTPS 01 | 104.28.211.29, KR | 200 | 200 |
| US HTTPS 01 | 35.212.192.172, US | 200 | 200 |

These are short requests, not quote-session stability tests. The registered
KR proxy uses WARP for Futu; only its exchange allowlist uses the Oracle native
exit. Switching to KR would remove the Pages WebSocket hop but would not
provide a proven fixed native Oracle exit.

Git HEAD remains the October 8 routing publication, `65bf912`. The Cloudflare
Pages deployment API shows only the October 1 deployment
`a931c74f-bbb6-45b4-8dec-4766171dcc54`; no October 11 redeployment was found.
This does not rule out runtime, KV, egress pool or destination-side changes.

Cloudflare `pagesFunctionsInvocationsAdaptiveGroups` account-level estimates
(UTC dates, October 12 partial through 05:15 UTC):

| Date | Requests | Script exceptions | Resource limit failures | Internal errors |
|---|---:|---:|---:|---:|
| 2026-10-10 | 64834 | 22907 | 2586 | 152 |
| 2026-10-11 | 57346 | 19163 | 4681 | 77 |
| 2026-10-12 partial | 18030 | 4780 | 2077 | 113 |

These aggregate errors are evidence of problems in the shared CF path, not
per-OpenD attribution. They already existed on October 10. The outcome does
not identify whether a resource failure is CPU, memory, or another limit.
See [Pages invocation status definitions](https://developers.cloudflare.com/pages/functions/metrics/).

## Directly correlated failure evidence

A temporary Cloudflare Pages deployment tail discarded request URLs, headers,
payloads and application logs. It retained only timestamps, CPU/wall time,
invocation outcomes and sanitized exception messages. All temporary diagnostic tail
sessions were deleted after sampling (HTTP 200); no ongoing capture remains.

A 50-second sample recorded 9 `exceededCpu`, 17 `exception` and 39 `canceled`
outcomes. These totals cover shared CF traffic and are not an OpenD error rate.
The CPU errors explicitly say `Worker exceeded CPU time limit.` Some exceptions
also report `Network connection lost.` and a runtime-canceled hung request.

For one quote session, three independent observations align (epoch seconds
avoid the OpenD human-readable timestamps, which can round differently):

| Observation | Timestamp / value |
|---|---|
| Surge opens OpenD -> 121.5.99.180:9595 via CF CU 01 | 1791782363.850759 |
| CF invocation starts | 1791782364.397 |
| CF outcome | exceededCpu; CPU 10 ms; wall time 2271 ms |
| CF end inferred from start + wall time | 1791782366.668 |
| Surge records connection closed | 1791782366.689035 |
| OpenD logs quote disconnected | 1791782366.697199 |

OpenD identifies that quote server as `121.5.99.180-CN`. Thus the CF termination,
Surge close and quote-disconnection event differ by about 21 ms then 8 ms.
The connection received 34,251 bytes before closure. Another invocation starting
at 1791782371.405 ran for 1624 ms, exceeded CPU at 36 ms, and aligns within
24 ms with the next quote-disconnection event at 1791782373.052456; its nearest
OpenD flow was `124.156.124.226:443` with roughly 110 KB received.

Cloudflare documents a 10 ms CPU budget for free HTTP Workers, distinct from
wall-clock duration, and termination when limits are consistently exceeded.
[Limits reference](https://developers.cloudflare.com/workers/platform/limits/).
This explains why short health checks can pass while data-heavy quote sessions
fail. CU 01/02 only change ingress; both use the same deployment and limits.

The archived module matches the recorded deployment SHA-256. Inspection finds
per-packet JS stream/queue/copy work, two concurrent TCP dials and a one-second
TCP setup timeout. No short fixed lifetime for an established quote session was
identified. The dial timeout alone cannot explain an established session that
already received data being terminated with `exceededCpu`.

## Why October 11, and what remains unknown

The first quote failure was 17:48:05 CST. CF resource-limit outcomes increased
from 36 in 17:30–17:44 to 231 in 17:45–17:59, but an earlier 16:15–16:29 bucket
had 513. These are aggregate correlations, not a unique trigger. No October 11
code deployment was found. KV changes, destination behavior, traffic shape and
runtime changes remain unproven. Existing sessions surviving a rule edit and
only adopting the new route on reconnect are another possible explanation,
not verified historical evidence.

## Mitigation choices and read/trade separation

- Retaining free CF: simplify/profile the Worker data path and validate with
  real quote traffic. This may reduce CPU but cannot guarantee arbitrarily
  sustained streams within the free budget. Timeout tweaks and changing CF
  ingress alone do not remove the CPU limit. No Worker redeploy was performed.
- A plan with higher CPU limits is a potential CF remedy, subject to separate
  paid-service authorization and live quote validation. No purchase or change
  was made.
- Split **quote** and **trade** channels, not all reads versus writes. Positions,
  funds and order queries are reads on trade channels. Official OpenD public
  configuration/operation references do not document independent quote/trade
  upstream proxy settings. The installed GUI XML also exposes no such setting.
- Surge sees one executable and encrypted connections. Both channel types use
  rotating IPs and port 443; quote traffic was also observed on 9595. A static
  IP/port split is incomplete, and exclusive ownership of a whole cloud subnet
  has not been established. It must not silently route an order path DIRECT.
- Two separately identifiable OpenD gateway processes are an engineering option:
  the quote-only gateway uses DIRECT; the trading gateway uses an established
  non-mainland native proxy. Client applications select the corresponding
  gateway. Concurrent-login/quote-right behavior, isolation, credentials and
  endpoint changes need validation and user involvement before deployment.
  No extra gateway or service was started.

References: [official OpenD options](https://openapi.futunn.com/futu-api-doc/opend/opend-cmd.html),
[operation commands](https://openapi.futunn.com/futu-api-doc/opend/opend-operate.html).

The initial diagnosis above predates the authorized mitigation below.

## Authorized mitigation — 14:17 CST onward

The user asked to reduce frequency/overhead, preserve useful cached state, and
commit after resolving the CF issue. Changes:

1. Pinned-module patch replaces TCP downlink Grain queues, 1 ms timers and BYOB
   copying with in-order streaming, preserving headers, async adapters,
   no-data-only retries and stale-connection cleanup. Valid explicit UUID
   WebSocket requests skip an unused derived-ID hash; authentication remains.
2. CF Auto changes from Smart (fixed five-minute tests) to native url-test
   (`interval=7200`, background evaluation). Futu fallback also uses 7200 s.
   Baseline seven-node testing falls from 2016 to 84/day/client, not counting
   connection failures or network changes. AI's native fixed-US pool is unchanged.
3. Each Surge CF leaf tests gstatic explicitly. The original Worker fabricates
   a local 204 for `cp.cloudflare.com`; that synthetic reply did not test real
   external forwarding. The replacement probe does. Shadowrocket retains its
   existing real group-level gstatic probe.
4. Daily managed-profile updates retain `strict=false`. Cached profiles/tests
   can survive refresh failures; they cannot revive a CPU-terminated TCP session.
   No quote or order-response data is cached/replayed as a network workaround.

Deployment: `35bfebe0-35fd-460f-be10-bc1232d5497d`, production success at
2026-10-12 06:17:18.548655 UTC. Module SHA-256:
`5dbf087fea73cb0cc9eef8543c8c0ef88dc6a79660dd95298e86abca5494257f`.
Settings/secrets/bindings were preserved by the code-only `--optimize` deployment.
Rollback retains the original production deployment:
`a931c74f-bbb6-45b4-8dec-4766171dcc54` (Pages deployment rollback API).

Validation before publication:

- Seven Node stream integrity/lifecycle tests passed; generated module syntax
  passed. CI runs these tests with the existing routing/upstream checks.
- Both profiles pass routing checks (141/138 host cases plus subnet cases),
  upstream rules are reachable, and rendering completes. Locale was explicitly
  set to `C` for rendering because this shell's `C.UTF-8` was unsupported by Perl.
- Before deployment: 38 quote disconnects and five `Network interruption`
  responses in the preceding 300 seconds.
- From 14:18 to 14:21: no quote disconnects or network-interruption responses;
  the new CF quote session exceeded 2 MB received. Low-frequency profile reload
  at 14:22 caused one reconnect; quote service reconnected at 14:22:09.
- A fresh 50-second tail on the optimized deployment observed zero exceededCpu
  outcomes (35 canceled, 10 other exceptions, 2 ok). This is a bounded shared
  traffic sample, not proof that every CF error is eliminated. Tail was deleted.
- pro15's existing minute sampler saved two pairs with `errors={}` at 14:18,
  14:19, 14:20 and 14:21. No collector or order task was triggered manually.
- The broad collector still reports `futu-options: cooldown / ValueError` in its
  latest report. That is a separate unresolved application result; do not claim
  all collectors recovered merely because the transport and sampler recovered.

At 14:27 CST, the post-reload quote session had no further disconnections for
approximately five minutes. The sampler run begun during reload failed once
(stock snapshot unavailable, reported 14:22:13); the 14:23, 14:24, 14:25 and
14:26 runs all saved two pairs with no errors. This transition failure is not
excluded silently from the recovery evidence. Longer-term stability still
requires ordinary trading-session observation.
