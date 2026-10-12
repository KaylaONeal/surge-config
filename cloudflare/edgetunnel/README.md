# EdgeTunnel deployment

The deployed Worker is based on `cmliu/edgetunnel` commit
`fb3212257e3527447d7368010b378f7e449444b4` with the reviewed [low-CPU relay patch](../../scripts/optimize-edgetunnel.py), and is served at
`edge-bcd7d61c.pages.dev` in the isolated account registered as
`infra cloudflare-edgetunnel` (migration: 2026-10-01).

Cloudflare resources:

- Pages production project: `edge-bcd7d61c` (advanced `_worker.js` mode)
- Original copied Worker: `surge-edgetunnel` (retained as a source archive)
- KV namespace: `surge-edgetunnel-kv`
- KV binding: `KV`
- production ingress: `edge-bcd7d61c.pages.dev`
- archived upstream module SHA-256: `c104ee5b19f2bfefdf27c2af5f9d3ff222d46dd8104b2fa8e87ac829d7b0f945`
- optimized module SHA-256: `5dbf087fea73cb0cc9eef8543c8c0ef88dc6a79660dd95298e86abca5494257f`
- production and preview `fail_open`: `false`

Runtime configuration disables KV access logging and enables two concurrent TCP
dials. `ADMIN`, `KEY` and `UUID` are Worker secrets. The local recovery copy is
`~/.config/surge-config/edgetunnel.env`, which is outside Git.

The migration copied the deployed module byte-for-byte, retained the existing
Trojan/WebSocket authentication and runtime settings, and moved `config.json`,
`cf.json` and `tg.json` into the new account's KV. Account-specific API
credentials are cleared rather than inherited. CF node labels and policy
groups are preserved; server/SNI/WebSocket Host use the new account's ingress.

`scripts/migrate-edgetunnel-account.py` documents the guarded one-time
migration. Its default mode audits without writing; `--apply` creates the
target resources and refuses to overwrite an existing target Worker or KV.
Run it through `infra run` so credentials come only from the environment.
Source and target account IDs also come from the infra environment;
account identifiers and credential values are not published in this repository.

The first workers.dev ingress passed a US WebSocket check but its local
optimized TLS connections closed before the handshake. Pages' hostname
passed the same local TLS checks, so `scripts/deploy-edgetunnel-pages.py`
deploys the identical module directly as a Pages Function with the isolated
KV and secret bindings. It does not proxy through either archived Worker.
Functions requests consume the dedicated account's Workers quota.

On 2026-10-01, policy-specific HTTPS probes returned 200 for CF Auto, CT 01,
CU 01 and CM 01; actual exits varied between SG and US. Node names are retained
for client continuity and do not guarantee a country. The fixed AI policy
remained on the existing US exit.

The dedicated account remains on its free limits. Exhaustion may stop
EdgeTunnel, and must not trigger an automatic fallback to the original
account. Retire the original public ingress after verifying the client path;
keep the original Worker and KV as an archive rather than deleting their data.

The upstream Worker is intentionally pinned. Review upstream changes before
deploying a newer commit because the Worker can initiate arbitrary outbound TCP
connections.

## Previous native Smart selection (2026-10-01; replaced 2026-10-12)

`CF Edge Auto` in `surge.conf` uses Surge's native `smart` group on Mac and iOS.
Its members remain the same seven Trojan-over-WebSocket CF ingress nodes. Real
connection quality, retransmissions, first-response latency and per-site history
inform selection; unavailable members can be retried using another CF member.
The WebSocket transport, Pages deployment, secrets, rules and all non-CF groups
are unchanged. No external program, local adapter, XHTTP or HTTP/3 client is
installed by this change.

Smart requires Mac 5.7.0+ or iOS 5.11.0+ with Smart unlocked. It is not purely
passive: it has a fixed five-minute health-test schedule, so `interval=7200` and
`tolerance` are omitted. Seven members on 288 daily rounds imply approximately
2,016 scheduled proxy requests per continuously testing device per day, compared
with 84 on a two-hour schedule; startup/network/failure tests and real traffic
are additional. This is a planning estimate, not a measured request count.
`evaluate-before-use=false` avoids waiting for an initial test on first use.
CF region pools and the Shadowrocket profile keep their existing two-hour
`url-test` behavior. The basic Smart behavior works on the installed Mac 5.7.6;
the newer three-second silent-failure handling requires Mac 6.8.0+/iOS 5.21.0+
and is not claimed for this machine.

The dedicated free account remains fail-closed on quota exhaustion. Smart
selection cannot recover an account-wide quota failure, does not preserve a
fixed exit country, and does not resume an already established TCP session on
another node. Existing CF connections need not move when the preferred member
changes. Connections using the fixed AI, download, exchange or DIRECT policies
keep their original path.

References: [Surge Smart group](https://manual.nssurge.com/policy-groups/smart.html),
[Surge Trojan transport](https://manual.nssurge.com/policies/trojan.html).

## CPU mitigation and low-frequency probes (2026-10-12)

A Pages tail correlated `exceededCpu` with an OpenD quote disconnection within
milliseconds. Keep the same CF account, host, authentication, KV bindings and
routing; do not substitute old market data or switch to the original account.

`python3 scripts/deploy-edgetunnel-pages.py --optimize` audits the candidate.
Add `--apply` to deploy the reviewed patch to the existing Pages project without
rewriting its live settings. The patch refuses a different archived source hash.
The original October 1 deployment is retained for rollback.

The replacement TCP downlink relays received bytes in order without Grain
batching, per-packet timers or BYOB copies. It preserves optional response
headers, async adapters, no-data-only retries, and generation-aware cleanup.
Explicit UUID WebSocket connections skip an unused derived-ID MD5 calculation;
UUID authentication and the other login/configuration paths remain unchanged.
Run `node --test tests/edgetunnel-stream-relay.test.mjs` for stream invariants.

Surge CF Edge Auto now uses native `url-test` with a two-hour result lifetime,
as Shadowrocket already did. Futu fallback also reuses tests for two hours;
first-use evaluation no longer blocks Surge. Connection failures may trigger
an earlier retest. Each Surge CF leaf tests an external gstatic URL explicitly,
not the Worker-local synthetic Cloudflare 204 responder. This reduces scheduled
probes but is not a fix for every possible CPU/resource failure.
