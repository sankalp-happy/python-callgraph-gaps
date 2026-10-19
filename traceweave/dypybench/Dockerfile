# The probe image: one target Python version, plus every system library any of
# the 50 projects needs to BUILD. Built once per version under test.
#
#   docker build --build-arg PYVER=3.11 -t tw-dypybench:3.11 .
#   docker build --build-arg PYVER=3.12 -t tw-dypybench:3.12 .
#
# Why the apt list matters: if Pillow fails because libjpeg is absent, the probe
# records "does not install on 3.11" and that is a lie about the Python version.
# Every system dependency goes in here so a failure means what it says.
# DyPyBench's own Dockerfile installs libjpeg8-dev and ffmpeg and gets the rest
# from `ubuntu:latest` by luck; slim images have none of it.
ARG PYVER=3.11
FROM python:${PYVER}-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        pkg-config \
        libjpeg-dev \
        zlib1g-dev \
        libfreetype6-dev \
        liblcms2-dev \
        libtiff-dev \
        libwebp-dev \
        libopenjp2-7-dev \
        libvips-dev \
        libxml2-dev \
        libxslt1-dev \
        libffi-dev \
        libssl-dev \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Deliberately NOT upgraded to the newest setuptools. The corpus is pinned to
# commits before 2023-01-18, and setuptools 66 (Jan 2023) made PEP 440 version
# parsing strict, which breaks a handful of those projects' metadata. The probe
# records that as a real install failure and `--setuptools` retries the same
# repo against an older one, so the two causes stay separable.
RUN pip install --no-cache-dir --upgrade pip wheel

WORKDIR /work
