# Execution host provenance

captured: 2026-08-24T06:45:23Z
hostname: kap-LOQ-15APH8

## Hardware
cpu:    AMD Ryzen 7 7840HS w/ Radeon 780M Graphics
cores:  16 threads / 8 physical
arch:   x86_64  (docker reports: amd64)
ram:    38 GiB
kernel: 6.8.0-136-generic
os:     Ubuntu 22.04.4 LTS

## Docker
  Server Version: 29.5.3
  Storage Driver: overlayfs
  Kernel Version: 6.12.76-linuxkit
  Operating System: Docker Desktop
  CPUs: 16
  Total Memory: 26.42GiB
  NOTE: Docker Desktop runs containers in a VM. Its memory ceiling is a
        SETTING, not the host's RAM. It defaulted to 7.75 GiB here and was
        raised to 26.42 GiB for this run. See RUN_REPORT.md section 5.

## Analysis image
  tag:    traceweave-static:latest
  digest: sha256:5a1991f03716ae98121f7e3a1cf7033f7d87966af9eecc5fbe6139e42cec5e0a
  python: 3.10.20
  pycg:   0.0.8
  pyright: 1.1.411
  node:   v20.19.2

## Base images (from config/base_images.json, unmodified)
  3.12 amd64: sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464
  3.10 amd64: sha256:e8d6cdadc17ce7146e1bb286e6093d58c8cf582659a558ad51cd103829655e72

## Host toolchain
  python3: Python 3.10.12
  git:     git version 2.34.1
