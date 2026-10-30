#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$task_root/.cache/kicad-docs" "$task_root/.cache/kicad"
export KICAD_DOCUMENTS_HOME="$task_root/.cache/kicad-docs"
export KICAD10_3RD_PARTY="$task_root/.cache/kicad-docs/3rdparty"
export KICAD_CONFIG_HOME="$task_root/.cache/kicad"
exec kicad-cli "$@"
