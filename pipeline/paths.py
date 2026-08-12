import os, shutil
from pathlib import Path

STYLES = ("natural", "filmic", "bw")
CROPS = ("8x10", "5x7")
_RT_BUNDLE = "/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli"


def root():
    return Path(os.environ.get("PIPELINE_ROOT",
                Path(__file__).resolve().parent.parent))


def input_dir():    return root() / "Input"
def output_dir():   return root() / "Output"
def archive_dir():  return root() / "archive"
def staging_dir():  return root() / "staging"
def run_dir():      return root() / "run"
def recipes_dir():  return root() / "recipes"
def sidecars_dir(): return root() / "sidecars"
def previews_dir(): return root() / "previews"
def config_dir():   return root() / "config"
def manifest_path(): return root() / ".manifest"


def rt_cli():
    # PATH first: Checkpoint 1 found the in-bundle binary exits 133/SIGTRAP
    # while /usr/local/bin/rawtherapee-cli (standalone 5.12 CLI) works.
    p = shutil.which("rawtherapee-cli")
    if p:
        return p
    if os.access(_RT_BUNDLE, os.X_OK):
        return _RT_BUNDLE
    raise RuntimeError("rawtherapee-cli not found (PATH or bundle)")
