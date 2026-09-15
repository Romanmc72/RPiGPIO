#!/usr/bin/env bash

set -euo pipefail

main() {
  SERVICE_NAME="$1"
  sudo journalctl -u "$SERVICE_NAME" -f
}

main "$@"
