import argparse, json, sys

def _wrap(fn):
    def inner(ns):
        try:
            return fn(ns) or 0
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    return inner

def build_parser():
    from . import driver
    from . import adjust as adjust_mod
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status"); p.add_argument("--json", action="store_true")
    p.set_defaults(fn=lambda ns: _dispatch(ns, _status_cmd, mutating=False))
    p = sub.add_parser("ingest"); p.add_argument("--json", action="store_true")
    # `from` is a keyword, so the destination has to be named explicitly.
    p.add_argument("--from", dest="sources", nargs="+")
    p.add_argument("--delivery-id")
    p.set_defaults(fn=lambda ns: _dispatch(ns, _ingest_cmd, mutating=True))
    p = sub.add_parser("preview")
    p.add_argument("stem", nargs="?"); p.add_argument("style", nargs="?")
    p.add_argument("--stem", dest="stem_flag"); p.add_argument("--style", dest="style_flag")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=lambda ns: _dispatch(ns, _preview_cmd, mutating=True,
                                           precheck=_preview_target))
    p = sub.add_parser("croppreview"); p.add_argument("stem"); p.add_argument("style"); p.add_argument("crop")
    p.set_defaults(fn=lambda ns: _dispatch(
        ns, lambda n: print(driver.crop_preview(n.stem, n.style, n.crop)),
        mutating=True))
    p = sub.add_parser("crops"); p.add_argument("--stem", required=True)
    p.add_argument("--json", action="store_true")
    # Read-only: it reports what approve would bind and persists nothing, so
    # it must not contend for the driver lock.
    p.set_defaults(fn=lambda ns: _dispatch(ns, _crops_cmd, mutating=False))
    p = sub.add_parser("approve")
    p.add_argument("stem", nargs="?"); p.add_argument("--stem", dest="stem_flag")
    p.add_argument("--review-file")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=lambda ns: _dispatch(ns, _approve_cmd, mutating=True,
                                           precheck=_approve_target))
    p = sub.add_parser("render"); p.add_argument("stem")
    p.set_defaults(fn=lambda ns: _dispatch(
        ns, lambda n: driver.render_photo(n.stem), mutating=True))
    p = sub.add_parser("verify"); p.add_argument("stem")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=lambda ns: _dispatch(ns, _verify_cmd, mutating=True))
    p = sub.add_parser("run"); p.add_argument("--json", action="store_true")
    p.add_argument("--stem"); p.add_argument("--force", action="store_true")
    # NOT mutating at dispatch: process_all takes the lock itself, and the
    # O_EXCL lock is not reentrant — wrapping it here would deadlock.
    p.set_defaults(fn=lambda ns: _dispatch(ns, _run_cmd, mutating=False))
    p = sub.add_parser("adjust")
    p.add_argument("--stem", required=True); p.add_argument("--style", required=True)
    p.add_argument("--temperature", type=int); p.add_argument("--exposure", type=float)
    p.add_argument("--reset", action="store_true"); p.add_argument("--json", action="store_true")
    p.set_defaults(fn=lambda ns: _locked_json(ns, lambda: adjust_mod.apply(
        ns.stem, ns.style, ns.temperature, ns.exposure, ns.reset)))
    return ap


def _locked(fn, mutating):
    """Mutating commands take the driver lock exactly once, here at dispatch."""
    from . import publish
    def body():
        if mutating:
            with publish.acquire_lock():
                return fn()
        return fn()
    return body


def _dispatch(ns, fn, mutating, precheck=None):
    """Run one subcommand: `precheck` validates argument shape before the lock
    is taken (a typo should not contend for the driver mutex), then the body
    runs and its failure becomes either an `error:` line or a JSON envelope."""
    from . import jsonio
    def run():
        if precheck is not None:
            precheck(ns)
        return _locked(lambda: fn(ns), mutating)()
    if getattr(ns, "json", False):
        return jsonio.run_json(lambda: run() or {}, adapters=_adapters())
    return _wrap(lambda _ns: run())(ns)


def _adapters():
    """The typed-error → contract-code map, shared by every --json command so
    one command can't report a different code than another for the same
    failure."""
    from . import ingest, render
    return {
        render.RenderError: "RENDER_FAILED",
        ingest.IngestError: "BAD_INPUT",
        FileNotFoundError: "NOT_FOUND",
    }


def _locked_json(ns, fn):
    # adjust: the legacy path pretty-prints the same result body --json emits.
    from . import jsonio
    body = _locked(fn, mutating=True)
    if getattr(ns, "json", False):
        return jsonio.run_json(body, adapters=_adapters())
    print(json.dumps(body(), indent=2, sort_keys=True))
    return 0

def _resolve(name, flag_value, positional):
    from . import jsonio
    if flag_value is not None and positional is not None:
        raise jsonio.CommandError(
            "BAD_INPUT", f"{name} given both positionally and as --{name}")
    value = flag_value if flag_value is not None else positional
    if value is None:
        raise jsonio.CommandError("BAD_INPUT", f"missing {name}")
    return value

def _preview_target(ns):
    return (_resolve("stem", ns.stem_flag, ns.stem),
            _resolve("style", ns.style_flag, ns.style))

def _approve_target(ns):
    return _resolve("stem", ns.stem_flag, ns.stem)

