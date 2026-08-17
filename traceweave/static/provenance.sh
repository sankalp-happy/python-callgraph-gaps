#!/bin/sh
# Runs INSIDE the static image. Prints what the image actually contains, as JSON.
#
# Exists because one component of the image is not version-pinned: node comes
# from the base image's Debian repos. Recording the resolved versions next to
# the base digest means a rebuild that moves node shows up in the artifact
# instead of quietly moving a result.
set -eu
PYCG_VER="$(python3 -c 'import importlib.metadata as m; print(m.version("pycg"))' 2>/dev/null || echo unknown)"
PYCG_IMPORTABLE="$(python3 -c 'import pycg.pycg; print("yes")' 2>/dev/null || echo no)"
printf '{'
printf '"python":"%s",' "$(python3 -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])')"
printf '"pycg":"%s",' "$PYCG_VER"
printf '"pycg_importable":"%s",' "$PYCG_IMPORTABLE"
printf '"pyright":"%s",' "$(pyright --version 2>/dev/null | head -1 || echo unknown)"
printf '"node":"%s",' "$(node --version 2>/dev/null || echo unknown)"
printf '"arch":"%s"' "$(uname -m)"
printf '}\n'
