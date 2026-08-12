import argparse


def cmd_status(args):
    print("photos: (manifest not yet implemented)")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    return ap


def main(argv=None):
    ns = build_parser().parse_args(argv)
    return ns.fn(ns)


if __name__ == "__main__":
    raise SystemExit(main())
