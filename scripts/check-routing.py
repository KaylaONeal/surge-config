#!/usr/bin/env python3
"""Check first-match routing with local rules, without remote-provider availability."""
from pathlib import Path
from ipaddress import ip_address, ip_network

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
        if parts[0] == 'smart':
            assert all(p not in groups and p not in {'DIRECT', 'REJECT'} for p in members), (name, 'Smart requires leaf proxies')

    def visit(name, parents):
        assert name not in parents, ('group cycle', parents, name)
        for member in groups.get(name, [])[1:]:
            if member in groups:
                visit(member, parents + [name])
    for name in groups:
        visit(name, [])
    pinned = {'US HY2 02', 'US HY2 01', 'US HTTPS 01'}

    def exits(name):
        if name not in groups:
            return {name}
        return set().union(*(exits(p) for p in groups[name][1:] if '=' not in p))

    for name in ('AI', 'US Only', 'Download'):
        assert exits(name) == pinned, (profile.name, name, 'must retain only fixed-us1 transports')
    assert groups['US Only'][0] == ('smart' if profile.name == 'surge.conf' else 'url-test')
    assert groups['AI'][:2] == ['select', 'US Only']
    assert groups['Download'][:2] == ['select', 'US HY2 02']
    assert groups['YouTube'] == ['select', 'US Auto', 'CF US Auto', 'CF Edge Auto', 'KR Auto', 'CF SG Auto']
    cf_leaves = {line.split('=', 1)[0].strip() for line in sections['[Proxy]']
                 if line.startswith('CF Edge ')}
    assert len(cf_leaves) == 7, (profile.name, 'must retain all seven CF ingress nodes')
    assert groups['CF Edge Auto'][0] == ('smart' if profile.name == 'surge.conf' else 'url-test')
    assert exits('CF Edge Auto') == cf_leaves, (profile.name, 'CF Auto must retry only within CF')
    assert groups['Futu'][:3] == ['fallback', 'CF Edge Auto', 'DIRECT']
    assert exits('Futu') == cf_leaves | {'DIRECT'}
    assert 'interval = 60' in groups['Futu']
    if profile.name == 'surge.conf':
        assert 'evaluate-before-use = false' in groups['CF Edge Auto']
        assert not any(p.startswith(('interval', 'tolerance')) for p in groups['CF Edge Auto'][1:]), \
            'Smart uses its own test schedule, not url-test interval/tolerance'
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

    def route(host, process=None):
        try:
            address = ip_address(host)
        except ValueError:
            address = None
        for fields in rules:
            kind, value = fields[:2]
            if kind == 'FINAL':
                return value
            if kind == 'PROCESS-NAME' and process == value:
                return fields[2]
            if kind in ('IP-CIDR', 'IP-CIDR6') and address is not None and address in ip_network(value):
                return fields[2]
            if (kind == 'DOMAIN' and host == value or
                kind == 'DOMAIN-SUFFIX' and (host == value or host.endswith('.' + value)) or
                kind == 'DOMAIN-KEYWORD' and value in host):
                return fields[2]

    google_ai_hosts = ('gemini.google.com', 'generativelanguage.googleapis.com',
                       'cloudcode-pa.googleapis.com', 'daily-cloudcode-pa.googleapis.com',
                       'autopush-cloudcode-pa.sandbox.googleapis.com',
                       'preprod-daily-cloudcode-pa.sandbox.googleapis.com',
                       'antigravity.google', 'antigravity.goog', 'antigravity-unleash.goog')
    download_hosts = ('persistent.oaistatic.com', 'releases.openai.com',
                      'downloads.claude.ai', 'registry.npmjs.org',
                      'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
                      'github-releases.githubusercontent.com')
    cases = {
        **dict.fromkeys(('ntfyx.me', 'staging.ntfyx.me', 'api.ntfyx.me',
                        'api.staging.ntfyx.me', 'app.ntfyx.me', 'app.staging.ntfyx.me',
                        'gateway.ntfyx.me', 'gateway.staging.ntfyx.me', 'status.ntfyx.me',
                        'quant.fallback.page', 'share.fallback.page',
                        'arb.fallback.page', 'discord.fallback.page',
                        'config.fallback.page'), 'US Only'),
        'notntfyx.me': 'DIRECT', 'ntfyx.me.example': 'DIRECT',
        'quant.fallback.page.example': 'DIRECT', 'unrelated.fallback.page': 'DIRECT',
        **dict.fromkeys(google_ai_hosts, 'AI'),
        **dict.fromkeys(download_hosts, 'Download'),
        'muse.ai': 'AI', 'auth.muse.ai': 'AI', 'api.muse.ai': 'AI',
        'www.facebook.com': 'AI', 'www.instagram.com': 'AI', 'auth.meta.com': 'AI',
        'notmuse.ai': 'DIRECT', 'muse.ai.example': 'DIRECT',
        'api.openai.com': 'AI', 'api.anthropic.com': 'AI',
        'cdn.oaistatic.com': 'AI', 'notreleases.openai.com': 'AI',
        'storage.googleapis.com': 'CF Edge Auto',
        'releases.openai.com.example': 'DIRECT',
        'sub.registry.npmjs.org': 'DIRECT',
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
        'api.cloudflare.com': 'DIRECT',
        'quant-kclaw.pages.dev': 'DIRECT',
        **dict.fromkeys(('trade.futunn.com', 'openapi.futunn.com', 'api5.futunn.com',
                        'q.futunn.com', 'collect.futunn.com', 'fututrade.com',
                        'api.fututrade.com', 'qtcardfthk.futufin.com',
                        'www.futuhk.com', 'cdn.futustatic.com', 'www.moomoo.com',
                        'collect.us.moomoocrypto.com'), 'Futu'),
        'notfutunn.com': 'DIRECT', 'futunn.com.example': 'DIRECT',
        'notfututrade.com': 'DIRECT', 'fututrade.com.example': 'DIRECT',
    }
    futu_rules = [line for line in original if line.endswith(',Futu')]
    assert len(futu_rules) >= 46
    fast_path = original.index('GEOIP,CN,DIRECT,no-resolve')
    assert all(original.index(line) < fast_path for line in futu_rules), 'Futu shadowed by domestic routing'
    opend = '/Applications/Futu_OpenD.app/Contents/MacOS/Futu_OpenD'
    process_rule = f'PROCESS-NAME,{opend},Futu'
    if profile.name == 'surge.conf':
        assert original.count(process_rule) == 1
        assert f'#!MACOS-ONLY\n{process_rule}' in profile.read_text()
        assert 'evaluate-before-use = true' in groups['Futu']
        for host in ('170.106.47.242', '106.55.66.56', '47.250.12.193', 'unknown.example'):
            assert route(host, opend) == 'Futu', (host, 'OpenD public destination bypassed')
        assert route('192.168.50.12', opend) == 'DIRECT', 'LAN must remain direct'
        assert route('unknown.example', '/tmp/Futu_OpenD') == 'DIRECT', 'Process path must be exact'
    else:
        assert process_rule not in original, 'macOS process rule must not enter Shadowrocket'
    if profile.name == 'surge.conf':
        cases.update(dict.fromkeys(('argotunnel.com', 'region1.v2.argotunnel.com',
                                   'region2.v2.argotunnel.com'), 'US Only'))
        tunnel_rule = 'DOMAIN-SUFFIX,argotunnel.com,US Only'
        assert original.count(tunnel_rule) == 1, (profile.name, 'missing native tunnel route')
        assert all(original.index(tunnel_rule) < i for i, line in enumerate(original)
                   if line.startswith(('RULE-SET,', 'DOMAIN-SET,'))), (profile.name, 'Tunnel route shadowed')
    for host, expected in cases.items():
        assert route(host) == expected, (profile.name, host, route(host), expected)
    assert original[-1] == 'FINAL,DIRECT', (profile.name, 'unknown traffic must stay direct')
    for host in download_hosts:
        rule = f'DOMAIN,{host},Download'
        assert original.count(rule) == 1, (profile.name, 'missing/duplicate download rule', host)
        assert all(original.index(rule) < i for i, line in enumerate(original)
                   if any(provider in line for provider in ('DOMAIN-SUFFIX,openai.com,',
                          'DOMAIN-SUFFIX,oaistatic.com,', 'DOMAIN-SUFFIX,claude.ai,',
                          'rules/ai-extra.list', 'ChinaMax_Domain.list', '/ruleset/direct.txt',
                          '/GitHub/GitHub.list', '/Developer/Developer.list', '/ruleset/proxy.txt',
                          'Global_Domain.list', '/Global/Global.list'))), (profile.name, 'Download rule shadowed', host)
    for rule in ('DOMAIN-SUFFIX,muse.ai,AI', 'DOMAIN,www.facebook.com,AI',
                 'DOMAIN,www.instagram.com,AI', 'DOMAIN,auth.meta.com,AI'):
        assert original.count(rule) == 1, (profile.name, 'missing/duplicate Muse rule', rule)
        assert all(original.index(rule) < i for i, line in enumerate(original)
                   if any(provider in line for provider in ('rules/ai-extra.list', 'rules/proxy-extra.list',
                          'ChinaMax_Domain.list', '/ruleset/direct.txt', '/ruleset/proxy.txt',
                          'Global_Domain.list', '/Global/Global.list'))), (profile.name, 'Muse rule shadowed', rule)
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
