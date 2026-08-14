RAW-<!-- issue number, e.g. RAW-1; delete this line if there's no ticket -->

## What changed

<!-- One or two sentences. Why, not just what. -->

## Quality gate

- [ ] `.venv/bin/python -m pytest tests/ -q` passes locally
- [ ] Touches an approval-fingerprint input (style profiles, crop geometry,
      sharpening, RawTherapee seed, toolchain.lock rendering entries, lab-profile
      review fields)? If yes, note that approved photos will re-enter
      `review_required` — that's expected, not a regression.
