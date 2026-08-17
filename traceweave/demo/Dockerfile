# Dev-only tooling for the live demo (design doc: "genuinely new work" -- no
# baked PyCG image exists elsewhere in this repo, only pycg_parse_rate.py's
# runtime `pip install` inside an existing base image). Does not touch the
# amd64-pinned corpus.
#
# BASE_IMAGE is passed as a build-arg, resolved by build_image.sh via
# scripts/resolve_image.py -- never hardcode a digest here, the project's own
# rule (resolve_image.py) is that a hardcoded amd64 pin silently emulates on
# an arm64 host and invalidates timings.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# Same pin + same shim as scripts/pycg_parse_rate.py: PyCG 0.0.8's sdist
# ships its package dir as PyCG/ while its own internal imports say
# `from pycg import ...`. Case-insensitive macOS hides this; Linux (this
# image) cannot import it at all without the symlink.
RUN pip install --no-cache-dir pycg==0.0.8 \
    && SP="$(python -c 'import site; print(site.getsitepackages()[0])')" \
    && ln -sfn "$SP/PyCG" "$SP/pycg"

COPY run_static.py /run_static.py
ENTRYPOINT ["python3", "/run_static.py"]
