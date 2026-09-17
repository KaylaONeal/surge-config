#!/usr/bin/env python3
"""Check first-match routing with local rules, without remote-provider availability."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREFIX = 'https://raw.githubusercontent.com/KaylaONeal/surge-config/main/'


def check(profile):
    sections = {}
    section = None
    for raw in profile.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('['):
            section = line
            sections[section] = []
        else:
            sections[section].append(line)
    policies = {'DIRECT', 'REJECT'}
    groups = {}
    for section in ('[Proxy]', '[Proxy Group]'):
        for line in sections[section]:
            name, value = map(str.strip, line.split('=', 1))
            assert name not in policies, (profile.name, 'duplicate policy', name)
            policies.add(name)
            if section == '[Proxy Group]':
                groups[name] = [p.strip() for p in value.split(',')]
    for name, parts in groups.items():
        members = [p for p in parts[1:] if '=' not in p]
        assert members and all(p in policies for p in members), (name, members)

    def visit(name, parents):
        assert name not in parents, ('group cycle', parents, name)
        for member in groups.get(name, [])[1:]:
            if member in groups:
                visit(member, parents + [name])
    for name in groups:
        visit(name, [])
    assert groups['YouTube'] == ['select', 'US Auto', 'CF US Auto', 'CF Edge Auto', 'KR Auto', 'CF SG Auto']
    for region in ('SG', 'US'):
        members = [p for p in groups[f'CF {region} Auto'][1:] if '=' not in p]
        assert all(p.endswith(' ' + region) for p in members), members

    for exchange in ('Bybit', 'Binance'):
        assert groups[exchange] == ['select', 'KR HTTPS 01'], (profile.name, exchange, 'exit must stay on verified KR node')

    rules = []
    original = sections['[Rule]']
    for line in original:
        fields = [p.strip() for p in line.split(',')]
        policy = fields[1] if fields[0] == 'FINAL' else fields[2]
        assert policy in policies, (profile.name, 'undefined policy', line)
        if fields[0] == 'RULE-SET' and fields[1].startswith(PREFIX):
            local = ROOT / fields[1][len(PREFIX):]
            assert local.is_file(), local
            for item in local.read_text().splitlines():
                if item and not item.startswith('#'):
                    rules.append(item.split(',')[:2] + [policy])
        else:
            rules.append(fields)

    def route(host):
        for fields in rules:
            kind, value = fields[:2]
            if kind == 'FINAL':
                return value
            if (kind == 'DOMAIN' and host == value or
                kind == 'DOMAIN-SUFFIX' and (host == value or host.endswith('.' + value)) or
                kind == 'DOMAIN-KEYWORD' and value in host):
                return fields[2]

    google_ai_hosts = ('gemini.google.com', 'generativelanguage.googleapis.com',
                       'cloudcode-pa.googleapis.com', 'daily-cloudcode-pa.googleapis.com',
                       'autopush-cloudcode-pa.sandbox.googleapis.com',
                       'preprod-daily-cloudcode-pa.sandbox.googleapis.com',
                       'antigravity.google', 'antigravity.goog', 'antigravity-unleash.goog')
    cases = {
        **dict.fromkeys(google_ai_hosts, 'AI'),
        'www.youtube.com': 'YouTube', 'youtu.be': 'YouTube',
        'www.youtube-nocookie.com': 'YouTube', 'i.ytimg.com': 'YouTube',
        'rr1.googlevideo.com': 'YouTube', 'yt3.ggpht.com': 'YouTube',
        'youtubei.googleapis.com': 'YouTube', 'youtube.googleapis.com': 'YouTube',
        'youtubeembeddedplayer.googleapis.com': 'YouTube',
        'video.google.com': 'YouTube', 'youtube-ui.l.google.com': 'YouTube',
        'api.backpack.exchange': 'CF Edge Auto', 'ws.backpack.exchange': 'CF Edge Auto',
        'backpack.app': 'CF Edge Auto', 'api.binance.com': 'Binance',
        'www.okx.com': 'CF Edge Auto', 'app.hyperliquid.xyz': 'CF Edge Auto',
        'api.jup.ag': 'CF Edge Auto', 'www.coingecko.com': 'CF Edge Auto',
        'www.binance.com': 'Binance', 'fapi.binance.com': 'Binance',
        'dapi.binance.com': 'Binance', 'stream.binance.com': 'Binance',
        'data.binance.vision': 'Binance', 'public.bnbstatic.com': 'Binance',
        'notbinance.com': 'DIRECT', 'binance.com.example': 'DIRECT',
        'www.bybit.com': 'Bybit', 'api.bybit.com': 'Bybit',
        'stream.bybit.com': 'Bybit', 'api2.bybit.com': 'Bybit',
        'www.bybitglobal.com': 'Bybit', 'www.bybit.global': 'Bybit',
        'www.bytick.com': 'Bybit', 'www.by-tick.com': 'Bybit',
        'fh-static.bycsi.com': 'Bybit',
        'notbybit.com': 'DIRECT', 'bybit.com.example': 'DIRECT',
        'www.google.com': 'CF Edge Auto', 'maps.googleapis.com': 'CF Edge Auto',
        'chatgpt.com': 'AI', 'claude.ai': 'AI',
        'www.taobao.com': 'DIRECT', 'kdb.corp.kuaishou.com': 'DIRECT',
        'adlp.corp.kuaishou.com': 'REJECT', 'unknown.example': 'DIRECT',
        'notbackpack.exchange': 'DIRECT', 'backpack.exchange.example': 'DIRECT',
    }
    for host, expected in cases.items():
        assert route(host) == expected, (profile.name, host, route(host), expected)
    for host in google_ai_hosts:
        rule = f'DOMAIN-SUFFIX,{host},AI'
        assert original.count(rule) == 1, (profile.name, 'missing/duplicate inline AI rule', host)
        assert all(original.index(rule) < i for i, line in enumerate(original)
                   if any(provider in line for provider in ('DOMAIN-SUFFIX,google.com,',
                          'DOMAIN-SUFFIX,googleapis.com,', 'rules/proxy-extra.list',
                          'ChinaMax_Domain.list', '/ruleset/direct.txt', '/Google/Google.list'))), (profile.name, 'AI rule shadowed', host)
    # Geo-sensitive domains must be inline and precede every broad provider,
    # including an old cached proxy-extra list that still routes Bybit to CF.
    bybit_hosts = ('bybit.com', 'bybitglobal.com', 'bybit.global', 'bytick.com', 'by-tick.com', 'bycsi.com')
    broad = ('rules/proxy-extra.list', 'ChinaMax_Domain.list', '/ruleset/direct.txt',
             '/ruleset/proxy.txt', 'Global_Domain.list', '/Global/Global.list')
    exchange_hosts = dict.fromkeys(bybit_hosts, 'Bybit')
    exchange_hosts.update(dict.fromkeys(('binance.com', 'binance.vision', 'bnbstatic.com'), 'Binance'))
    for host, policy in exchange_hosts.items():
        rule = f'DOMAIN-SUFFIX,{host},{policy}'
        assert original.count(rule) == 1, (profile.name, 'missing/duplicate inline exchange rule', host)
        assert all(original.index(rule) < i for i, line in enumerate(original)
                   if any(provider in line for provider in broad)), (profile.name, 'Exchange rule shadowed', host)
    youtube = next(i for i, line in enumerate(original) if '/YouTube/YouTube.list,' in line)
    assert sum('/YouTube/YouTube.list,' in line for line in original) == 1
    assert original[youtube].endswith(',YouTube')
    for i, line in enumerate(original):
        if any(s in line for s in ('DOMAIN-SUFFIX,google.com,', 'DOMAIN-SUFFIX,googleapis.com,',
                                    'ChinaMax_Domain.list', '/ruleset/direct.txt', '/Google/Google.list')):
            assert youtube < i, ('YouTube shadowed by broad rule', line)
    print(f'OK {profile.name}: policy references, cycles, region pools, rule priority, {len(cases)} routes')


for name in ('surge.conf', 'shadowrocket.conf'):
    check(ROOT / name)
