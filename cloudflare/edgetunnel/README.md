# EdgeTunnel deployment

The deployed Worker is based on `cmliu/edgetunnel` commit
`fb3212257e3527447d7368010b378f7e449444b4` and is served at
`edge.fallback.page`.

Cloudflare resources:

- Worker: `surge-edgetunnel`
- KV namespace: `surge-edgetunnel-kv`
- KV binding: `KV`
- custom domain: `edge.fallback.page`

Runtime configuration disables KV access logging and enables two concurrent TCP
dials. `ADMIN`, `KEY` and `UUID` are Worker secrets. The local recovery copy is
`private/edgetunnel.env`, which is ignored by Git.

The upstream Worker is intentionally pinned. Review upstream changes before
deploying a newer commit because the Worker can initiate arbitrary outbound TCP
connections.
