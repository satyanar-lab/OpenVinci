#!/bin/sh
# OpenVinci container entrypoint.
#
# Tightens the few ulimits the running process can lower without
# CAP_SYS_RESOURCE, then execs the command. Anything that needs
# to RAISE limits (e.g. higher --nofile for huge concurrent loads)
# should be set on `docker run` via `--ulimit nofile=...` and is
# documented in the README.
set -e

# No core dumps from the worker — containers shouldn't write
# coredumps to the filesystem layer.
ulimit -c 0 2>/dev/null || true

# Cap address-space, file size, and process count at sane defaults
# so a runaway gcc invocation in /api/generate can't pin the host.
# These are advisory; the OPENVINCI_GCC_TIMEOUT_S timeout in
# backend/gen/compile.py is the real seat-belt.
ulimit -f $((512 * 1024)) 2>/dev/null || true   # max file size: 512 MB
ulimit -u 1024             2>/dev/null || true  # processes/threads
                                                # (pytest forks lots of gcc when
                                                #  running verify.sh; 256 was
                                                #  too tight for that path)

exec "$@"
