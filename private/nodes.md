# Node inventory

This directory is tracked. It records the real proxy topology but never stores
authentication material.

| Config name | Protocol | Server | Port | Intended pool | Notes |
|---|---|---|---:|---|---|
| `JP HTTPS 01` | HTTPS | `us1.fallback.page` | 443 | JP | Imported from phone node `jp`; verify actual exit country |
| `KR HTTPS 01` | HTTPS | `kr.fallback.page` | 443 | KR | Imported from phone node `kr` |
| `US HTTPS 01` | HTTPS | `us1.fallback.page` | 443 | US | Uses `www.bing.com` as SNI |
| `US TUIC 01` | TUIC v5 | `192.3.243.194` | 51443 | US | Imported from phone node `uh`; verify actual exit country |
| `US HY2 Relay 01` | Hysteria 2 | `139.196.52.175` | 36001 | US | Mainland relay endpoint; verify final exit country |
| `US HY2 01` | Hysteria 2 | `139.196.52.175` | 36000 | US | Mainland relay endpoint; verify final exit country |
| `US HY2 02` | Hysteria 2 | `us2.fallback.page` | 4444 | US | Port hopping `5000-6000` |
| `CF Edge Direct` | Trojan over WebSocket | `edge.fallback.page` | 443 | CF Edge | Normal DNS/Anycast entry |
| `CF Edge CT 01` | Trojan over WebSocket | `188.164.248.21` | 443 | CF Edge | China Telecom candidate |
| `CF Edge CT 02` | Trojan over WebSocket | `8.35.211.67` | 443 | CF Edge | China Telecom candidate |
| `CF Edge CU 01` | Trojan over WebSocket | `104.26.0.109` | 443 | CF Edge | China Unicom candidate |
| `CF Edge CU 02` | Trojan over WebSocket | `172.67.66.108` | 443 | CF Edge | China Unicom candidate |
| `CF Edge CM 01` | Trojan over WebSocket | `104.17.107.60` | 443 | CF Edge | China Mobile candidate |
| `CF Edge CM 02` | Trojan over WebSocket | `104.17.160.249` | 443 | CF Edge | China Mobile candidate |

The pool assignments preserve the intent of the exported phone profile. Node
names and ingress locations do not prove the egress country. Verify each node's
public exit IP before relying on the `AI` policy.

The Cloudflare entries all use `edge.fallback.page` as TLS SNI and WebSocket
Host. `CF Edge Auto` tests them on the client and selects the best entry for the
current network. Cloudflare Worker egress is not guaranteed to be in the US, so
this group is deliberately excluded from `AI` / `US Only`.

Authentication values live in `private/secrets.env`, which is ignored by Git.
Start from `private/secrets.example.env`.
