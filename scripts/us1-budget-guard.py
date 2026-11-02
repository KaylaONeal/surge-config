#!/usr/bin/env python3
"""Staged us1 proxy circuit breaker. No changes without explicit --apply.

The kernel cuts proxy RESPONSE ports. This is not a host/account billing cap.
"""
import argparse
import contextlib
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Los_Angeles')
LIMIT = 180 * 1024**3
TABLE = 'us1_budget_guard'
FENCE = 'us1_budget_block'
STATES = {'armed', 'blocked'}
MAX_BASELINE_AGE = 3600


class GuardError(Exception):
    pass


class LockBusyError(GuardError):
    pass


def stamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise GuardError('timestamp must include timezone')
    return parsed.astimezone(timezone.utc)


def month(now):
    return now.astimezone(TZ).strftime('%Y-%m')


def month_start(now):
    return now.astimezone(TZ).replace(day=1, hour=0, minute=0, second=0,
                                     microsecond=0).astimezone(timezone.utc).isoformat()


def integer(value):
    if type(value) is not int or not 0 <= value < 2**63:
        raise GuardError('invalid nonnegative integer counter')
    return value


def snapshot():
    return {'at': datetime.now(timezone.utc).isoformat(),
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'tx_bytes': int(Path('/sys/class/net/ens4/statistics/tx_bytes').read_text()),
            'interface': 'ens4'}


def baseline_usage(data, snap):
    now, at = stamp(snap['at']), stamp(data['as_of'])
    if data.get('verified') is not True or not data.get('evidence'):
        raise GuardError('baseline requires verified=true and evidence reference')
    if data.get('interface') != 'ens4' or data.get('boot_id') != snap['boot_id']:
        raise GuardError('baseline interface/boot does not match current snapshot')
    if data.get('month') != month(now) or month(at) != month(now):
        raise GuardError('baseline must cover the current Los Angeles month')
    if not 0 <= (now-at).total_seconds() <= MAX_BASELINE_AGE:
        raise GuardError('baseline is future-dated or older than one hour')
    before, current = integer(data['tx_bytes_at_as_of']), integer(snap['tx_bytes'])
    if current < before:
        raise GuardError('interface counter rolled back since baseline')
    return integer(data['month_tx_bytes']) + current - before


def fingerprint(document):
    # Handles change on reload; consumed is the sole expected mutable object.
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()
                    if k not in {'handle', 'used', 'metainfo'}}
        if isinstance(value, list):
            return [clean(v) for v in value if not (isinstance(v, dict) and 'metainfo' in v)]
        return value
    return hashlib.sha256(json.dumps(clean(document), sort_keys=True).encode()).hexdigest()


def quota(document):
    found = [item['quota'] for item in document.get('nftables', [])
             if 'quota' in item and item['quota'].get('name') == 'monthly_budget']
    if len(found) != 1:
        raise GuardError('missing/duplicate kernel quota')
    obj = found[0]
    if obj.get('inv') is not True:
        raise GuardError('kernel quota must match over threshold')
    return integer(obj['bytes']), integer(obj.get('used', 0))


def quota_rules(limit=LIMIT):
    integer(limit)
    return f'''create table inet {TABLE}
add quota inet {TABLE} monthly_budget {{ over {limit} bytes; }}
add chain inet {TABLE} cut_proxy
add rule inet {TABLE} cut_proxy tcp sport 443 drop
add rule inet {TABLE} cut_proxy udp sport 4444 drop
add chain inet {TABLE} account {{ type filter hook postrouting priority 110; policy accept; }}
add rule inet {TABLE} account oifname "ens4" quota name "monthly_budget" jump cut_proxy
'''


def fence_rules():
    # Atomic replacement of only our own table; no flush ruleset/Docker edits.
    return f'''destroy table inet {FENCE}
table inet {FENCE} {{
 chain inbound {{ type filter hook input priority -10; policy accept;
  tcp dport 443 drop
  udp dport 4444 drop
 }}
 chain outbound {{ type filter hook output priority -10; policy accept;
  tcp sport 443 drop
  udp sport 4444 drop
 }}
}}
'''


