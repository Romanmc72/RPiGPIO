#!/usr/bin/env bash
# Restarts the daemon background service. Useful if a
# change was just made and you don't want a full reboot.

set -euo pipefail

main() {
  sudo systemctl daemon-reload
  sudo systemctl restart led_schedule.service
}

main
