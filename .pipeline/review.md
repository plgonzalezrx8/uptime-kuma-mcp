# Independent review ledger

## Review policy

Publication requires a fresh independent read-only `SHIP` verdict against the
exact final checkout. Any review dispatched before a subsequent source or
required-documentation change is stale and cannot clear the gate.

## Invalidated reviews

- `deleg_8301c70d`: returned `REVISE` against a pre-fix checkout. It found
  embedded URL credential leakage, failure to reuse Kuma's issued session JWT
  after 2FA login, release tags bypassing acceptance gates, and missing CI
  security/container-smoke gates. Those findings were reproduced and fixed;
  subsequent changes invalidate it as the final verdict.
- `deleg_9c0b2828`: returned `REVISE` against an older checkout. Its readiness,
  workflow, release, and receipt findings were already superseded. It also found
  concurrent refresh-event races and an insufficiently bounded upstream heartbeat
  read; both were reproduced and fixed after the verdict.
- `deleg_1a276315`: timed out without a verdict and was superseded by the
  approved Trivy gate, base-image refresh, refresh locks, heartbeat-budget fix,
  and final receipt updates.
- `deleg_3067d437`: returned `REVISE` after reproducing login readiness without
  each monitor's authoritative initial `heartbeatList`. Login now clears stale
  heartbeat state, tracks initial lists per monitor independent of event order,
  handles zero monitors explicitly, and remains unauthenticated until all required
  initial caches are complete. Source and receipt changes invalidate that verdict.
- `deleg_224f6c9a`: returned `REVISE` after reproducing URL leaks through an
  unrecognized `client_secret` query key and an `access_token` fragment. URL
  redaction now normalizes query keys through the general sensitive-key/suffix
  policy and sanitizes query-shaped fragments while preserving benign neighbors.
  Source, tests, and receipt changes invalidate that verdict.
- `deleg_d63c61ff`: returned `REVISE` after reproducing raw credential exposure
  from malformed URL ports and credentials nested inside non-sensitive query
  values. Malformed URLs now fail closed, and decoded query/fragment values are
  recursively sanitized with an explicit depth bound that fails closed on deeper
  URL content. Source, tests, and receipt changes invalidate that verdict.
- `deleg_dd646cbb`: returned `REVISE` after reproducing credentials hidden behind
  multiple percent-encoding layers in non-sensitive query values. Percent-decoding
  and sanitization now recurse together under the same explicit depth bound, with
  the entire nested value redacted if encoded content remains at the boundary.
  Source, tests, and receipt changes invalidate that verdict.
- `deleg_0004e5fb`: returned `REVISE` after reproducing normalized secret
  assignments in arbitrary text and percent-encoded fragment credentials.
  Assignment keys now use normalized sensitive-key classification, and every URL
  fragment follows bounded recursive percent-decoding and sanitization before
  output. Source, tests, and receipt changes invalidate that verdict.
- `deleg_f00c22ac`: returned `REVISE` after reproducing quoted JSON/Python-style
  secret assignments in arbitrary text and heartbeat messages. Assignment parsing
  now recognizes and preserves matched quotes around keys and values while
  replacing the complete secret value. Source, tests, and receipt changes
  invalidate that verdict.
- `deleg_57da2685`: returned `REVISE` after reproducing whitespace-bearing or
  escaped quoted values and compound secret keys such as `AWS_SECRET_ACCESS_KEY`
  and `privateKeyPem`. Assignment discovery now evaluates overlapping complete-key
  candidates, quote-aware alternatives consume complete values including escapes
  and whitespace, and token-aware key classification covers secret/password/token
  components and qualified key compounds. Source, tests, and receipt changes
  invalidate that verdict.
- `deleg_aa0614be`: returned `REVISE` after reproducing auth/credential compound
  keys such as `authorizationHeader`, `authKey`, `authenticationKey`, and
  `clientCredentials`. Token-aware classification now treats auth,
  authentication, authorization, credential, and credentials components as
  sensitive while regression tests preserve benign lexical near-matches. Source,
  tests, and receipt changes invalidate that verdict.
- `deleg_36a8e164`: returned `REVISE` after reproducing partial redaction of
  unquoted custom and Digest Authorization header values. Authorization and
  Proxy-Authorization headers are now redacted through their line boundary before
  generic assignment handling; regression tests cover custom schemes and complete
  Digest material in arbitrary text and heartbeat projections. Source, tests, and
  receipt changes invalidate that verdict.
- `deleg_5cf689c0`: returned `REVISE` after reproducing a disconnect race between
  initial-state delivery and login completion that could restore authenticated
  state and permit stale-cache reads. Login now verifies both Socket.IO and client
  connection state before committing authentication, and operational reads require
  current connected/authenticated state after session establishment. Regression
  tests cover fail-closed cached reads and subsequent session-token
  reauthentication. Source, tests, and receipt changes invalidate that verdict.
- `deleg_bb7e766b`: returned `REVISE` after finding that reauthentication cleared
  the `info` readiness event but retained the previously authenticated Kuma version,
  allowing a new versionless `info` payload to reuse stale `2.5.0` compatibility
  state. Each login now resets the observed version before collecting initial state;
  regression coverage proves a versionless reconnect fails closed with
  `version_unknown`. Source, tests, and receipt changes invalidate that verdict.

## Final verdict

Pending a replacement independent read-only review of this exact checkout.
The verdict is intentionally delivered out-of-tree so recording it cannot mutate
the reviewed checkout and invalidate its exact-target guarantee. Do not publish
unless that verdict is `SHIP` with no Critical or Important findings.