class System:
    def __init__(self, runner=subprocess.run):
        self.runner = runner

    def run(self, args, data=None, allow_failure=False):
        result = self.runner(args, input=data, capture_output=True, text=True, timeout=15)
        if result.returncode and not allow_failure:
            raise GuardError('command failed: ' + ' '.join(args[:4]))
        return result

    def nft(self, script):
        self.run(['nft', '-f', '-'], script)

    def table(self, name=TABLE):
        result = self.run(['nft', '-j', 'list', 'table', 'inet', name], allow_failure=True)
        if result.returncode:
            raise GuardError('kernel table missing or unreadable: ' + name)
        return json.loads(result.stdout)

    def fence(self):
        self.nft(fence_rules())
        self.table(FENCE)

    def has_fence(self):
        document = json.loads(self.run(['nft', '-j', 'list', 'tables']).stdout)
        return any(item.get('table', {}).get('family') == 'inet'
                   and item['table'].get('name') == FENCE
                   for item in document.get('nftables', []))

    def stop(self):
        errors = []
        for args in (['systemctl', 'stop', 'hysteria-server.service'],
                     ['docker', 'stop', '--time', '5', 'gost']):
            try:
                self.run(args)
            except (GuardError, OSError, subprocess.TimeoutExpired):
                errors.append(' '.join(args[:3]))
        return errors

    def running(self):
        hysteria = self.run(['systemctl', 'is-active', 'hysteria-server.service'], allow_failure=True)
        gost = self.run(['docker', 'inspect', '--format', '{{.State.Running}}', 'gost'])
        return {'hysteria': hysteria.returncode == 0, 'gost': gost.stdout.strip() == 'true'}

    def start(self, wanted):
        if wanted.get('hysteria'):
            self.run(['systemctl', 'start', 'hysteria-server.service'])
        if wanted.get('gost'):
            self.run(['docker', 'start', 'gost'])
        actual = self.running()
        if any(wanted.get(name) and not actual[name] for name in actual):
            raise GuardError('proxy recovery readback failed')


class Ledger:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / 'state.json'

    @contextlib.contextmanager
    def locked(self, on_acquire_error=None):
        lock = None
        acquiring_flock = False
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock = open(self.directory / 'lock', 'a')
            os.chmod(lock.name, 0o600)
            # Normal contention waits; it must never bypass serialization.
            acquiring_flock = True
            fcntl.flock(lock, fcntl.LOCK_EX)
        except BlockingIOError as error:
            if lock:
                lock.close()
            if not acquiring_flock:
                if on_acquire_error:
                    on_acquire_error()
                raise GuardError('lock setup I/O failure') from error
            raise LockBusyError('lock busy; no ledger or firewall mutation') from error
        except OSError as error:
            if lock:
                lock.close()
            if on_acquire_error:
                on_acquire_error()
            raise GuardError('lock acquisition I/O failure') from error
        try:
            yield
        finally:
            lock.close()

    def load(self):
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text())
        if data.get('schema') != 1 or data.get('state') not in STATES:
            raise GuardError('invalid persisted ledger schema/state')
        return data

    def save(self, data):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix='.state-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            dfd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        finally:
            if os.path.exists(name):
                os.unlink(name)


