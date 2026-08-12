# HANDOFF

## Goal
COMPLETE. GH7 RW2 → 22 verified print-ready outputs per photo. Pipeline
built, reviewed, hardened, merged to main (cce53fb). Both photos published.

## Done
- All 16 plan tasks + final whole-branch review + fix wave + migration
  re-render. 159/159 tests. Branch pipeline-implementation merged to main
  (--no-ff, branch preserved). SDD workspace deleted (git is the record).
- Published: Output/photos/P1036163/current + P1036170/current — 22
  artifacts + provenance.json each; views Output/TIF (6) / JPG (18) /
  PDF (20). QA verified: 300dpi both axes, sRGB ICC, privacy-clean
  metadata (allowlist asserted), 3-channel bw JPGs, PDF info empty,
  losslessness proven by extraction hash, exact pixel geometry.
- Styles: P1036163 base styles as-is; P1036170 sidecar-tuned (natural
  5700K +0.12EV, filmic 5950K +0.12EV, bw +0.15EV + S-curve). Expression
  audits + fingerprint-bound crops in committed recipes.

## Ruled out
(historical — see git log and docs/superpowers/specs rev 6 exclusions)

## In flight
- Nothing running.

## Next (for future deliveries — the repeatable loop)
1. Drop new .rw2/.RW2 files into Input/.
2. scripts/process.sh ingest && scripts/process.sh run  → previews.
3. Operator review loop per docs/superpowers/review-loop.md (preview →
   sidecar tune → croppreview → expression audit in recipe →
   scripts/process.sh approve <stem> → scripts/process.sh run).
4. Commit recipes/ + sidecars/ after each approval.
5. When a print lab is chosen: add config/lab-profiles/<lab>-v1.yaml per
   spec; artifact deps re-render exactly the affected outputs.
