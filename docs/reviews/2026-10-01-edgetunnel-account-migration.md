# EdgeTunnel account migration — 2026-10-01

Status: deployed, published and active on the local Surge client. The original
EdgeTunnel public ingress is retired. Phone clients must refresh their
published subscription to use the new ingress.

## Deployment and isolation

- Dedicated account: registered as `infra cloudflare-edgetunnel`; account
  identifiers and API tokens are kept outside the public repository.
- Production project: `edge-bcd7d61c`, Pages Functions advanced mode.
- Ingress: `edge-bcd7d61c.pages.dev`.
- KV: `surge-edgetunnel-kv`, bound directly in the dedicated account.
- Worker module SHA-256:
  `c104ee5b19f2bfefdf27c2af5f9d3ff222d46dd8104b2fa8e87ac829d7b0f945`.
- The module is byte-identical to the original pinned EdgeTunnel deployment.
  Existing authentication is retained; business-account API credentials are
  cleared from the migrated account-specific KV configuration.
- Production and preview use `fail_open=false`. Quota exhaustion may stop
  EdgeTunnel; no business-account fallback, account rotation or paid upgrade
  is configured.

Pages executes the module directly rather than forwarding through a Worker
in the original account. Both archived `surge-edgetunnel` Workers retain
their code and KV, with workers.dev and preview ingress disabled. The old
`edge.fallback.page` custom-domain binding is removed, and no old Worker route
remains. Ten other original-account Worker domain bindings were preserved.

## Verification

- Verified-certificate TLS and WebSocket probes through CT/CU ingress
  completed with valid HTTP 101 upgrades at the new Pages hostname.
- Policy-specific HTTPS probes through CF Auto, CT 01, CU 01 and CM 01
  returned HTTP 200 before publication and again after retiring the old
  ingress. Destination-observed exits varied between SG and US; historical
  node names do not guarantee a country.
- The fixed AI policy continued to use the existing US exit.
- Effective local profile: all seven CF definitions use the new SNI and
  WebSocket Host; other profile lines and remembered selections are retained.
- Migration configuration commit: `f4b48d6`; GitHub check-rules run
  `36803290686` completed successfully.
- Published protected Surge and Shadowrocket profiles returned HTTP 200 and
  matched the committed templates' credential render byte-for-byte, with
  zero references to the old ingress. Credential values and protected URLs
  are not recorded here.
- Original configuration service `/health`: HTTP 200, `ok`.
- The dedicated account's `pagesFunctionsInvocationsAdaptiveGroups` dataset
  recorded 2,190 Pages Function requests for
  `2026-10-01T01:18:36Z`–`2026-10-01T02:03:36Z`: 1,401 success, 720 client
  disconnects, 55 script exceptions and 14 resource-limit outcomes. This is
  an account-wide, adaptive-sampling snapshot, not a billing balance or an
  exact per-project counter; the provider reported `scriptName=__unknown__`.
  The migration preserves the pinned runtime code and does not claim to fix
  its existing exception/resource-limit behavior.

The local `argotunnel.com → US Only` exception is included in the publication
to keep business Cloudflare Tunnel connections independent of EdgeTunnel.
Live connector requests through the native US nodes completed successfully.
The routing checker includes first-match and ordering coverage for those
desktop connector hosts. This platform-specific exception is not added to
Shadowrocket.

## Earlier ingress investigation

The copied standard Worker's workers.dev endpoint accepted a WebSocket
upgrade from the existing US server, but local CT/CU ingress closed during
verified TLS negotiation. Account-level workers.dev SNI and port 8443 also
failed. Old SNI with new WebSocket Host returned 403. These findings were
network-specific and did not prove a universal workers.dev block.

The account's Pages hostname completed verified TLS on the same CF IPs.
Deploying the same module as Pages Functions provided a working ingress
without buying or transferring a domain. No proxy chain through the
original business account is involved.

The unrelated pre-existing YouTube documentation correction, editor swap
file and project instruction files remain outside the migration commits.
