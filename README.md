# surge-config

Single rule set for Surge (macOS/iOS) and Shadowrocket, shared across devices via one URL.

## Routing policy

| Traffic | Policy group | Exit |
|---|---|---|
| AI / LLM services (OpenAI, Claude, Gemini, Copilot, Grok, Perplexity, Cursor, HuggingFace, …) | `AI` | **US only** — `fallback` group, never crosses to KR/UK |
| Other overseas services (Google, YouTube, Telegram, X, GitHub, Netflix, …) | `Proxy` / `Streaming` / `Telegram` | **Fastest of US / KR / UK** — `url-test`, retested every 300 s |
| Domestic (ChinaMax list + GEOIP CN) | `Domestic` | DIRECT |
| Everything unmatched | `Fallback` | **DIRECT** |

`AI` uses `fallback`, not `url-test`: latency is irrelevant, exit country is not.
A US node only gets skipped when it is genuinely dead, so an AI request can never
egress from Korea and trip an account-region check.

## Files

| File | Use |
|---|---|
| `surge.conf` | Surge 5. Has `#!MANAGED-CONFIG` — auto-refreshes daily. |
| `shadowrocket.conf` | Shadowrocket. Same rules, Surge-only keys stripped. |
| `rules/ai-extra.list` | Self-maintained AI domains that upstream lists miss. |
| `scripts/check-rules.sh` | Verifies every RULE-SET URL returns 200. |

## Install

Surge → Profile → Download from URL:

```
https://raw.githubusercontent.com/KaylaONeal/surge-config/main/surge.conf
```

Shadowrocket → Config → Add from URL:

```
https://raw.githubusercontent.com/KaylaONeal/surge-config/main/shadowrocket.conf
```

Then edit **only** the `[Proxy]` section with your own nodes.

## Node naming (required)

Policy groups reference node names literally. Keep the region prefix:

```
US HTTPS 01 = https, us1.example.com, 443, USER, PASS, sni=us1.example.com
US HY2 01   = hysteria2, us1.example.com, 8443, password=PASS, sni=us1.example.com, download-bandwidth=200
```

Adding a second US node means adding `US HY2 02` to the `[Proxy]` section **and**
to the `US Auto`, `US Only`, and `Fastest` groups.

> Credentials live in your local profile copy, not in this repo. If you paste real
> node passwords into a file here, make the repo private and use a token-authenticated
> raw URL — a public repo means anyone can read and use your nodes.

## Correctness & freshness

- Rules come from [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) (updated near-daily) via remote `RULE-SET`, so the rule bodies refresh without editing this repo.
- `#!MANAGED-CONFIG interval=86400` re-pulls the profile skeleton once a day.
- A daily GitHub Action runs `scripts/check-rules.sh`; if upstream renames or deletes a list, CI turns red instead of the rule silently vanishing.
- Rule order matters: AI sets are evaluated **before** `Google`/`Microsoft`/`Global`, otherwise `gemini.google.com` would be swallowed by the Google set and routed to a non-US node.

## Known trade-off

`FINAL,Fallback` sends unmatched traffic DIRECT, per design. A brand-new overseas
site nobody has listed yet will therefore fail rather than silently proxy.
Fix in one tap: switch the `Fallback` group from `DIRECT` to `Proxy` in the app UI,
or add a rule to `rules/ai-extra.list` / open a PR.
