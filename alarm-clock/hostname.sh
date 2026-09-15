#!/usr/bin/env bash

set -euo pipefail

main() {
  sudo sed -i 's/127.0.1.1\s\+raspberrypi/127.0.1.1\talarmclock/' /etc/hosts
  sudo hostnamectl set-hostname alarmclock
  sudo systemctl restart avahi-daemon
}

main "$@"
