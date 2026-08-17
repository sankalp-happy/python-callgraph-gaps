# The Phase 1 §1.2 static-extraction image: both baselines' tools, one image.
#
# One image rather than two so that a repo's PyCG graph and its Pyright
# resolutions come from the same pinned environment -- MANIFEST §1's "one
# corpus, one architecture" applies to the analysis side too, and a reader
# should be able to name a single digest that produced both halves of S.
#
# BASE_IMAGE is a build-arg resolved by build_image.sh via
# scripts/resolve_image.py. Never hardcode a digest here: an amd64 pin
# silently emulates under QEMU on an arm64 host and invalidates every timing
# (resolve_image.py, tests/run_checks.sh check 6).
#
# Python 3.10, not 3.12: MANIFEST §2.1 -- PyCG 0.0.8 does not run on 3.12 at
# all (100% parse-failure rate, measured). Our own AST inventory therefore runs
# on the HOST's newest interpreter and never inside this image, which is why
# nothing here needs to parse contemporary syntax.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# Same pin + same shim as scripts/pycg_parse_rate.py and demo/Dockerfile:
# PyCG 0.0.8's sdist ships its package dir as PyCG/ while its own internal
# imports say `from pycg import ...`. Case-insensitive macOS hides this; Linux
# cannot import it at all without the symlink.
RUN pip install --no-cache-dir pycg==0.0.8 \
    && SP="$(python -c 'import site; print(site.getsitepackages()[0])')" \
    && ln -sfn "$SP/PyCG" "$SP/pycg"

# Pyright 1.1.411 -- the version MANIFEST §2 pins, published 2026-06-25.
# The npm package ships its own bundled JS, so nothing is fetched at run time
# and the container needs no network.
#
# Node itself comes from the base image's Debian repos and is therefore the one
# floating component in an otherwise fully pinned image. It is not left
# implicit: `provenance.sh` records the resolved node and npm versions beside
# the image digest, so a rebuild that moves node is visible in the artifact
# rather than invisible in the results.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g pyright@1.1.411 \
    && apt-get purge -y npm && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /root/.npm

COPY provenance.sh /provenance.sh
RUN chmod +x /provenance.sh

# No ENTRYPOINT: the two baselines invoke different programs in this image
# (`python3 /s/pycg_graph.py` and `pyright-langserver --stdio`), and an
# entrypoint would just mean two --entrypoint overrides at every call site.
CMD ["/provenance.sh"]
