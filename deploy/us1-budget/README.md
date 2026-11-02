# Staged us1 proxy circuit breaker

Not installed or activated by this repository. A verified current-month baseline
is required; the example deliberately cannot activate. A network tier, an
enabled Ops Agent, a passing test, and a zero bill do not establish that baseline.

Read `docs/reviews/2026-11-01-us1-budget-design.md` before activation. Review and
copy the script to `/opt/us1-budget/us1-budget-guard.py` (root-owned, mode 0755),
units to `/etc/systemd/system/`, and the named drop-ins to
`hysteria-server.service.d/budget.conf` and `docker.service.d/budget.conf`.
These files contain no install script and do not enable any units automatically.

Before enabling, check shared `infra jobs`/`infra ports`, install the boot unit
and drop-ins together, validate units with `systemd-analyze verify`, and confirm
the actual service/container names remain the same. The boot fence must run
before Hysteria and Docker; it deliberately never auto-opens after reboot.
The existing `gost` restart policy is `no`; do not change it to bypass recovery.
Do not restart Docker to install the ordering drop-in.

Read-only commands:

```sh
python3 /opt/us1-budget/us1-budget-guard.py snapshot
python3 /opt/us1-budget/us1-budget-guard.py status
python3 /opt/us1-budget/us1-budget-guard.py render-quota
python3 /opt/us1-budget/us1-budget-guard.py render-fence
```

After the operator has verified and approved a baseline, activation requires
an explicit command. Enabling/start of boot protection briefly closes the
proxy paths; webhook and SSH are preserved. Use an administrative SSH connection
independent of the proxied routes, then verify the boot fence before activation:

```sh
systemctl daemon-reload
systemctl enable --now us1-budget-boot.service
python3 /opt/us1-budget/us1-budget-guard.py activate --baseline /root/private-baseline.json --apply
systemctl enable --now us1-budget-check.timer
```

Since the boot fence precedes first activation, it does not stop already-running
proxies; activation records and restores their current running state. Once
armed, each check only reads the existing quota and writes the ledger: no quota
reset/recreation. Do not call `nft reset quota` or reload this table externally.

Recovery after a block/reboot/month transition requires a new verified baseline
covering the intervening traffic, then explicit `resume --baseline ... --apply`.
Reconciliation never lowers the retained same-month usage. Only services captured
as running before the first block are restored; missing/corrupt restore state
does not authorize starting an unrelated/stopped service. Verify proxy service
state and destination responses afterward. Recovery failure restores the fence.

All ledger operations use `/var/lib/us1-budget`, exclusive flock, atomic rename
and fsync. Preserve the directory and its records. A malformed ledger or missing
kernel object during `tick --apply` closes the proxy paths instead of creating
a fresh allowance. A `blocked` check exits 3; enforcement failures exit 2.

Rollback is an operator decision: first leave the proxy fence installed, disable
the timer, reconcile actual usage, and only then remove the two dedicated nft
tables if reopening is authorized. Never flush the full nft ruleset and never
stop Docker globally. No automated rollback opens the ports.
