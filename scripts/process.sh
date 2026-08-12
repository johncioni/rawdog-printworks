#!/bin/zsh
exec "$(dirname "$0")/../.venv/bin/python" -m pipeline "$@"