class Guard:
    def __init__(self, ledger, system, sample=snapshot):
        self.ledger, self.system, self.sample = ledger, system, sample

    def lock_failure(self):
        # Without a lock, do not read or write the ledger, reset a quota, or
        # reopen anything. Best-effort external closure cannot promise durable
        # intent while storage/locking is broken; report that explicitly.
        failures = []
        try:
            self.system.fence()
        except Exception:
            failures.append('nft')
        try:
            failures.extend(self.system.stop())
        except Exception:
            failures.append('proxy-stop')
        raise GuardError('lock acquisition I/O failure; no state written; '
                         'best-effort proxy closure attempted; failures=' + str(failures))

    @staticmethod
    def usage_floor(state, snap, reviewed_usage):
        if not state or state.get('month') != month(stamp(snap['at'])):
            return reviewed_usage
        physical_floor = state.get('iface_month_bytes', 0)
        last = state.get('last')
        if (last and snap['boot_id'] == last['boot_id']
                and snap['tx_bytes'] >= last['tx_bytes']
                and stamp(snap['at']) >= stamp(last['at'])):
            physical_floor += snap['tx_bytes'] - last['tx_bytes']
        return max(reviewed_usage, physical_floor, state.get('used_bytes', 0))

    def block(self, state, reason, stop=True):
        state = dict(state or {'schema': 1})
        state.update(state='blocked', reason=reason)
        # Persist intention first. Even a persistence failure must still fence.
        save_error = None
        try:
            self.ledger.save(state)
        except Exception as error:
            save_error = error
        fence_error = None
        try:
            self.system.fence()
        except Exception as error:
            fence_error = error
        errors = self.system.stop() if stop else []
        if save_error or fence_error or errors:
            raise GuardError('blocked intent; enforcement/persistence incomplete: '
                             f'ledger={bool(save_error)} nft={bool(fence_error)} stop={errors}')
        return state

    def activate(self, baseline, state=None):
        initial = self.sample()
        initial_usage = baseline_usage(baseline, initial)  # before any mutation
        if state and state.get('state') == 'armed':
            raise GuardError('already armed; never reset a live quota')
        initial_usage = self.usage_floor(state, initial, initial_usage)
        wanted = state.get('restore_services') if state else None
        if wanted is None:
            wanted = self.system.running()
        pending = dict(state or {'schema': 1})
        pending.update(restore_services=wanted, month=month(stamp(initial['at'])),
                       last=initial, iface_month_bytes=initial_usage,
                       used_bytes=initial_usage)
        pending = self.block(pending, 'activation_pending')
        if initial_usage >= LIMIT:
            return self.block(pending, 'verified_baseline_exceeds_threshold')
        try:
            # Explicit recovery only: closed fence + stopped proxies protect
            # replacement. Routine ticks NEVER create/reset/update this quota.
            self.system.nft(f'destroy table inet {TABLE}\n' + quota_rules())
            snap = self.sample()  # quota already counts before this checkpoint
            used = self.usage_floor(pending, snap, baseline_usage(baseline, snap))
            pending.update(last=snap, iface_month_bytes=used, used_bytes=used)
            if used >= LIMIT:
                raise GuardError('threshold crossed during activation')
            remaining = LIMIT - used
            # Kernel obj_update retains consumed; netns acceptance is required.
            self.system.nft(f'add quota inet {TABLE} monthly_budget {{ over {remaining} bytes; }}\n')
            kernel = self.system.table()
            limit, consumed = quota(kernel)
            pending['used_bytes'] = used + consumed
            if limit != remaining or consumed >= remaining:
                raise GuardError('quota limit/readback exhausted or inconsistent')
            new = {'schema': 1, 'state': 'armed', 'reason': 'verified_activation',
                   'month': month(stamp(snap['at'])), 'last': snap,
                   'iface_month_bytes': used, 'used_bytes': used + consumed,
                   'kernel_anchor_bytes': used, 'kernel_limit': remaining,
                   'kernel_used': consumed, 'fingerprint': fingerprint(kernel),
                   'baseline': baseline, 'restore_services': wanted}
            pending = new  # any later failure preserves this higher trusted floor
            self.ledger.save(new)
            self.system.nft(f'destroy table inet {FENCE}\n')
            self.system.start(wanted)
            return new
        except Exception:
            self.block(pending, 'activation_or_recovery_failed')
            raise

    def tick(self, state):
        if state is None:
            return self.block(None, 'unknown_month_baseline')
        if state['state'] == 'blocked':
            updated = dict(state)
            try:
                snap = self.sample()
                updated['observed_while_blocked'] = snap
                last = state.get('last')
                if (last and state.get('month') == month(stamp(snap['at']))
                        and snap['boot_id'] == last['boot_id']
                        and snap['tx_bytes'] >= last['tx_bytes']
                        and stamp(snap['at']) >= stamp(last['at'])):
                    updated['iface_month_bytes'] += snap['tx_bytes'] - last['tx_bytes']
                    updated['used_bytes'] = max(updated['used_bytes'], updated['iface_month_bytes'])
                    updated['last'] = snap
                # Across a boot/reset/month boundary we cannot invent the gap
                # or divide bytes across months. Keep the last trusted total.
            except Exception as error:
                updated['observation_error'] = type(error).__name__
            return self.block(updated, state.get('reason', 'blocked'))
        try:
            snap = self.sample()
            last = state['last']
            elapsed = (stamp(snap['at']) - stamp(last['at'])).total_seconds()
            if month(stamp(snap['at'])) != state['month']:
                raise GuardError('new_month_requires_verified_baseline')
            if snap['boot_id'] != last['boot_id'] or snap['tx_bytes'] < last['tx_bytes']:
                raise GuardError('boot_or_interface_counter_reset')
            if not 0 <= elapsed <= 90:
                raise GuardError('clock_rollback_or_sampling_gap')
            if self.system.has_fence():
                raise GuardError('interrupted_activation_fence_remains')
            running = self.system.running()
            if any(wanted and not running[name] for name, wanted
                   in state.get('restore_services', {}).items()):
                raise GuardError('expected_proxy_service_not_running')
            kernel = self.system.table()
            limit, consumed = quota(kernel)
            if fingerprint(kernel) != state['fingerprint'] or limit != state['kernel_limit']:
                raise GuardError('kernel_rules_changed')
            if consumed < state['kernel_used']:
                raise GuardError('kernel_quota_counter_reset')
            updated = dict(state)
            updated['iface_month_bytes'] += snap['tx_bytes'] - last['tx_bytes']
            updated.update(last=snap, kernel_used=consumed,
                           used_bytes=max(updated['iface_month_bytes'], state['kernel_anchor_bytes'] + consumed))
            if updated['used_bytes'] >= LIMIT or consumed >= limit:
                return self.block(updated, 'threshold_reached')
            self.ledger.save(updated)
            return updated
        except Exception as error:
            return self.block(state, 'observation_failed:' + type(error).__name__ + ':' + str(error)[:100])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['snapshot', 'status', 'activate', 'resume', 'tick', 'block', 'boot', 'render-quota', 'render-fence'])
    parser.add_argument('--state-dir', default='/var/lib/us1-budget')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if args.command.startswith('render-'):
        print(quota_rules() if args.command == 'render-quota' else fence_rules(), end='')
        return 0
    if args.command == 'snapshot':
        data = snapshot()
        data.update(month=month(stamp(data['at'])), month_start=month_start(stamp(data['at'])))
        print(json.dumps(data))
        return 0
    ledger, system = Ledger(args.state_dir), System()
    if not args.apply:
        # No lock/state directory creation and no service/nft writes.
        state = ledger.load()
        print(json.dumps({'apply': False, 'requested': args.command, 'state': state,
                          'activation_requires': 'verified baseline plus --apply'}))
        return 0
    if args.command == 'status':
        raise GuardError('status is read-only; omit --apply')
    guard = Guard(ledger, system)
    with ledger.locked(on_acquire_error=guard.lock_failure):
        try:
            state = ledger.load()
        except Exception:
            guard.block(None, 'ledger_unreadable')
            raise GuardError('ledger unreadable; proxies fenced, baseline reconciliation required')
        if args.command in {'activate', 'resume'}:
            if args.baseline is None:
                raise GuardError('--baseline is required; zero is never assumed')
            if args.command == 'resume' and not state:
                raise GuardError('resume requires existing blocked ledger')
            result = guard.activate(json.loads(args.baseline.read_text()), state)
        elif args.command == 'boot':
            result = guard.block(state, 'boot_requires_reconciliation', stop=False)
        elif args.command == 'block':
            result = guard.block(state, 'operator_block')
        else:
            result = guard.tick(state)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['state'] == 'armed' or args.command in {'boot', 'block'} else 3


if __name__ == '__main__':
    try:
        sys.exit(main())
    except LockBusyError as error:
        print(json.dumps({'error': str(error), 'status': 'lock_busy'}), file=sys.stderr)
        sys.exit(75)
    except (GuardError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error), 'status': 'not_armed_or_needs_review'}), file=sys.stderr)
        sys.exit(2)
