# surge-config

Git-managed Surge configuration shared by iOS and macOS. Real node topology is
tracked; passwords and other authentication material are not.

## Routing policy

| Traffic | Policy | Default exit |
|---|---|---|
| AI / LLM services | `AI` | US-only fallback pool |
| Other overseas services | `Proxy`, `Streaming`, `Telegram` | JP first, with cross-region and manual alternatives |
| Domestic services | `Domestic` | DIRECT |
| Ads | `AdBlock` | REJECT, switchable to DIRECT |
| Cloudflare fallback | `CF Edge Auto` | Best of direct/CT/CU/CM EdgeTunnel ingress |
| Everything unmatched | `Fallback` | DIRECT |

AI rules are evaluated before Google, Microsoft and Global rule sets. The
`US Only` group never falls back to JP or KR.

## Repository layout

| Path | Purpose | Tracked |
|---|---|---|
| `surge.conf` | Shared Surge profile template for iOS and macOS | Yes |
| `shadowrocket.conf` | Shadowrocket profile template | Yes |
| `private/nodes.md` | Real protocol/server/port/SNI inventory | Yes |
| `private/secrets.example.env` | Empty authentication-variable template | Yes |
| `~/.config/surge-config/credentials.env` | Local passwords and authentication IDs | Outside repository |
| `rules/*.list` | Shared AI, direct, reject and macOS process rules | Yes |
| `build/*.conf` | Rendered usable profiles containing credentials | **No** |

The raw phone export is intentionally ignored because it contains proxy
credentials, API access tokens and a complete MITM CA private key.

## Authentication boundary

These values are treated as secrets and never committed:

- proxy passwords and usernames;
- TUIC UUIDs and other authentication identifiers;
- Surge HTTP API and external-controller tokens;
- MITM/keystore private keys and their passphrases.
- protected rendered-profile URLs when they contain an access token.

The committed profiles use placeholders such as `__HTTPS_PASSWORD__`. They are
not directly usable by Surge until rendered.

Create the local credential directory and render:

```bash
mkdir -p ~/.config/surge-config
chmod 700 ~/.config/surge-config
cp private/secrets.example.env ~/.config/surge-config/credentials.env
chmod 600 ~/.config/surge-config/credentials.env
$EDITOR ~/.config/surge-config/credentials.env
./scripts/render-config.sh
```

Usable profiles are written to `build/` with mode `0600`.

## Remote loading limitation

Surge managed profiles are downloaded as final configuration text. Surge does
not substitute local environment variables into a remote profile, so a Git
file that excludes passwords cannot simultaneously be a directly usable full
profile.

There are two safe deployment choices:

1. Render locally and import `build/surge.conf`; all remote `RULE-SET` files
   continue updating independently.
2. Render in a protected deployment service and serve the result from an
   authenticated URL. The generated result must not be committed back to Git.

Making the GitHub repository private protects tracked metadata, but by itself
does not inject credentials and does not guarantee Surge can authenticate to a
private GitHub raw URL.

`SURGE_MANAGED_URL` must be the protected URL that returns the rendered
`surge.conf`. The renderer writes it into `#!MANAGED-CONFIG`, so the initial
one-click import and every later automatic update use the same endpoint.

## Platform-specific behavior

One Surge profile is used for both platforms. `#!IOS-ONLY` enables hotspot,
APNs and cellular handling on iOS. `#!MACOS-ONLY` applies the work/DLP process
reject list only on macOS.

The node pool assignments were imported from `surgeconf-260830.conf`. Ingress
hostnames do not prove egress country; verify every node's public exit IP before
depending on the `AI` US-only guarantee. See `private/nodes.md` for the items
that still require verification.

## Validation

```bash
./scripts/check-rules.sh
```

The GitHub Action runs the same remote-rule check daily.

## One-click install service

The deployed configuration service is hosted at `config.fallback.page`. Its
unguessable path token is stored only in
`~/.config/surge-config/config-service.env`. Opening
that protected path in Safari shows buttons for Surge and Shadowrocket.

Surge Mac 6.7 or later can use the same browser install button. On older Mac
versions, use **Profiles > Download Profile from URL** and paste the protected
managed-profile URL, or update Surge first.

`edge.fallback.page` hosts the separately deployed EdgeTunnel Worker. Its
authentication values are Cloudflare Worker secrets with an ignored local
recovery copy in `~/.config/surge-config/edgetunnel.env`.

Set `SURGE_CONFIG_HOME` to override this local credential directory. Keep the
directory mode at `0700` and each credential file at `0600`.
