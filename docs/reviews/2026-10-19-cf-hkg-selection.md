# CF HKG pool and Polymarket routing — 2026-10-19

## Current implementation

`polymarket.com` and every subdomain route to `CF HKG Auto`, covering web,
Gamma, CLOB, Data, Relayer, WebSocket and Perps. The group falls back only
between `CF HKG 01` and `CF HKG 02`, using the existing CU 01/02 ingress IPs.
Both leaves explicitly supply the same three-IP Hong Kong reverse-proxy pool:

| Configured proxyIP | Polymarket-observed IP in individual-node test | Country |
|---|---|---|
| 47.239.4.246 | 47.239.4.246 | HK |
| 8.212.60.215 | 8.210.177.80 | HK |
| 219.76.13.166 | 219.76.13.166 | HK |

These complete-chain checks ran at 16:51 CST. All three geoblock checks returned
HTTP 200 / HK / blocked=false. CLOB and Perps public time checks passed on the
second and third candidates; the first candidate had one WebSocket close for
CLOB and later passed through the group. This is public network verification,
not private account or order authorization.

The WebSocket path uses a percent-encoded list:

```text
/?proxyip=47.239.4.246%2C8.212.60.215%2C219.76.13.166
```

The pinned Worker decodes the query value, tries the explicit reverse-proxy
addresses, and disables its default reverse-proxy fallback. Native Surge handles
CF-ingress failover; the Worker retries the explicit reverse-proxy addresses
when candidate TCP connection setup or the initial write fails. A later stream
closure is not a guarantee of another IP retry. Standard health probes alone do not validate a target's
country or this reverse-proxy path.

The ordinary Worker-direct path still exists for destinations that accept it.
This is a measured, destination-verified HK pool for Polymarket, not a permanent
geographic guarantee for every protocol and arbitrary website. Recheck exit
countries before relying on a later measurement; upstream IP behavior can change.
AI fixed-US, existing CF groups, exchange groups and DIRECT rules remain intact.
No Worker deployment, paid service, server or persistent job was created.

## Why the old nodes exited through SG

Before modification, the Mac active profile matched the current rendered source
byte for byte. Its CF nodes already used the new Pages ingress. It was not a
stale local-node configuration.

At 16:38 CST, both original CU nodes reported SG / 43.160.241.174 to Polymarket.
The existing upstream DNS explains the regional mismatch:

```text
hkg.proxyip.cmliussss.net -> proxyip.sg.cmliussss.net -> SG reverse-proxy pool
proxyip.hk.cmliussss.net  -> separate HK reverse-proxy pool
```

The new pool pins tested numeric proxyIP addresses rather than either dynamic
regional hostname. The HK reverse proxies came from the existing provider's HK
pool. They are not the 104.28.x.x Worker exit IPs reported by IPinfo.

## Mac compatibility incident and correction

The initial candidate set `test-url=https://polymarket.com/api/geoblock` on its
leaves. The user reported that this prevented Surge from starting and manually
restored those three values to the standard HTTP gstatic probe. That manual
change was verified and retained. A previous `surge-cli reload` success was not
sufficient proof of restart compatibility.

The installed Surge is Mac 5.7.6 (2838). HTTPS health tests require Mac 6.10.0+
(or iOS 5.23.0+). The final templates use only HTTP health-test URLs. HTTPS API
and geolocation verification runs independently in `probe-polymarket-hk.js`.
`check-routing.py` and the local apply helper reject HTTPS health URLs before
installation; an in-memory regression check confirmed rejection.

## Local CLI application

Mac 5.7.6 supports `reload`; it does not have `managed-profile update`. The
latter command exists on Mac 6.8.0+. `external-resource update all` updates
referenced resources, not the main managed profile.

For the existing local profile, use:

```sh
LC_ALL=C LANG=C LC_CTYPE=C bash scripts/render-config.sh
python3 scripts/apply-local-surge.py
python3 scripts/apply-local-surge.py --apply --expected-current-sha256 <reviewed_active_sha256>
```

The helper does not fetch or publish subscriptions. It rejects intervening
manual edits, backs up the profile, atomically installs the rendered file,
reloads Surge, and rolls back on a failed reload. A negative stale-SHA test
confirmed that it leaves the active profile unchanged.

The final source was applied at 16:57 CST with the manually repaired profile
as its reviewed predecessor. Backup:
`build/local-backups/20261019T085705.785042Z/surge.conf` (credential-bearing,
ignored, mode 0600). Applied profile SHA-256:
`78305d7eb44901b4e909de018257b88cba942baecbede05a85c188e556c62697`.

Final verification at 16:57:07–16:57:23 CST passed all 12 requests:

| Selection | Polymarket country / observed IP | CLOB time | Perps time |
|---|---|---|---|
| CF HKG 01 | HK / 47.239.4.246 | 200 | 200 |
| CF HKG 02 | HK / 47.239.4.246 | 200 | 200 |
| CF HKG Auto | HK / 47.239.4.246 | 200 | 200 |
| Normal rules (no forced policy) | HK / 47.239.4.246 | 200 | 200 |

The active file matched the rendered final SHA, and the running effective
profile contained the Polymarket suffix rule and exactly two HK ingress members.
No HTTPS `test-url` remained. The three-IP pool's individual candidates were
verified separately before enabling the shared retry pool; this task did not
force a live outage of those third-party servers.

## Validation and scope

- Local policy checks: 154 Surge and 151 Shadowrocket route cases passed,
  including Polymarket suffix boundaries and the explicit HK-only members/IPs.
- `bash scripts/check-rules.sh` passed all upstream URL and routing checks.
- Invalid HTTPS health URLs and stale active-file SHA are rejected before apply.
- The existing hosted service renders the published GitHub main branch.
  Publication acceptance requires CI and both protected profiles to match the
  local render. Phone clients must refresh their subscription; phone execution
  has not been observed in this task.

## Reproduce

```sh
/Applications/Surge.app/Contents/Applications/surge-cli script evaluate scripts/probe-polymarket-hk.js generic 120
```

This probes each HK ingress, the HK group, and normal rules without changing
selections. `scripts/probe-cf-regions.js` preserves the original seven-node,
two-target comparison.

## Sources

- [Surge testing and HTTPS version requirements](https://manual.nssurge.com/tools/testing.html)
- [Surge CLI managed-profile update](https://manual.nssurge.com/tools/cli.html)
- [Surge fallback group](https://manual.nssurge.com/policy-groups/fallback.html)
- [Pinned EdgeTunnel proxyIP parser](https://github.com/cmliu/edgetunnel/blob/fb3212257e3527447d7368010b378f7e449444b4/_worker.js#L6217)
- [Pinned EdgeTunnel TCP retry logic](https://github.com/cmliu/edgetunnel/blob/fb3212257e3527447d7368010b378f7e449444b4/_worker.js#L2345)
- [Polymarket read-only geoblock check](https://docs.polymarket.com/api-reference/geoblock)
