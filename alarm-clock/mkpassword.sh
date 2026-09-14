#!/usr/bin/env bash

set -euo pipefail

main() {
  if [[ "$#" != "1" ]] then
    echo 'Arg 1: <password string> required, only 1 arg allowed.'
    exit 1
  fi
  PASSWORD_STRING="$1"
  printf '%s' "$PASSWORD_STRING" | sha256sum | cut -d' ' -f1
}

main "$@"
