### Task 10: Ingest banner, Settings, notifications

**Files:**
- Create: `app/RAWdogPrintworks/Sources/IngestBanner.swift`, `SettingsSheet.swift`
- Modify: `PrintworksApp.swift` (Settings scene + UserDefaults-backed config), `Sources/PrintworksCore/AppModel.swift` (pending-input detection — test-first)

**Interfaces:**
- Produces:
  - Settings: two fields (repo path default `~/Projects/rawdog-printworks`, python path default `<repo>/.venv/bin/python`) stored in `UserDefaults` keys `repoPath`/`pythonPath`. Paths are tilde-expanded (`NSString.expandingTildeInPath`) before any use — `URL(fileURLWithPath: "~/…")` does NOT expand. Validation is **live** (spec §5.5): field changes debounce (~600 ms) into a `status --json` probe via a throwaway `PipelineClient`, showing ok/error inline; Save enables only while the current pair validates; saving rebuilds the model's client + watcher.
  - `AppModel.pendingInputFiles: [String]` — computed on refresh by listing `Input/*.rw2|*.RW2` whose stems are absent from the snapshot (test with a temp dir set as repo); `IngestBanner` renders "N new RAW files — Ingest now?" → `model.ingestPending()` (plain `ingest --delivery-id <uuid> --json` + `run --json`, test-first).
  - Notification on publish: after an approve-chain or reprocess `RunResult` containing `published` entries, post `UNUserNotificationCenter` notification "P1036163 published (v004, 29 files)" (request authorization once at first use; guard `#if !DEBUG`-free — personal app, always attempt; failure to authorize is silently ignored).

- [ ] **Step 1: Model tests** (`pendingInputFiles`, `ingestPending` args) → fail → implement.
- [ ] **Step 2: Implement views + notification hook.**
- [ ] **Step 3: Gate + manual smoke** (drop a copy of a published RW2 → conflict banner from pipeline result; Settings validation passes on the real repo, fails on a bogus path). Screenshot the banner + settings sheet.
- [ ] **Step 4: Commit**

```bash
git add app/
git commit -m "feat(app): ingest banner, settings sheet with validation, publish notifications"
```

---

