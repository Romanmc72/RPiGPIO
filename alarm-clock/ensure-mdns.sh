#!/usr/bin/env bash
# ensure-mdns.sh : make alarmclock.local survive reboots and transient mDNS failures
# Run once (with sudo or as pi with sudo privs) to configure permanent auto-heal:
#   ./ensure-mdns.sh          # or sudo ./ensure-mdns.sh
# Idempotent ; safe to re-run.
set -euo pipefail

HOSTNAME_DESIRED="alarmclock"
MDNS_NAME="${HOSTNAME_DESIRED}.local"
AVAHI_CONF="/etc/avahi/avahi-daemon.conf"
OVERRIDE_DIR="/etc/systemd/system/avahi-daemon.service.d"
OVERRIDE_FILE="${OVERRIDE_DIR}/10-auto-heal.conf"
HEAL_SCRIPT="/usr/local/bin/alarmclock-mdns-heal.sh"
MONITOR_SERVICE="/etc/systemd/system/alarmclock-mdns-monitor.service"
MONITOR_TIMER="/etc/systemd/system/alarmclock-mdns-monitor.timer"
FALLBACK_SERVICE="/etc/systemd/system/alarmclock-mdns-fallback.service"
FALLBACK_SCRIPT="/usr/local/bin/alarmclock-mdns-fallback.py"