def _read_review(path):
    from pathlib import Path
    from . import jsonio
    try:
        text = Path(path).read_text()
    except OSError as error:
        raise jsonio.CommandError(
            "NOT_FOUND", f"review file unreadable: {error}") from error
    try:
        review = json.loads(text)
    except ValueError as error:
        raise jsonio.CommandError(
            "BAD_INPUT", f"review file is not valid JSON: {error}") from error
    if not isinstance(review, dict):
        raise jsonio.CommandError(
            "BAD_INPUT", "review file must contain a JSON object")
    return review

def _approve_cmd(ns):
    from . import driver
    stem = _approve_target(ns)
    if ns.review_file is None:
        return driver.approve(stem)
    result = driver.approve_review(stem, _read_review(ns.review_file))
    if not ns.json:
        # No legacy output to preserve — pretty-print the same body --json emits.
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    return result

def _run_cmd(ns):
    from . import driver, jsonio
    stems = {ns.stem} if ns.stem else None
    if not ns.json:
        # With neither flag this is process_all()'s own signature default, so
        # the legacy invocation stays byte-for-byte what it was.
        return driver.process_all(stems=stems, force=ns.force)
    result = {"published": [], "advanced": [], "failed": []}
    try:
        driver.process_all(stems=stems, force=ns.force, collect=result)
    except RuntimeError as error:
        # Per-stem failures are collected, so a RuntimeError reaching here is
        # the toolchain-drift refusal that stops the whole batch.
        raise jsonio.CommandError("TOOLCHAIN_FAILED", str(error)) from error
    failed = result["failed"]
    if failed:
        total = sum(len(result[key])
                    for key in ("published", "advanced", "failed"))
        raise jsonio.CommandError(
            "PARTIAL_FAILURE", f"{len(failed)} of {total} photos failed",
            result=result)
    return result


def _status_cmd(ns):
    if not ns.json:
        return _status()
    from . import status
    return status.snapshot()

def _preview_cmd(ns):
    from . import driver, provenance, recipe
    from . import adjust as adjust_mod
    stem, style = _preview_target(ns)
    if not ns.json:
        print(driver.preview_photo(stem, style))
        return
    # Sampled before the render: the render is what moves the revision.
    revision_before = provenance.review_revision(stem, recipe.load(stem))
    driver.preview_photo(stem, style)
    return adjust_mod.preview_result(stem, style, revision_before)

def _crops_cmd(ns):
    from . import driver
    result = driver.crop_windows(ns.stem)
    if not ns.json:
        # No legacy output to preserve — pretty-print the same body --json emits.
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    return result

def _ingest_result(ns):
    """The staged copy-in (when --from) and the Input/ ingest as one body."""
    from . import ingest
    result = {"ingested": [], "skipped": [], "conflicts": [], "failed": []}
    if ns.sources:
        staged = ingest.stage_sources(ns.sources)
        for key in ("skipped", "conflicts", "failed"):
            result[key] += staged[key]
    for stem, outcome in sorted(ingest.run(ns.delivery_id).items()):
        if outcome == "ok":
            result["ingested"].append(stem)
        elif outcome.startswith("failed: "):
            result["failed"].append({"file": stem, "code": "BAD_INPUT",
                                     "message": outcome.removeprefix("failed: ")})
        else:
            # Today that is only "skipped (already ingested)"; unwrapping the
            # text rather than matching it keeps a new outcome from vanishing.
            result["skipped"].append(
                {"file": stem,
                 "reason": outcome.removeprefix("skipped (").removesuffix(")")})
    return result

def _ingest_cmd(ns):
    from . import jsonio
    if not ns.json and not ns.sources and ns.delivery_id is None:
        return _ingest()
    # Never the legacy _ingest here: it signals failure with SystemExit, a
    # BaseException run_json deliberately does not catch, which would exit
    # without ever writing an envelope.
    result = _ingest_result(ns)
    if not ns.json:
        # No legacy output to preserve on the flag path — pretty-print the same
        # body --json emits, and keep _ingest's exit code for failures.
        print(json.dumps(result, indent=2, sort_keys=True))
        if result["failed"]:
            raise SystemExit(1)
        return
    if result["failed"]:
        raise jsonio.CommandError(
            "PARTIAL_FAILURE", f"{len(result['failed'])} file(s) failed",
            result=result)
    return result

def _verify_cmd(ns):
    from . import driver, jsonio
    if not ns.json:
        return _verify(ns.stem)
    # Same SystemExit hazard as ingest — the JSON path reports problems as an
    # error envelope instead of exiting out from under run_json.
    problems = driver.verify_photo(ns.stem)
    if problems:
        raise jsonio.CommandError("VERIFY_FAILED", "; ".join(problems))
    return {"stem": ns.stem, "verify": "clean"}

def _status():
    from . import driver, manifest
    m = manifest.load()
    if not m["photos"]:
        print("photos: none ingested")
        return
    for stem in sorted(m["photos"]):
        fp = driver._current_fingerprint(stem)
        print(f"{stem}: {manifest.effective_state(m, stem, fp)}")

def _ingest():
    from . import ingest
    results = ingest.run()
    for stem, r in sorted(results.items()):
        print(f"{stem}: {r}")
    if any("failed" in r for r in results.values()):
        raise SystemExit(1)

def _verify(stem):
    from . import driver
    problems = driver.verify_photo(stem)
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print("verify: clean")

def main(argv=None):
    ns = build_parser().parse_args(argv)
    return ns.fn(ns)

if __name__ == "__main__":
    raise SystemExit(main())
