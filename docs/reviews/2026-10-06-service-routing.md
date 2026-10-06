# Shared-service routing repair — 2026-10-06

Recent ntfy notification cache contained 39 failure messages, including 25 public ntfyx health transitions and 6 metric-collection alerts. Actual Surge request logs showed the ntfyx hosts falling through FINAL/DIRECT. Policy-specific probes of production/staging API, site, Web and quant.fallback.page timed out after 15 seconds on DIRECT while the same requests returned HTTP 200 in about 1.7–2.6 seconds through US Only.

Both profiles now route ntfyx.me and the exact quant.fallback.page, share.fallback.page, arb.fallback.page and discord.fallback.page hosts through US Only, before remote rule sets. Anonymous Access-protected origins retain their normal login redirects. No broad fallback.page/CDN rule was added, FINAL,DIRECT and exchange/AI exits are retained.

The active mini profile was backed up under ~/.local/state/infra/backup/2026-10-06/surge/ and patched narrowly before reload. The effective profile and pro15 request logs were checked after the asynchronous reload settled. Real ntfyx monitor reads then verified all eight endpoint identities and currently accessible queue/business aggregates. Known Cloudflare Analytics/Billing permission gaps remain partial coverage. pro12 finance-publish.service subsequently passed full release/file verification for 20261006T125340-d17fb4d4.

Local routing checks cover the added hosts and unrelated lookalike hosts. Remote rule checks and credential rendering passed. Existing unrelated README edits, editor swap file and untracked local helpers were preserved. Shared-infra audit details: ~/AI/share_source/docs/infra-health-20261006.md.
