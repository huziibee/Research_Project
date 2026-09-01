# T45 - historical early-artifact reconciliation and evidence-only slice report

**Status:** COMPLETE_CPU_ONLY_NON_OFFICIAL

## Goal

Close the remaining provenance gap in the historical T31 direct-base cost and
produce a no-new-inference report from saved early outputs. This ticket never
trains, selects, tunes, prompts, decodes, regenerates, or alters a prediction.

## Required work

1. Locate the exact T31 direct-base prediction bytes, the policy and gold bytes
   used to score them, and the corresponding run/config provenance.
2. Recompute the asymmetric cost from those exact bytes. If it exactly
   reproduces the reported cost, issue a byte-addressed reconciliation artifact;
   otherwise retain the discrepancy as `NOT_COMPUTED` and do not replace the
   historical result with a fresh replay.
3. Produce an evidence-only slice/disagreement report over all available saved
   early system outputs: depth, ambiguity type, capability status, natural
   dialogue presence, and base/adapter disagreements. Every denominator and
   missing system field must be explicit; insufficient support is count-only.
4. Record raw prediction/config/policy/gold hashes, artifact paths, and any
   unavailable input. Do not make interpretation, single-ambiguity,
   isolated-context, wording, or generalisation claims.

## Acceptance

- A machine-readable reconciliation result with exact byte hashes and either
  `VERIFY_PASSED` or `NOT_COMPUTED`.
- A separate no-new-inference saved-output slice report with explicit scope,
  denominators, support gates, and unavailable fields.
- No inference job and no modification of historical predictions or Pilot data.

## Completion record — 2026-09-01

- Control status `PASS` (diagnostic status `VERIFY_PASSED`): exact saved
  direct-base bytes `73692cbe4f2300dd1d3d5bce55ef6dd598c2fb0bafe7e7cf4a52b598d470cbba`,
  the fixed policy `8fb1f28518667d2d1be6793db351eae39349959cf4fa13375d0f298f181d3f23`,
  and the frozen source/gold bytes reproduce the historical total cost `16.25`
  over `120` records (mean `0.13541666666666666`) exactly.
- The no-new-inference saved-output slice report covers all eight archived
  systems by depth, ambiguity type, capability status and dialogue presence.
  It retains `NOT_COMPUTED` boundaries for interpretation, single ambiguity,
  isolated factor effects and generalisation. It records 49 core base/adapter
  prediction-signature disagreements; all 120 raw-text hashes differ but are
  explicitly not treated as semantic evidence.
- Local immutable result hashes: reconciliation
  `d39b88264f7f2c73ee2a9f29d14836b21d59928383c17c80e67f41a36b92fd64`; slice
  report `03c5d26500cdb012df5c1a441c70b31334f43ce4835a689a2c3b7d7142f9ba42`.
  The result remains non-official and does not replace historical T31.
