import argparse


def cmd_status(args):
    print("photos: (manifest not yet implemented)")
    return 0


def cmd_ingest(args):
    from . import ingest

    results = ingest.run()
    for stem, result in sorted(results.items()):
        print(f"{stem}: {result}")
    return 0 if all("failed" not in result
                    for result in results.values()) else 1


def build_parser():
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("ingest").set_defaults(fn=cmd_ingest)
    return ap


def main(argv=None):
    ns = build_parser().parse_args(argv)
    return ns.fn(ns)


if __name__ == "__main__":
    raise SystemExit(main())
