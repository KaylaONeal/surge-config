# Company DNS incident — 2026-08-31

## Symptom

Company intranet sites matched a `DIRECT` rule but did not open in a browser.
A profile without encrypted DNS and DNS hijacking worked.

## Root cause

The system resolver returned an address for the tested intranet hostname, while
the configured public DNS and encrypted DNS path returned no answer. `DIRECT`
only controls routing; it cannot repair a failed DNS lookup.

The company suffixes were also duplicated in `rules/direct-extra.list`, which
made rule-match diagnostics ambiguous on stale or differently loaded profiles.

The protected configuration service continued returning an old template after
GitHub Raw had updated. Its `cacheEverything: true` fetch policy made a manual
profile refresh unreliable and explained why another computer still observed
the old `direct-extra.list` match.

## Fix

- Keep company suffixes inline before every remote rule set.
- Resolve both apex and wildcard company domains with `server:syslib`.
- Remove encrypted DNS and DNS hijacking from the Surge template.
- Remove duplicate company suffixes from `direct-extra.list`.
- Retain the explicit `adlp` and `kepm` rejects before broad company DIRECT.
- Fetch templates without edge caching and use a unique query parameter.

## Verification

Regression checks enforce DNS settings, host mappings, inline rule order, and
the absence of duplicate remote-list entries. The protected rendered profile
must be checked again after publishing.