need_sudo() {
  if [[ $EUID -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      echo "Re-execing with sudo..."
      exec sudo bash "$0" "$@"
    else
      echo "ERROR: must run as root" >&2; exit 1
    fi
  fi
}

# Only require sudo for system-modifying steps; allow --check without root
if [[ "${1:-}" != "--check" ]]; then
  # we will call sudo inside individual steps if not root, so don't force exec here
  true
fi

run_sudo() {
  if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

echo "[ensure-mdns] Ensuring hostname is ${HOSTNAME_DESIRED}..."

# 1. /etc/hosts — ensure 127.0.1.1 maps to alarmclock (handle raspberrypi or missing)
if grep -qE '^127\.0\.1\.1\s+' /etc/hosts; then
  run_sudo sed -i -E "s/^127\.0\.1\.1\s+.*/127.0.1.1\t${HOSTNAME_DESIRED}/" /etc/hosts
else
  echo -e "127.0.1.1\t${HOSTNAME_DESIRED}" | run_sudo tee -a /etc/hosts >/dev/null
fi

# 2. hostnamectl
if [[ "$(cat /etc/hostname 2>/dev/null | tr -d ' \n')" != "${HOSTNAME_DESIRED}" ]] || [[ "$(hostname)" != "${HOSTNAME_DESIRED}" ]]; then
  run_sudo hostnamectl set-hostname "${HOSTNAME_DESIRED}"
  echo "[ensure-mdns] hostname set to ${HOSTNAME_DESIRED}"
else
  echo "[ensure-mdns] hostname already ${HOSTNAME_DESIRED}"
fi

# 3. Pin avahi host-name explicitly so it doesn't depend on DHCP hostname
echo "[ensure-mdns] Configuring ${AVAHI_CONF} host-name=${HOSTNAME_DESIRED}..."
if grep -qE '^\s*#?\s*host-name=' "${AVAHI_CONF}"; then
  run_sudo sed -i -E "s/^\s*#?\s*host-name=.*/host-name=${HOSTNAME_DESIRED}/" "${AVAHI_CONF}"
else
  # insert under [server] section
  run_sudo awk -v hn="host-name=${HOSTNAME_DESIRED}" '
    /^\[server\]/ {print; print hn; inserted=1; next}
    inserted && /^\[/ {inserted=0}
    {print}
    END {if (!inserted && !found) print "[server]\n" hn}
  ' "${AVAHI_CONF}" > /tmp/avahi.conf.new && run_sudo mv /tmp/avahi.conf.new "${AVAHI_CONF}"
  # if awk approach duplicated, ensure single entry — simpler fallback:
  if ! grep -q "^host-name=${HOSTNAME_DESIRED}" "${AVAHI_CONF}"; then
    run_sudo sed -i "/^\[server\]/a host-name=${HOSTNAME_DESIRED}" "${AVAHI_CONF}"
  fi
fi
# Ensure use-ipv4/ipv6 remain yes (already) and publish settings sane
# Disable rate-limit aggressively? keep existing

# 4. Systemd override: make avahi-daemon auto-restart on failure
echo "[ensure-mdns] Installing avahi-daemon auto-restart override..."
run_sudo mkdir -p "${OVERRIDE_DIR}"
run_sudo tee "${OVERRIDE_FILE}" >/dev/null <<'OVERRIDE'
[Unit]
StartLimitIntervalSec=60
StartLimitBurst=10

[Service]
Restart=always
RestartSec=3
# If avahi exits or crashes, restart quickly. Also restart on failure from watchdog.
OVERRIDE
run_sudo chmod 644 "${OVERRIDE_FILE}"

# 5. Healing script — checks that avahi is advertising the desired name
echo "[ensure-mdns] Installing heal script at ${HEAL_SCRIPT}..."
run_sudo tee "${HEAL_SCRIPT}" >/dev/null <<'HEAL'
#!/usr/bin/env bash
set -uo pipefail
HOSTNAME_DESIRED="alarmclock"
EXPECTED="${HOSTNAME_DESIRED}.local"
# Log to journal via echo (systemd will capture)
log() { echo "[mdns-heal] $*"; }

# Check 1: avahi-daemon active?
if ! systemctl is-active --quiet avahi-daemon; then
  log "avahi-daemon not active, restarting..."
  systemctl restart avahi-daemon || true
  sleep 3
fi

# Check 2: hostname conflict — avahi appends -N on conflict (alarmclock-2, -3, etc.)
# Detect via systemctl status line "running [xxx.local]" or journal
STATUS_HOST="$(systemctl status avahi-daemon 2>/dev/null | grep -oE 'running \[[^]]+\.local\]' | grep -oE '[a-z0-9-]+\.local' | head -1 || true)"
if [[ -n "${STATUS_HOST}" && "${STATUS_HOST}" != "${EXPECTED}" ]]; then
  log "avahi is advertising ${STATUS_HOST} instead of ${EXPECTED} (conflict), restarting..."
  # Try to clear stale cache: restart avahi-daemon with fresh probe
  systemctl restart avahi-daemon || true
  sleep 5
  # If still conflicted, force flush by stopping, waiting, starting
  STATUS_HOST2="$(systemctl status avahi-daemon 2>/dev/null | grep -oE 'running \[[^]]+\.local\]' | grep -oE '[a-z0-9-]+\.local' | head -1 || true)"
  if [[ -n "${STATUS_HOST2}" && "${STATUS_HOST2}" != "${EXPECTED}" ]]; then
    log "still advertising ${STATUS_HOST2}, doing stop/start cycle..."
    systemctl stop avahi-daemon || true
    sleep 2
    # Remove stale cache if any (avahi keeps cache in /var/run/avahi-daemon?)
    rm -f /var/run/avahi-daemon/pid 2>/dev/null || true
    systemctl start avahi-daemon || true
    sleep 3
  fi
fi

# Check 3: recent journal indicates Host name conflict or failure
if journalctl -u avahi-daemon --since "2 minutes ago" --no-pager 2>/dev/null | grep -q "Host name conflict"; then
  log "journal shows Host name conflict in last 2m, ensuring restart..."
  # Already handled above, but ensure one more restart if still conflicted
  STATUS_HOST3="$(systemctl status avahi-daemon 2>/dev/null | grep -oE 'running \[[^]]+\.local\]' | grep -oE '[a-z0-9-]+\.local' | head -1 || true)"
  if [[ "${STATUS_HOST3}" != "${EXPECTED}" ]]; then
    systemctl restart avahi-daemon || true
  fi
fi

# Check 4: interface flapped — avahi withdraws interface on dhcp flap; ensure it re-joins
# If wlan0 has an IP but avahi has "Interface wlan0.* no longer relevant" recently, restart
if journalctl -u avahi-daemon --since "5 minutes ago" --no-pager 2>/dev/null | grep -q "no longer relevant for mDNS"; then
  if ip -4 addr show wlan0 2>/dev/null | grep -q "inet "; then
    # wlan0 has IP but avahi thought it was gone — nudge it
    if ! systemctl status avahi-daemon 2>/dev/null | grep -q "Registering new address record for.*on wlan0"; then
      :
    fi
    # Lightweight heal: SIGHUP reload often enough, but restart is more reliable on flaky wlan
    log "detected interface flap, reloading avahi-daemon..."
    systemctl reload avahi-daemon 2>/dev/null || systemctl restart avahi-daemon || true
  fi
fi

# Final check: is fallback needed? If after heals still not EXPECTED, start fallback publisher
STATUS_FINAL="$(systemctl status avahi-daemon 2>/dev/null | grep -oE 'running \[[^]]+\.local\]' | grep -oE '[a-z0-9-]+\.local' | head -1 || true)"
if [[ -n "${STATUS_FINAL}" && "${STATUS_FINAL}" != "${EXPECTED}" ]]; then
  log "avahi still not on ${EXPECTED} (is ${STATUS_FINAL}), starting fallback publisher..."
  systemctl start alarmclock-mdns-fallback.service 2>/dev/null || true
else
  # avahi healthy — ensure fallback is not needed but leave it running as redundant (optional)
  # We keep fallback running redundantly; it will also advertise alarmclock.local
  if systemctl is-active --quiet alarmclock-mdns-fallback.service; then
    : # keep running for redundancy
  fi
fi

# Ensure avahi is enabled to survive reboots
systemctl is-enabled --quiet avahi-daemon 2>/dev/null || systemctl enable avahi-daemon 2>/dev/null || true

HEAL
run_sudo chmod +x "${HEAL_SCRIPT}"

# 6. Monitor service — runs heal script every 30s via timer, plus on boot
echo "[ensure-mdns] Installing monitor timer/service..."
run_sudo tee "${MONITOR_SERVICE}" >/dev/null <<'SVC'
[Unit]
Description=AlarmClock mDNS heal — ensures alarmclock.local is advertised
After=network-online.target avahi-daemon.service
Wants=network-online.target avahi-daemon.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/alarmclock-mdns-heal.sh
SVC

run_sudo tee "${MONITOR_TIMER}" >/dev/null <<'TIMER'
[Unit]
Description=Run AlarmClock mDNS heal every 30 seconds

[Timer]
OnBootSec=30
OnUnitActiveSec=30
Unit=alarmclock-mdns-monitor.service

[Install]
WantedBy=timers.target
TIMER

run_sudo chmod 644 "${MONITOR_SERVICE}" "${MONITOR_TIMER}"

# 7. Fallback mDNS publisher — pure-Python zeroconf, redundant to avahi-daemon
# Advertises A record for alarmclock.local and _http._tcp service so even if avahi
# is wedged, the name remains resolvable.
echo "[ensure-mdns] Installing fallback publisher..."
run_sudo tee "${FALLBACK_SCRIPT}" >/dev/null <<'PYEOF'
#!/usr/bin/env python3
"""Fallback mDNS publisher — advertises alarmclock.local via zeroconf.
Runs even if avahi-daemon is down. Uses python3-zeroconf if available,
otherwise falls back to raw UDP mDNS announcements (minimal).
"""
import socket
import time
import threading
import sys

HOSTNAME = "alarmclock"
SERVICE_TYPE = "_http._tcp.local."
PORT = 80

def get_ip():
    # Prefer wlan0 IPv4
    try:
        # Use routing trick to get preferred outbound IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip.startswith("127."):
            raise Exception("loopback")
        return ip
    except Exception:
        pass
    # Fallback: parse ip addr
    import subprocess, re
    try:
        out = subprocess.check_output(["ip", "-4", "addr", "show", "wlan0"], text=True)
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "192.168.0.20"

def run_zeroconf():
    from zeroconf import Zeroconf, ServiceInfo
    ip = get_ip()
    print(f"[fallback] zeroconf publishing {HOSTNAME}.local -> {ip}", flush=True)
    desc = {}
    info = ServiceInfo(
        SERVICE_TYPE,
        f"{HOSTNAME}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(ip)],
        port=PORT,
        properties=desc,
        server=f"{HOSTNAME}.local.",
    )
    zc = Zeroconf()
    zc.register_service(info)
    print(f"[fallback] registered {HOSTNAME}.local on {ip}:80", flush=True)
    try:
        while True:
            time.sleep(60)
            # refresh IP if changed
            new_ip = get_ip()
            if new_ip != ip:
                print(f"[fallback] IP changed {ip} -> {new_ip}, re-registering", flush=True)
                zc.unregister_service(info)
                info = ServiceInfo(
                    SERVICE_TYPE,
                    f"{HOSTNAME}.{SERVICE_TYPE}",
                    addresses=[socket.inet_aton(new_ip)],
                    port=PORT,
                    properties=desc,
                    server=f"{HOSTNAME}.local.",
                )
                zc.register_service(info)
                ip = new_ip
    except KeyboardInterrupt:
        pass
    finally:
        zc.unregister_service(info)
        zc.close()

def run_raw_mdns():
    """Minimal raw mDNS responder — answers A queries for alarmclock.local.
    This is a last-resort when zeroconf library is unavailable.
    """
    import struct
    ip = get_ip()
    print(f"[fallback] raw mDNS publishing {HOSTNAME}.local -> {ip} (zeroconf not installed)", flush=True)
    # Join mDNS multicast group 224.0.0.251:5353 and respond to queries
    MCAST_GRP = "224.0.0.251"
    MCAST_PORT = 5353
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except Exception:
        pass
    sock.bind(("", MCAST_PORT))
    # Join multicast
    mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    # Also need to allow multicast loop
    sock.settimeout(1.0)
    hostname_labels = HOSTNAME.encode() + b"\x05local\x00"
    # Actually encode as DNS labels: \x0aalarmclock\x05local\x00
    qname = b"\x0a" + HOSTNAME.encode() + b"\x05local\x00"
    while True:
        try:
            data, addr = sock.recvfrom(9000)
        except socket.timeout:
            # Periodically announce gratuitously (unsolicited response)
            # Build unsolicited mDNS response
            try:
                # Header: id 0, flags 0x8400 (response, authoritative), 0 questions, 1 answer
                header = struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0)
                # Answer: name, type A(1), class IN(1) + cache flush bit 0x8001, ttl 120, rdlen 4, rdata
                answer = qname + struct.pack("!HHIH", 1, 0x8001, 120, 4) + socket.inet_aton(get_ip())
                sock.sendto(header + answer, (MCAST_GRP, MCAST_PORT))
            except Exception as e:
                print(f"[fallback] announce failed: {e}", flush=True)
            continue
        try:
            if len(data) < 12:
                continue
            # Parse query: check if QNAME matches alarmclock.local and QTYPE A or ANY
            # Simple: if qname bytes in data, respond
            if qname.lower() not in data.lower():
                continue
            # Check QR bit — only respond to queries (QR=0)
            flags = struct.unpack("!H", data[2:4])[0]
            if flags & 0x8000:
                continue
            # Build response copying transaction ID
            txid = data[0:2]
            header = struct.pack("!HHHHHH", struct.unpack("!H", txid)[0], 0x8400, 0, 1, 0, 0)
            answer = qname + struct.pack("!HHIH", 1, 0x8001, 120, 4) + socket.inet_aton(get_ip())
            # For good measure also add question echo? minimal response works with 0 questions
            sock.sendto(header + answer, (MCAST_GRP, MCAST_PORT))
        except Exception as e:
            print(f"[fallback] handle query failed: {e}", flush=True)

if __name__ == "__main__":
    try:
        import zeroconf  # noqa: F401
        run_zeroconf()
    except ImportError:
        # Try to handle without lib — use raw
        print("[fallback] python3-zeroconf not found, using raw mDNS responder", flush=True)
        run_raw_mdns()
    except Exception as e:
        print(f"[fallback] zeroconf failed: {e}, falling back to raw", flush=True)
        try:
            run_raw_mdns()
        except Exception as e2:
            print(f"[fallback] raw also failed: {e2}", flush=True)
            sys.exit(1)
PYEOF
run_sudo chmod +x "${FALLBACK_SCRIPT}"

run_sudo tee "${FALLBACK_SERVICE}" >/dev/null <<'FBSVC'
[Unit]
Description=AlarmClock fallback mDNS publisher (redundant to avahi-daemon)
After=network-online.target avahi-daemon.service
Wants=network-online.target
# Keep running even if avahi is down — provides redundancy

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/alarmclock-mdns-fallback.py
Restart=always
RestartSec=5
User=root
# Also run as pi if root not desired: User=pi
# Need network capabilities
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
FBSVC
run_sudo chmod 644 "${FALLBACK_SERVICE}"

# 8. Ensure alarm_clock_server.service ordering — make it want avahi
ALARM_SVC="/etc/systemd/system/alarm_clock_server.service"
if [[ -f "${ALARM_SVC}" ]] && ! grep -q "avahi-daemon" "${ALARM_SVC}"; then
  echo "[ensure-mdns] Patching alarm_clock_server.service to depend on avahi..."
  # Add After and Wants if missing
  if grep -q "^After=" "${ALARM_SVC}"; then
    run_sudo sed -i 's/^After=.*/After=network-online.target avahi-daemon.service/' "${ALARM_SVC}"
  else
    run_sudo sed -i '/^\[Unit\]/a After=network-online.target avahi-daemon.service' "${ALARM_SVC}"
  fi
  if ! grep -q "Wants=" "${ALARM_SVC}"; then
    run_sudo sed -i '/^After=/a Wants=avahi-daemon.service' "${ALARM_SVC}"
  fi
fi

# 9. Try to install python3-zeroconf for robust fallback (best-effort, don't fail setup)
if ! python3 -c "import zeroconf" 2>/dev/null; then
  echo "[ensure-mdns] Attempting to install python3-zeroconf (best-effort)..."
  run_sudo apt-get update -qq 2>/dev/null || true
  run_sudo apt-get install -y python3-zeroconf 2>/dev/null || pip3 install zeroconf 2>/dev/null || echo "[ensure-mdns] zeroconf install failed — fallback will use raw UDP responder"
fi

# 10. Reload systemd and enable everything
echo "[ensure-mdns] Reloading systemd..."
run_sudo systemctl daemon-reload
run_sudo systemctl enable avahi-daemon.service 2>/dev/null || true
run_sudo systemctl enable avahi-daemon.socket 2>/dev/null || true
run_sudo systemctl enable alarmclock-mdns-monitor.timer 2>/dev/null || true
run_sudo systemctl enable alarmclock-mdns-fallback.service 2>/dev/null || true

# Start / restart services
run_sudo systemctl restart avahi-daemon 2>/dev/null || run_sudo systemctl start avahi-daemon || true
sleep 2
run_sudo systemctl start alarmclock-mdns-monitor.timer 2>/dev/null || true
run_sudo systemctl start alarmclock-mdns-monitor.service 2>/dev/null || true  # one-shot now
run_sudo systemctl restart alarmclock-mdns-fallback.service 2>/dev/null || run_sudo systemctl start alarmclock-mdns-fallback.service || true
run_sudo systemctl daemon-reload 2>/dev/null || true

# Also ensure alarm_clock_server still enabled
if [[ -f "${ALARM_SVC}" ]]; then
  run_sudo systemctl enable alarm_clock_server.service 2>/dev/null || true
fi

echo ""
echo "[ensure-mdns] Done. Status:"
systemctl is-active avahi-daemon 2>&1 | sed 's/^/  avahi-daemon: /' || true
systemctl status avahi-daemon --no-pager 2>&1 | grep -E "Active:|running \[" | sed 's/^/  /' || true
systemctl is-active alarmclock-mdns-fallback.service 2>&1 | sed 's/^/  fallback: /' || true
systemctl is-active alarmclock-mdns-monitor.timer 2>&1 | sed 's/^/  monitor timer: /' || true
echo "  hostname: $(cat /etc/hostname 2>/dev/null) / $(hostname)"
grep -E "host-name" "${AVAHI_CONF}" 2>/dev/null | sed 's/^/  avahi conf: /' || true
echo ""
echo "Verify with: getent hosts ${MDNS_NAME}  or  ping -c1 ${MDNS_NAME}"
echo "Logs: journalctl -u avahi-daemon -u alarmclock-mdns-fallback -u alarmclock-mdns-monitor --no-pager -n 50"
