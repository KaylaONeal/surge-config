#!/usr/bin/env python3
"""Risk-focused fake counters/clock/kernel/service tests; no live firewall writes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('budget', Path(__file__).resolve().parents[1] / 'scripts/us1-budget-guard.py')
budget = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(budget)


def kernel(limit, used=0):
    return {'nftables': [{'quota': {'family': 'inet', 'table': budget.TABLE,
                                  'name': 'monthly_budget', 'bytes': limit,
                                  'used': used, 'inv': True, 'handle': 1}},
                         {'rule': {'chain': 'account', 'expr': ['quota', 'jump-cut']}}]}


class FakeSystem:
    def __init__(self):
        self.actions = []
        self.doc = kernel(budget.LIMIT)
        self.fenced = False
        self.services = {'hysteria': True, 'gost': True}
        self.start_error = False
        self.stop_error = False

    def nft(self, script):
        import re
        self.actions.append(('nft', script))
        if 'create table' in script:
            self.doc = kernel(budget.LIMIT)
        elif 'add quota' in script:
            # Model actual Linux object update; independent netns acceptance
            # still required because a fake cannot prove CLI/kernel semantics.
            self.doc['nftables'][0]['quota']['bytes'] = int(re.search(r'over (\d+) bytes', script).group(1))
        if script == f'destroy table inet {budget.FENCE}\n':
            self.fenced = False

    def table(self, name=budget.TABLE):
        if self.doc is None:
            raise budget.GuardError('kernel missing')
        return deepcopy(self.doc)

    def fence(self):
        self.actions.append(('fence',))
        self.fenced = True

    def has_fence(self):
        return self.fenced

    def stop(self):
        self.actions.append(('stop',))
        self.services = {'hysteria': False, 'gost': False}
        return ['failed stop'] if self.stop_error else []

    def running(self):
        return self.services.copy()

    def start(self, wanted):
        self.actions.append(('start',))
        if self.start_error:
            raise budget.GuardError('start failed')
        self.services = wanted.copy()


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = budget.Ledger(self.temp.name)
        self.system = FakeSystem()
        self.now = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
        self.tx = 1000
        self.boot = 'fake-boot-A'
        self.guard = budget.Guard(self.ledger, self.system, self.sample)

    def sample(self):
        return {'at': self.now.isoformat(), 'tx_bytes': self.tx,
                'boot_id': self.boot, 'interface': 'ens4'}

    def baseline(self, used=100):
        return {'verified': True, 'evidence': 'synthetic fixture, not production approval',
                'month': '2026-11', 'as_of': self.now.isoformat(),
                'boot_id': self.boot, 'interface': 'ens4',
                'tx_bytes_at_as_of': self.tx, 'month_tx_bytes': used}

    def armed(self):
        return self.guard.activate(self.baseline())

    def assert_closed(self, state):
        self.assertEqual('blocked', state['state'])
        self.assertTrue(self.system.fenced)
        self.assertFalse(any(self.system.services.values()))

    def test_unknown_baseline_and_default_command_have_no_activation(self):
        absent = Path(self.temp.name) / 'not-created'
        with patch('builtins.print'):
            self.assertEqual(0, budget.main(['activate', '--state-dir', str(absent)]))
        self.assertFalse(absent.exists())
        data = self.baseline(); data['verified'] = False
        with self.assertRaises(budget.GuardError): self.guard.activate(data)
        self.assertEqual([], self.system.actions)
        self.assert_closed(self.guard.tick(None))

    def test_baseline_freshness_boot_and_counter_validation(self):
        for field, value in [('as_of', (self.now+timedelta(seconds=1)).isoformat()),
                             ('as_of', (self.now-timedelta(hours=2)).isoformat()),
                             ('boot_id', 'other-boot'), ('tx_bytes_at_as_of', 1001),
                             ('month_tx_bytes', -1), ('month_tx_bytes', True),
                             ('evidence', ''), ('month', '2026-10')]:
            with self.subTest(field=field, value=value):
                data=self.baseline(); data[field]=value
                with self.assertRaises(budget.GuardError): self.guard.activate(data)
        self.assertEqual([], self.system.actions)

    def test_initialization_waiting_traffic_is_included(self):
        data = self.baseline(500)
        self.tx += 200  # data flowed while operator reviewed baseline
        original = self.system.nft
        def nft(script):
            original(script)
            if 'create table' in script:
                self.tx += 90  # include state/fence/stop/kernel installation gap
                self.system.doc['nftables'][0]['quota']['used'] = 30
        self.system.nft=nft
        state=self.guard.activate(data)
        self.assertEqual(790, state['iface_month_bytes'])
        self.assertEqual(820, state['used_bytes'])  # overlap deliberately overcounts
        self.assertEqual(budget.LIMIT-790, state['kernel_limit'])

    def test_tick_accounts_host_traffic_without_resetting_kernel(self):
        state=self.armed(); self.system.actions.clear()
        self.tx+=100; self.now+=timedelta(seconds=10)
        self.system.doc['nftables'][0]['quota']['used']=80
        state=self.guard.tick(state)
        self.assertEqual(200,state['used_bytes'])
        self.assertEqual([],self.system.actions)

    def test_interface_quota_reboot_clock_and_month_fail_closed(self):
        for mutation in ('counter','boot','clock','gap','month','missing','rules','quota-reset'):
            with self.subTest(mutation=mutation):
                self.setUp()
                state=self.armed()
                if mutation=='counter': self.tx=999
                if mutation=='boot': self.boot='new-boot'
                if mutation=='clock': self.now-=timedelta(seconds=1)
                if mutation=='gap': self.now+=timedelta(seconds=91)
                if mutation=='month': self.now=datetime(2026,12,1,8,tzinfo=timezone.utc)
                if mutation=='missing': self.system.doc=None
                if mutation=='rules': self.system.doc['nftables'][1]['rule']['expr']=['accept']
                if mutation=='quota-reset': state['kernel_used']=100
                self.assert_closed(self.guard.tick(state))

    def test_threshold_catches_kernel_or_physical_bytes(self):
        for source in ('kernel','physical'):
            with self.subTest(source=source):
                self.setUp(); state=self.armed()
                if source=='kernel': self.system.doc['nftables'][0]['quota']['used']=state['kernel_limit']
                else: self.tx+=budget.LIMIT
                self.assert_closed(self.guard.tick(state))

    def test_block_is_sticky_service_restart_and_month_do_not_reopen(self):
        state=self.guard.block(self.armed(),'operator')
        self.system.services={'hysteria':True,'gost':True}
        self.system.fenced=False
        self.now=datetime(2026,12,1,8,tzinfo=timezone.utc)
        self.assert_closed(self.guard.tick(state))

    def test_crash_after_armed_save_requires_explicit_reconciliation(self):
        for remaining_fence in (True, False):
            with self.subTest(fence=remaining_fence):
                self.setUp(); state=self.armed()
                self.system.fenced=remaining_fence
                self.system.services={'hysteria':False,'gost':False}
                self.assert_closed(self.guard.tick(state))

    def test_nonproxy_physical_traffic_is_still_counted_while_blocked(self):
        state=self.guard.block(self.armed(),'operator')
        self.tx+=4096; self.now+=timedelta(minutes=10)
        state=self.guard.tick(state)
        self.assertEqual(4196,state['iface_month_bytes'])
        self.assert_closed(state)
        self.now=datetime(2026,12,1,8,tzinfo=timezone.utc); self.tx+=100
        state=self.guard.tick(state)
        self.assertEqual('2026-11',state['month'])
        self.assertEqual(4196,state['iface_month_bytes'])
        self.assertEqual(self.tx,state['observed_while_blocked']['tx_bytes'])

    def test_recovery_does_not_reduce_same_month_usage(self):
        state=self.armed(); self.tx+=500
        state=self.guard.tick(state)
        state=self.guard.block(state,'operator')
        state=self.guard.activate(self.baseline(0),state)
        self.assertEqual(600,state['iface_month_bytes'])
        with self.assertRaises(budget.GuardError): self.guard.activate(self.baseline(),state)

    def test_recovery_counts_unsampled_physical_bytes_before_new_baseline(self):
        state=self.guard.block(self.armed(),'operator')
        self.tx+=500  # no blocked tick ran during this interval
        self.now+=timedelta(minutes=5)
        state=self.guard.activate(self.baseline(0),state)
        self.assertEqual(600,state['iface_month_bytes'])
        self.assertGreaterEqual(state['used_bytes'],600)

    def test_failed_first_activation_retains_its_verified_usage_floor(self):
        self.system.start_error=True
        with self.assertRaises(budget.GuardError): self.guard.activate(self.baseline(1000))
        state=self.ledger.load()
        self.assert_closed(state)
        self.assertEqual('2026-11',state['month'])
        self.assertGreaterEqual(state['used_bytes'],1000)
        self.system.start_error=False
        self.tx+=500  # also retain traffic since failed activation, without tick
        state=self.guard.activate(self.baseline(0),state)
        self.assertGreaterEqual(state['used_bytes'],1500)

    def test_cli_lock_io_failures_attempt_closure_without_ledger_write(self):
        state=self.armed()
        before=self.ledger.path.read_bytes()
        (Path(self.temp.name)/'lock').mkdir()
        for command in ('tick','boot','block'):
            with self.subTest(command=command):
                self.system.services={'hysteria':True,'gost':True}
                self.system.fenced=False
                with patch.object(budget,'System',return_value=self.system):
                    with self.assertRaisesRegex(budget.GuardError,'no state written'):
                        budget.main([command,'--apply','--state-dir',self.temp.name])
                self.assertTrue(self.system.fenced)
                self.assertFalse(any(self.system.services.values()))
                self.assertEqual(before,self.ledger.path.read_bytes())
        self.system.actions.clear()
        with patch.object(budget,'System',return_value=self.system), patch('builtins.print'):
            budget.main(['tick','--state-dir',self.temp.name])
        self.assertEqual([],self.system.actions)

    def test_lock_mkdir_flock_io_errors_close_but_contention_does_not(self):
        for target,error,closed in ((budget.Path,'mkdir',True),
                                    (budget.fcntl,'flock',True),
                                    (budget.fcntl,'flock',False)):
            with self.subTest(operation=error,closed=closed):
                self.system.actions.clear(); self.system.fenced=False
                self.system.services={'hysteria':True,'gost':True}
                failure=OSError('storage unavailable') if closed else BlockingIOError(11,'busy')
                with patch.object(target,error,side_effect=failure), patch.object(budget,'System',return_value=self.system):
                    with self.assertRaises(budget.GuardError):
                        budget.main(['tick','--apply','--state-dir',self.temp.name])
                self.assertEqual(closed,self.system.fenced)
                if not closed:
                    self.assertEqual([],self.system.actions)
                    self.assertTrue(all(self.system.services.values()))
        # EAGAIN from storage setup is not evidence that another writer owns
        # flock: only flock contention takes the no-enforcement busy path.
        self.system.fenced=False
        with patch.object(budget.Path,'mkdir',side_effect=BlockingIOError(11,'storage busy')), patch.object(budget,'System',return_value=self.system):
            with self.assertRaises(budget.GuardError):
                budget.main(['tick','--apply','--state-dir',self.temp.name])
        self.assertTrue(self.system.fenced)

    def test_start_failure_and_ledger_write_failure_still_fence(self):
        self.system.start_error=True
        with self.assertRaises(budget.GuardError): self.armed()
        self.assert_closed(self.ledger.load())
        with patch.object(self.ledger,'save',side_effect=OSError('disk full')):
            with self.assertRaises(budget.GuardError): self.guard.block(None,'disk-full')
        self.assertTrue(self.system.fenced)
        self.assertFalse(any(self.system.services.values()))

    def test_atomic_write_retains_previous_state_on_replace_failure(self):
        before={'schema':1,'state':'blocked','reason':'old'}
        self.ledger.save(before)
        with patch.object(budget.os,'replace',side_effect=OSError('crash before rename')):
            with self.assertRaises(OSError): self.ledger.save(dict(before,reason='new'))
        self.assertEqual(before,self.ledger.load())
        self.assertEqual(0o600,self.ledger.path.stat().st_mode & 0o777)

    def test_dst_month_boundary_is_not_fixed_offset(self):
        self.assertEqual('2026-10',budget.month(budget.stamp('2026-11-01T06:59:59Z')))
        self.assertEqual('2026-11',budget.month(budget.stamp('2026-11-01T07:00:00Z')))
        self.assertEqual('2026-11-01T07:00:00+00:00',budget.month_start(budget.stamp('2026-11-02T08:00:00Z')))
        self.assertEqual(0,budget.stamp('2026-11-02T08:00:00Z').astimezone(budget.TZ).hour)

    def test_runner_whitelists_only_proxy_targets(self):
        calls=[]
        def runner(args,**kwargs):
            calls.append(args)
            return type('Result',(),{'returncode':0,'stdout':'{}'})()
        system=budget.System(runner)
        system.stop()
        self.assertEqual([['systemctl','stop','hysteria-server.service'],['docker','stop','--time','5','gost']],calls)
        rules=budget.quota_rules()+budget.fence_rules()
        self.assertNotIn('flush ruleset',rules)
        self.assertNotIn('uid',rules)
        self.assertIn('hook postrouting',rules)
        self.assertIn('tcp sport 443 drop',rules)
        self.assertNotIn('ct state established accept',rules)


class SmallModelTests(unittest.TestCase):
    def test_fenced_intent_survives_every_transaction_crash_prefix(self):
        # Small exhaustive coordination model, not a proof of Python/kernel.
        # Each reachable state can crash/stutter or see a service restart;
        # neither clears the kernel rules. Boot ordering is an explicit axiom.
        def explore(remove_guard=False):
            seen={('blocked',True,False)}; pending=list(seen)
            while pending:
                phase,fenced,quota=pending.pop()
                following={('blocked',True,False),  # reboot with boot fence
                           (phase,fenced,quota),    # crash/restart/stutter
                           ('blocked',fenced,quota), # durable closed intention
                           (phase,True,quota)}     # install fence
                if fenced: following.add((phase,True,True)) # quota install
                if fenced and (quota or remove_guard): following.add(('armed',True,quota))
                if phase=='armed': following.add(('armed',False,quota))
                for item in following-seen:
                    seen.add(item); pending.append(item)
            return seen
        good=explore()
        self.assertTrue(all(fenced or quota for _,fenced,quota in good))
        self.assertTrue(all(phase in budget.STATES for phase,_,_ in good))
        bad=explore(remove_guard=True)
        self.assertIn(('armed',False,False),bad)
        self.assertGreater(len(bad),len(good))


if __name__=='__main__': unittest.main()
