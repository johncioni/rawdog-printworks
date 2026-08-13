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
    p = sub.add_parser("approve"); p.add_argument("stem")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=lambda ns: _dispatch(
        ns, lambda n: driver.approve(n.stem), mutating=True))
    p = sub.add_parser("render"); p.add_argument("stem")
    p.set_defaults(fn=lambda ns: _dispatch(
        ns, lambda n: driver.render_photo(n.stem), mutating=True))
    p = sub.add_parser("verify"); p.add_argument("stem")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=lambda ns: _dispatch(ns, _verify_cmd, mutating=True))
    p = sub.add_parser("run"); p.add_argument("--json", action="store_true")
    # NOT mutating at dispatch: process_all takes the lock itself, and the
    # O_EXCL lock is not reentrant — wrapping it here would deadlock.
    p.set_defaults(fn=lambda ns: _dispatch(
        ns, lambda n: driver.process_all(), mutating=False))
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
        from . import ingest, render
        return jsonio.run_json(lambda: run() or {}, adapters={
            render.RenderError: "RENDER_FAILED",
            ingest.IngestError: "BAD_INPUT",
            FileNotFoundError: "NOT_FOUND"})
    return _wrap(lambda _ns: run())(ns)


def _locked_json(ns, fn):
    # adjust: the legacy path pretty-prints the same result body --json emits.
    from . import jsonio
    body = _locked(fn, mutating=True)
    if getattr(ns, "json", False):
        return jsonio.run_json(body)
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

def _ingest_cmd(ns):
    from . import ingest, jsonio
    if not ns.json:
        return _ingest()
    # Never the legacy _ingest here: it signals failure with SystemExit, a
    # BaseException run_json deliberately does not catch, which would exit
    # without ever writing an envelope.
    results = ingest.run()
    failed = [f"{stem}: {r}" for stem, r in sorted(results.items())
              if "failed" in r]
    if failed:
        raise jsonio.CommandError("PARTIAL_FAILURE", "; ".join(failed))
    return {}

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
