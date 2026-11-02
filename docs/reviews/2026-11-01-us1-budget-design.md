# us1 proxy budget protection — staged design

Prepared 2026-11-02. **Not deployed; no verified monthly baseline exists yet.**
This is a response-side kernel cutoff plus proxy-service shutdown, not an
absolute cap on host or billing-account charges. No billing API, credentials,
API enablement, new packages, or permission changes are part of this code.

## Google allowance and current access gap

Google's [network pricing](https://cloud.google.com/vpc/network-pricing) lists
200 **GiB** of free Standard Tier internet outbound transfer; incoming traffic
is free. Premium Tier has different prices. The pricing page says the Standard
allowance is per account across regions, while the
[overview](https://docs.cloud.google.com/network-tiers/docs/overview#free_tier)
describes region/SKU scope. Use the conservative account-wide interpretation
until the actual account and SKU are inspected; do not give every VM a fresh
200 GiB allocation. This allowance does not cover every network product charge.

[Monthly pricing tiers](https://docs.cloud.google.com/billing/docs/how-to/pricing-table#about_pricing_tiers)
reset at midnight Pacific Time on the first day of the month, including DST.
[Alerts-only budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets)
do not stop usage or billing. The
[current spend-cap service list](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)
does not include Compute Engine/VPC traffic. Monitoring is suitable for baseline
reconciliation, not the immediate cutoff: [Compute network sent-byte metrics](https://docs.cloud.google.com/monitoring/api/metrics_gcp_c#compute)
are sampled every 60 seconds and can remain invisible for a further 240 seconds.

us1's service-account token could not read Compute, Monitoring or Billing
because of its restricted OAuth scopes. The existing mini gcloud user also
lacked access to the project. A Google Cloud login was requested through infra
question 233 and expired without a response. Neither actual network tier nor
this month's baseline has therefore been established. No cloud permission,
network tier, fixed IP or billing setting was changed.

## Scope and evidence

The physical interface `ens4` carries host and Docker outbound traffic. The
ledger accumulates its `tx_bytes` in the `America/Los_Angeles` calendar month.
The conservative threshold is 180 GiB (193273528320 bytes), retaining 20 GiB
relative to a hypothetical applicable 200 GiB tier allowance. Network tier,
billing SKU, account-wide usage, and historical baseline still require cloud
account verification. Local counters are not the provider's billing meter.

Actual proxy targets are `hysteria-server.service` (UID 999, UDP 4444) and
Docker container `gost` (UID 0, host network, TCP 443). The Shanghai relay also
terminates at UDP 4444. SSH, `tsla-webhook-inbox-1`,
`tsla-webhook-tunnel-1`, s-ui and Google agents are separate consumers. Blocking
UID 0 or all ens4 traffic would damage those consumers and is not implemented.

The official [quota documentation](https://wiki.nftables.org/wiki-nftables/index.php/Quotas)
defines named `over` quotas and their accumulated used bytes. An `inet`
postrouting rule evaluates the quota for every IP packet leaving ens4,
including IPv4/IPv6 and Docker-forwarded traffic. On exhaustion it jumps to a
chain dropping only TCP source port 443 and UDP source port 4444; there is no
early established-connection ACCEPT. Thus already-established proxy responses
also stop even if the user-space timer is unavailable.

This does **not** drop the proxies' temporary upstream source ports. The next
timer check adds the unconditional inbound/outbound proxy-port fence and stops
the two dedicated proxy objects to close upstream sockets. SSH/webhook and other
non-proxy outbound traffic remain possible and continue to consume any applicable
allowance. No finite total-host/account overshoot bound is claimed. Ten-second
sampling plus command timeouts controls normal shutdown delay, but does not bound
traffic while the timer/process is dead. The 20 GiB margin is a buffer, not proof
that charges cannot occur. Dropped packets also count toward the kernel quota,
and link-layer versus IP byte counts can differ; the ledger uses the larger
physical or kernel-derived estimate and can block conservatively early.

## Initialization without a gap or a live quota reset

1. Validate baseline before mutation: explicit `verified=true`, evidence reference,
   LA month, timezone-aware timestamp no older than one hour, matching boot ID,
   current ens4 counter at least the reviewed counter. Unknown is never zero.
   Same-month recovery also carries forward the saved physical total plus every
   monotone same-boot TX byte from its last sample to the current snapshot, even
   if no blocked timer ran. A newly reviewed smaller number cannot erase that
   independently observed floor or the prior kernel-derived floor.
2. Persist `blocked/activation_pending`, atomically install the dedicated port
   fence, and stop only the two proxy services. Any failure retains closed intent.
   This first pending record already contains the verified usage/month/snapshot.
   Each higher observation replaces that retained floor; a later start, readback
   or persistence failure closes using the highest trusted state, never an older
   empty pending record. A baseline at/above the threshold persists blocked.
3. Create the named quota while the fence remains closed. Take a new ens4 snapshot
   **after** the quota starts counting. Add all TX since the baseline snapshot.
4. Update only the quota's limit to `180 GiB - accounted usage`; preserve consumed
   bytes. Traffic after quota creation and before the new snapshot is counted
   twice, intentionally conservative. Traffic during later activation is counted
   by the still-live quota. Neither user-space interval is treated as zero.
5. Verify quota, persist `armed`, remove only the dedicated fence, and restore
   only the two services previously observed running. Failed recovery re-fences.

Linux's named-quota update preserves the consumed counter. Root independently
tested this on us1 nftables 1.1.0 in an isolated network namespace: changing limit
1024 to 2048 retained used=128 and the same handle. Production rules were not
changed. Root then tested generated rule shapes in two isolated namespaces,
both removed in `finally` cleanup:

| Probe | Small test threshold | Observed result |
|---|---|---|
| Established IPv4 TCP 443 stream | 8192 bytes | Received 7240 of 65536 payload bytes |
| Established IPv6 TCP 443 stream | 8192 bytes | Received 7140 of 65536 payload bytes |
| Management port 22 after quota exhaustion | Same exhausted quota | Received all 65536 payload bytes |
| UDP 4444 replies | 4096 bytes | Received 3072 of 8192 payload bytes |
| Unconditional fence | Not applicable | Rendered-shape nft syntax accepted |

Payload and quota byte totals differ because headers count. UDP `sendto` can
return EPERM on this local drop, an expected interruption of the simulated proxy.
Named quota `used` saturates at its limit in readback; it is not an unlimited
post-exhaustion meter. The physical ledger continues accumulating same-boot,
same-month ens4 TX while blocked so remaining webhook/management traffic is not
silently ignored. Crossing a reset/boot/month boundary preserves the last trusted
total and records the new observation, without inventing missing monthly bytes.

Routine ticks never create, replace, update or reset a quota. They check its
fingerprint, limit and monotone consumed value; any missing/corrupt/reset object
closes the proxies. The full table fingerprint ignores only handles, metadata,
and used bytes, so a rule change cannot quietly retain "armed" status.

## State table and recovery

| State | Trigger | Next state / action | Waiting limit |
|---|---|---|---|
| Uninitialized | Read-only command | No writes, no inferred allowance | Operator evidence |
| Uninitialized | `tick --apply` / boot | Blocked, port fence | Operator evidence |
| Uninitialized/blocked | Valid baseline + explicit activation/recovery | Persist blocked, install/verify quota, armed | Bounded commands, fail closed |
| Armed | Healthy same-month sample | Armed; atomic ledger update | 10 seconds after prior check completes |
| Armed | Threshold | Blocked; kernel already cuts response ports, stop proxies | Kernel per packet; timer handles upstream |
| Armed | Counter rollback/boot change/clock rollback/>90s sampling gap | Blocked; never infer missing bytes | Next execution / boot fence |
| Armed | Kernel object/ledger failure | Blocked; preserve failure reason and fence | Next execution |
| Armed | LA month changes | Blocked; no automatic zero/reset | New verified month baseline |
| Blocked | Service restart / repeated tick | Blocked; reassert fence and stop proxies | Every timer check |
| Blocked | Reboot | Boot fence before proxies, stays blocked | Explicit recovery |

`flock` serializes operator and timer writes; temporary file + fsync + replace +
directory fsync preserves either old or new ledger. Blocked intention is written
before external side effects. If the disk write fails, code still attempts the
firewall fence and dedicated service stop, and reports incomplete enforcement.
Directory creation, lock-file opening and lock-acquisition I/O failures also
attempt the external fence and both proxy stops, without reading/writing the
ledger without ownership. This is explicitly best-effort: durable closed intent
cannot be promised while storage/locking is broken, and another already-running
operator may exist. Normal lock contention keeps blocking on `flock`; it never
bypasses the lock or changes state/firewall in parallel. If the OS explicitly
reports contention, the command exits as busy without closure or ledger writes.
After a process crash, a persisted armed state always has an installed quota;
a persisted blocked state is reasserted. Firewall deletion by another privileged
administrator is not preventable here; it is detected at the next check.
An armed ledger with a leftover closed fence or an expected proxy still stopped
is treated as interrupted recovery and moved back to blocked, never reported as
a healthy completed recovery. Recovery remains an explicit operator action.

The boot unit runs before network-pre, Docker and Hysteria. Hysteria requires its
success. Docker has ordering only, to avoid making unrelated webhook availability
depend on a guard failure; gost currently has restart policy `no`. Boot always
installs the port fence and never restores allowance automatically. Enabling the
boot unit/drop-ins is an explicit deployment step, not an action of this repository.

LA transitions are computed with `ZoneInfo`, not fixed UTC offsets: November 2026
starts at `2026-11-01T07:00:00Z`; after DST ends, November 2 local midnight is
`08:00:00Z`. The counter month is not inferred by adding 24-hour days.

## Verification and limits

The final local suite passed 19 tests. Independent review reproduced and then
verified fixes for three recovery bugs: unobserved TX during a block, loss of a
higher verified baseline after failed activation, and lock-entry I/O errors
escaping closure. All six non-apply status/action commands were independently
checked to make no state-directory, firewall or service changes.

`systemd-analyze verify` accepted the staged service units on us1 without
diagnostics. Post-test inspection confirmed no budget tables or test namespaces
remained in production, and Hysteria, gost and both webhook containers were
still running. This is syntax/isolation evidence, not a production boot test.

`python3 tests/test-us1-budget-guard.py` covers unknown/stale/future baselines,
initialization traffic, byte-counter/boot/time rollback, long sample gaps, month
rollover, quota reset/removal/rule changes, threshold from either meter, service
restart, same-month reconciliation floors, service-start failure, disk failure,
atomic-write interruption, protected service targets, and the DST boundary.
Regression cases include an unsampled blocked interval before resume, a failed
first activation followed by a smaller reviewed baseline, and CLI entry failures
where the lock path is a directory or mkdir/flock reports an I/O error. Read-only
commands and lock-contention paths remain free of enforcement side effects.

The small exhaustive coordination model in that test enumerates persistent
intent, fence, quota, crash/stutter, restart and boot transitions. Its invariant
is that a configured lifecycle state has either the closed fence or the kernel
quota. Removing the guard before persisting/opening armed status reaches an
unprotected state; the mutation is detected. This proves only the small model,
not Python, nftables or every administrator/network interaction. Boot ordering
is an explicit assumption; no TLC installation or unrelated framework is added.

Outstanding deployment gates: trusted current-month baseline with no collection
lag gap; actual Google network tier/SKU and billing-account scope; complete
activation lifecycle on the deployed host; boot ordering verification; independent SSH/webhook
continuity and authenticated proxy response checks after any authorized activation.
No test substitutes for those gates, and no amount of passing tests supplies a
missing baseline.
