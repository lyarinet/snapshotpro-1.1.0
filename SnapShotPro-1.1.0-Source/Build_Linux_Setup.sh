#!/usr/bin/env bash
set -eu
exec "$(dirname "$0")/Build_Standalone_Mac_Linux.sh" --linux "$@"
