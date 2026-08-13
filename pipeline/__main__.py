import argparse, sys

def _wrap(fn):
    def inner(ns):
        try:
            return fn(ns) or 0
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    return inner

def build_parser():
    from . import driver, manifest, ingest, render
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status"); p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_wrap(lambda ns: _status_cmd(ns)))
    sub.add_parser("ingest").set_defaults(fn=_wrap(lambda ns: _ingest()))
    p = sub.add_parser("preview")
    p.add_argument("stem", nargs="?"); p.add_argument("style", nargs="?")
    p.add_argument("--stem", dest="stem_flag"); p.add_argument("--style", dest="style_flag")
    p.set_defaults(fn=_wrap(lambda ns: print(driver.preview_photo(*_preview_target(ns)))))
    p = sub.add_parser("croppreview"); p.add_argument("stem"); p.add_argument("style"); p.add_argument("crop")
    p.set_defaults(fn=_wrap(lambda ns: print(driver.crop_preview(ns.stem, ns.style, ns.crop))))
    p = sub.add_parser("approve"); p.add_argument("stem")
    p.set_defaults(fn=_wrap(lambda ns: driver.approve(ns.stem)))
    p = sub.add_parser("render"); p.add_argument("stem")
    p.set_defaults(fn=_wrap(lambda ns: driver.render_photo(ns.stem)))
    p = sub.add_parser("verify"); p.add_argument("stem")
    p.set_defaults(fn=_wrap(lambda ns: _verify(ns.stem)))
    sub.add_parser("run").set_defaults(fn=_wrap(lambda ns: driver.process_all()))
    return ap

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
    from . import jsonio, status
    return jsonio.run_json(lambda: status.snapshot())

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
