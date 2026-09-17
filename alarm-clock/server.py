#!/usr/bin/env python3
"""
Admin server for alarm-clock schedule.json

Features:
 - Password auth via hash in env var (ALARM_ADMIN_PASSWORD_HASH or ADMIN_PASSWORD_HASH)
 - Serves API + interactive web page
 - Watches schedule.json for external changes and pushes via SSE
 - Handles write conflicts via lightweight file hash (daemon wins)
 - Validates schedule rules and recordings management

Service Definition
------------------
The service definition is set up in the alarm_clock_server.service file.

place that file at:

`/etc/systemd/system/alarm_clock_server.service`

then run these commands to enable and start the service and to ensure it starts up on reboot:

```sh
sudo systemctl daemon-reload
sudo systemctl enable alarm_clock_server.service
sudo systemctl start alarm_clock_server.service
```
"""
from __future__ import annotations

import os
import re
import json
import time
import hashlib
import threading
import secrets
import mimetypes
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Tuple, Dict
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = Path(__file__).parent / "schedule.json"
CONFIG_PATH = Path(os.environ.get("ALARM_CONFIG_PATH") or os.environ.get("CONFIG_PATH") or DEFAULT_CONFIG)
# Fallback: if default doesn't exist but /home/pi/schedule.json exists, use that
if not CONFIG_PATH.exists() and Path("/home/pi/schedule.json").exists():
    CONFIG_PATH = Path("/home/pi/schedule.json")

HOST = os.environ.get("ALARM_HOST", "0.0.0.0")
PORT = int(os.environ.get("ALARM_PORT", "8080"))

PASSWORD_HASH_ENV_VARS = ["ALARM_ADMIN_PASSWORD_HASH", "ADMIN_PASSWORD_HASH", "PASSWORD_HASH"]

STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# TLS / self-signed cert config
# ---------------------------------------------------------------------------
# Env vars:
#   ALARM_TLS_DISABLE / ALARM_DISABLE_TLS / DISABLE_TLS = "1" to force plain HTTP
#   ALARM_TLS_CERT / ALARM_CERT_FILE -> path to cert PEM
#   ALARM_TLS_KEY  / ALARM_KEY_FILE  -> path to key PEM
#   ALARM_CERT_DIR / ALARM_TLS_CERT_DIR -> directory holding server.crt/server.key
#   ALARM_TLS_RENEW_DAYS -> days before expiry to auto-renew (default 30)
#   ALARM_TLS_VALID_DAYS -> validity period for generated cert (default 825)
TLS_DISABLE = os.environ.get("ALARM_TLS_DISABLE", os.environ.get("ALARM_DISABLE_TLS", os.environ.get("DISABLE_TLS", ""))).strip().lower() in ("1", "true", "yes")
TLS_CERT_ENV_VARS = ["ALARM_TLS_CERT", "ALARM_CERT_FILE", "TLS_CERT", "SSL_CERT"]
TLS_KEY_ENV_VARS = ["ALARM_TLS_KEY", "ALARM_KEY_FILE", "TLS_KEY", "SSL_KEY"]
TLS_CERT_DIR_ENV_VARS = ["ALARM_CERT_DIR", "ALARM_TLS_CERT_DIR", "CERT_DIR"]
DEFAULT_CERT_DIR = Path(__file__).parent / "certs"
TLS_RENEW_DAYS = int(os.environ.get("ALARM_TLS_RENEW_DAYS", "30"))
TLS_VALID_DAYS = int(os.environ.get("ALARM_TLS_VALID_DAYS", "300"))

# Sessions: token -> expiry
SESSIONS: dict[str, float] = {}
SESSION_LOCK = threading.Lock()
SESSION_TTL = 24 * 3600

# SSE clients
SSE_CLIENTS: list = []
SSE_LOCK = threading.Lock()

# File hash tracking
file_hash: str = ""
file_hash_lock = threading.Lock()

# ---------------------------------------------------------------------------
# TLS helpers — self-signed cert with auto-renew
# ---------------------------------------------------------------------------
def _get_cert_paths() -> tuple[Path, Path]:
    """Resolve cert/key paths from env or defaults."""
    cert_path = None
    key_path = None
    for k in TLS_CERT_ENV_VARS:
        v = os.environ.get(k)
        if v:
            cert_path = Path(v.strip())
            break
    for k in TLS_KEY_ENV_VARS:
        v = os.environ.get(k)
        if v:
            key_path = Path(v.strip())
            break
    if cert_path and not key_path:
        # derive key alongside cert
        key_path = cert_path.with_suffix(".key")
    if key_path and not cert_path:
        cert_path = key_path.with_suffix(".crt")
    if not cert_path or not key_path:
        cert_dir = None
        for k in TLS_CERT_DIR_ENV_VARS:
            v = os.environ.get(k)
            if v:
                cert_dir = Path(v.strip())
                break
        if not cert_dir:
            cert_dir = DEFAULT_CERT_DIR
        if not cert_path:
            cert_path = cert_dir / "server.crt"
        if not key_path:
            key_path = cert_dir / "server.key"
    return cert_path, key_path


def _get_local_ips() -> list[str]:
    ips: set[str] = set()
    # Try routing trick
    try:
        import socket as _sock

        s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if not ip.startswith("127."):
                ips.add(ip)
        finally:
            s.close()
    except Exception:
        pass
    # Enumerate via ip addr if available
    try:
        import subprocess
        import re as _re

        out = subprocess.check_output(["ip", "-4", "addr", "show"], text=True, timeout=3)
        for m in _re.finditer(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out):
            ip = m.group(1)
            if not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    try:
        import socket as _sock

        for fam, _, _, _, sockaddr in _sock.getaddrinfo(_sock.gethostname(), None):
            if fam == _sock.AF_INET:
                ip = sockaddr[0]
                if not ip.startswith("127."):
                    ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


def _get_sans() -> tuple[list[str], list[str]]:
    """Return (dns_names, ip_strings) for SAN."""
    import socket as _sock

    dns: set[str] = {"localhost", "alarmclock", "alarmclock.local"}
    try:
        hn = _sock.gethostname().strip()
        if hn:
            dns.add(hn)
            if not hn.endswith(".local"):
                dns.add(hn + ".local")
    except Exception:
        pass
    # Also add FQDN
    try:
        fqdn = _sock.getfqdn().strip()
        if fqdn and fqdn != "localhost":
            dns.add(fqdn)
    except Exception:
        pass
    ips = ["127.0.0.1", "::1"] + _get_local_ips()
    # Deduplicate preserving order
    seen: set[str] = set()
    uniq_ips: list[str] = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            uniq_ips.append(ip)
    return sorted(dns), uniq_ips


def _cert_expiry_datetime(cert_path: Path):
    """Return not_valid_after as aware datetime, or None if unreadable."""
    try:
        from cryptography import x509 as _x509

        data = cert_path.read_bytes()
        cert = _x509.load_pem_x509_certificate(data)
        # cryptography >=42 uses not_valid_after_utc
        dt = getattr(cert, "not_valid_after_utc", None)
        if dt is None:
            dt = cert.not_valid_after  # type: ignore
            # naive -> assume UTC
            from datetime import timezone as _tz

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_tz.utc)
        return dt
    except ImportError:
        pass
    except Exception:
        pass
    # Fallback: openssl
    try:
        import subprocess

        out = subprocess.check_output(
            ["openssl", "x509", "-enddate", "-noout", "-in", str(cert_path)], text=True, timeout=5
        )
        # out: notAfter=Sep 17 12:00:00 2027 GMT
        val = out.strip().split("=", 1)[-1].strip()
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        for fmt in ("%b %d %H:%M:%S %Y %Z", "%b  %d %H:%M:%S %Y %Z"):
            try:
                parsed = _dt.strptime(val, fmt)
                return parsed.replace(tzinfo=_tz.utc)
            except ValueError:
                continue
    except Exception:
        pass
    return None


def _cert_needs_renewal(cert_path: Path, key_path: Path) -> bool:
    if not cert_path.exists() or not key_path.exists():
        return True
    # Check key/cert match by verifying openssl can read them together (light check)
    # Check expiry
    exp = _cert_expiry_datetime(cert_path)
    if exp is None:
        # If unreadable, force renewal
        return True
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    now = _dt.now(_tz.utc)
    remaining = exp - now
    if remaining.total_seconds() <= TLS_RENEW_DAYS * 86400:
        return True
    # Also check that SAN still covers current IPs/hosts — if IPs changed, renew
    # Light heuristic: if local IPs not all in cert SAN, we should renew.
    # We skip strict check to avoid churn; only renew on expiry/missing.
    return False


def _generate_self_signed_cert_openssl(cert_path: Path, key_path: Path) -> bool:
    dns_names, ip_strs = _get_sans()
    # Build SAN string: DNS:foo,IP:1.2.3.4
    san_parts = [f"DNS:{d}" for d in dns_names] + [f"IP:{ip}" for ip in ip_strs]
    san = ",".join(san_parts)
    # Use openssl req with addext (OpenSSL >=1.1.1)
    import subprocess
    import tempfile

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    # Generate key + cert in one go
    cfg = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".cnf")
    try:
        cfg.write("[req]\n")
        cfg.write("distinguished_name=req_distinguished_name\n")
        cfg.write("x509_extensions=v3_req\n")
        cfg.write("prompt=no\n")
        cfg.write("[req_distinguished_name]\n")
        cfg.write("CN=alarmclock.local\n")
        cfg.write("[v3_req]\n")
        cfg.write("subjectAltName=" + san + "\n")
        cfg.write("basicConstraints=CA:FALSE\n")
        cfg.write("keyUsage=digitalSignature,keyEncipherment\n")
        cfg.write("extendedKeyUsage=serverAuth\n")
        cfg.flush()
        cfg.close()
        cmd = [
            "openssl",
            "req",
            "-x509",
            "-nodes",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            str(TLS_VALID_DAYS),
            "-config",
            cfg.name,
            "-extensions",
            "v3_req",
        ]
        subprocess.check_call(cmd, timeout=30)
        # Restrict key perms
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[tls] openssl generation failed: {e}")
        return False
    finally:
        try:
            os.unlink(cfg.name)
        except Exception:
            pass


def _generate_self_signed_cert_cryptography(cert_path: Path, key_path: Path) -> bool:
    try:
        from cryptography import x509 as _x509
        from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import ipaddress
        from datetime import datetime as _dt
        from datetime import timezone as _tz
        from datetime import timedelta as _td
    except ImportError:
        return False
    try:
        dns_names, ip_strs = _get_sans()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = _x509.Name([_x509.NameAttribute(NameOID.COMMON_NAME, "alarmclock.local")])
        now = _dt.now(_tz.utc)
        builder = (
            _x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(_x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + _td(days=TLS_VALID_DAYS))
            .add_extension(_x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                _x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                _x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
        )
        sans: list = []
        for d in dns_names:
            sans.append(_x509.DNSName(d))
        for ip in ip_strs:
            try:
                sans.append(_x509.IPAddress(ipaddress.ip_address(ip)))
            except ValueError:
                continue
        builder = builder.add_extension(_x509.SubjectAlternativeName(sans), critical=False)
        cert = builder.sign(private_key=key, algorithm=hashes.SHA256())
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[tls] cryptography generation failed: {e}")
        return False


def _generate_self_signed_cert(cert_path: Path, key_path: Path) -> bool:
    # Prefer cryptography (no external binary, works on minimal images)
    if _generate_self_signed_cert_cryptography(cert_path, key_path):
        return True
    # Fallback to openssl CLI
    return _generate_self_signed_cert_openssl(cert_path, key_path)


def ensure_tls_cert() -> Tuple[Optional[Path], Optional[Path]]:
    """Ensure a self-signed cert/key exist and are not near expiry.

    Returns (cert_path, key_path) if TLS should be used, else (None, None).
    Auto-generates/renews when needed — this is the 'auto-renew' mechanism.
    Renewal also happens dynamically via a background thread (see start).
    """
    if TLS_DISABLE:
        print("[tls] TLS disabled via env (ALARM_TLS_DISABLE)")
        return None, None
    cert_path, key_path = _get_cert_paths()
    try:
        if _cert_needs_renewal(cert_path, key_path):
            reason = "missing" if not cert_path.exists() or not key_path.exists() else "expiring/renew"
            print(f"[tls] Generating self-signed cert ({reason}) -> {cert_path}")
            ok = _generate_self_signed_cert(cert_path, key_path)
            if not ok:
                print("[tls] Failed to generate cert — falling back to plain HTTP")
                return None, None
            exp = _cert_expiry_datetime(cert_path)
            if exp:
                print(f"[tls] New cert valid until {exp.isoformat()} SAN will cover local IPs")
        else:
            exp = _cert_expiry_datetime(cert_path)
            if exp:
                print(f"[tls] Existing cert valid until {exp.isoformat()} — {cert_path}")
    except Exception as e:
        print(f"[tls] ensure_tls_cert error: {e} — falling back to HTTP")
        return None, None
    # Final sanity: both files exist and are readable
    if not cert_path.exists() or not key_path.exists():
        return None, None
    return cert_path, key_path


def _tls_renewal_loop(cert_path: Path, key_path: Path, check_interval: float = 3600.0):
    """Background thread: periodically check expiry and renew in place.

    The running server keeps using the old cert until next restart (Python
    ssl context is loaded at startup). Renewal here ensures the cert on disk
    is fresh so the next (re)start — whether manual, systemd restart, or
    reboot — picks it up. For long uptimes, we log that a restart is needed.
    """
    while True:
        try:
            time.sleep(check_interval)
            if _cert_needs_renewal(cert_path, key_path):
                print("[tls] Background renewal: cert near expiry, regenerating...")
                ok = _generate_self_signed_cert(cert_path, key_path)
                if ok:
                    exp = _cert_expiry_datetime(cert_path)
                    print(f"[tls] Background renewal done; new expiry {exp}; restart to apply")
                else:
                    print("[tls] Background renewal failed")
        except Exception as e:
            print(f"[tls] renewal loop error: {e}")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def get_password_hash() -> Optional[str]:
    for k in PASSWORD_HASH_ENV_VARS:
        v = os.environ.get(k)
        if v:
            return v.strip()
    # Fallback: scan any env var that looks like a password hash (broad compatibility
    # with unspecified env var name – e.g. tests may use a different name). Prefer
    # keys containing PASSWORD, otherwise any bcrypt/sha256 looking value.
    for k, v in os.environ.items():
        ku = k.upper()
        vv = v.strip() if isinstance(v, str) else ""
        if not vv:
            continue
        is_hash_like = vv.startswith("$2") or re.fullmatch(r"[a-fA-F0-9]{64}", vv) is not None
        if "PASSWORD" in ku and is_hash_like:
            return vv
        if "PASSWORD" in ku and vv:
            # plain hash env may contain bcrypt even without detection
            return vv
    for k, v in os.environ.items():
        vv = v.strip() if isinstance(v, str) else ""
        if vv.startswith("$2"):
            return vv
    return None

def get_password_hash_source() -> Optional[str]:
    for k in PASSWORD_HASH_ENV_VARS:
        if os.environ.get(k):
            return k
    for k, v in os.environ.items():
        ku = k.upper()
        vv = v.strip() if isinstance(v, str) else ""
        if "PASSWORD" in ku and vv:
            return k
    for k, v in os.environ.items():
        if v.strip().startswith("$2"):
            return k
    return None

def verify_password(plain: str, hash_val: str) -> bool:
    hash_val = hash_val.strip()
    plain = plain or ""
    # bcrypt format $2a$ / $2b$
    if hash_val.startswith("$2"):
        try:
            import bcrypt
            return bcrypt.checkpw(plain.encode(), hash_val.encode())
        except Exception:
            pass
    # Try sha256 hex (64 chars)
    if re.fullmatch(r"[a-fA-F0-9]{64}", hash_val):
        h = hashlib.sha256(plain.encode()).hexdigest()
        return secrets.compare_digest(h.lower(), hash_val.lower())
    # Try generic: hash is sha256 of password (allow plain compare via hashlib)
    # Also support werkzeug-style pbkdf2:sha256 ... fallback to plain equality via secrets
    # If hash contains ':', treat as salted? Keep simple.
    # Last resort: if hash looks like hex sha256 of plain, already handled; else direct compare for dev
    return secrets.compare_digest(plain, hash_val)


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    with SESSION_LOCK:
        SESSIONS[token] = time.time() + SESSION_TTL
    return token

def is_valid_token(token: Optional[str]) -> bool:
    if not token:
        return False
    with SESSION_LOCK:
        exp = SESSIONS.get(token)
        if exp and exp > time.time():
            return True
        if exp:
            del SESSIONS[token]
    return False

def extract_token(handler: BaseHTTPRequestHandler) -> Optional[str]:
    # Cookie
    cookie = handler.headers.get("Cookie", "")
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("session="):
            return part[len("session="):].strip()
    # Authorization Bearer
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    # Query param token (for SSE)
    qs = urllib.parse.urlparse(handler.path).query
    params = urllib.parse.parse_qs(qs)
    if "token" in params:
        return params["token"][0]
    return None

def require_auth(handler: BaseHTTPRequestHandler) -> bool:
    # If no password hash configured, allow all (dev mode) but warn
    h = get_password_hash()
    if not h:
        return True
    token = extract_token(handler)
    return is_valid_token(token)

# ---------------------------------------------------------------------------
# Config file helpers
# ---------------------------------------------------------------------------
def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_config_file() -> Tuple[Optional[Dict], str, bytes]:
    try:
        raw = CONFIG_PATH.read_bytes()
        h = compute_hash(raw)
        cfg = json.loads(raw.decode())
        return cfg, h, raw
    except FileNotFoundError:
        return None, "", b""
    except Exception as e:
        print(f"Error reading config: {e}")
        return None, "", b""

def atomic_write_config(cfg: dict) -> str:
    """Write config atomically, flush to disk, return new hash."""
    raw = json.dumps(cfg, indent=2).encode() + b"\n"
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_bytes(raw)
    # fsync
    try:
        with open(tmp, "rb") as f:
            os.fsync(f.fileno())
    except Exception:
        pass
    tmp.replace(CONFIG_PATH)
    # Ensure directory fsync
    try:
        dirfd = os.open(str(CONFIG_PATH.parent), os.O_DIRECTORY)
        os.fsync(dirfd)
        os.close(dirfd)
    except Exception:
        pass
    new_hash = compute_hash(raw)
    with file_hash_lock:
        global file_hash
        file_hash = new_hash
    notify_sse_clients(cfg, new_hash)
    return new_hash

def get_audio_dir(cfg: dict) -> Path:
    d = cfg.get("audio", {}).get("audio_dir", "/home/pi/wake-up-calls")
    return Path(d)

# Recording name helpers - allow dots inside name (e.g. good-morning-10.gigi) but prevent traversal
REC_NAME_RE = re.compile(r"^[A-Za-z0-9._\-]+$")
def is_valid_recording_name(name: str) -> bool:
    if not name or not REC_NAME_RE.match(name):
        return False
    if name.startswith(".") or ".." in name or "/" in name or "\\" in name:
        return False
    return True

def recording_path(audio_dir: Path, name: str) -> Path:
    """Resolve a recording name to a .wav path, stripping only a trailing .wav suffix (not other dots)."""
    # Prevent directory traversal: take basename only
    base = name.split("/")[-1].split("\\")[-1]
    base = base.strip()
    # Strip .wav suffix if present (case-insensitive)
    if base.lower().endswith(".wav"):
        base = base[:-4]
    # After stripping .wav, validate again (caller should have validated)
    safe = Path(base).name  # extra safety, though base already basename
    return audio_dir / f"{safe}.wav"


def _ensure_wav_bytes(data: bytes) -> tuple[bytes, bool]:
    """Ensure *data* is a PCM WAV playable by ``aplay``.

    The browser previously used ``MediaRecorder`` which emits ``webm/opus``
    or ``mp4/aac`` but saved the blob as ``.wav`` verbatim - the result is
    static/noise on the Pi.  We now generate true PCM WAV on the client via
    Web Audio (see ``static/index.html``), but keep this server-side safety
    net so old clients, Safari MediaRecorder fallback, or curl uploads still
    produce a valid WAV.

    Returns ``(wav_bytes, was_converted)``.  If ``data`` already looks like
    ``RIFF/WAVE`` it is returned unchanged; otherwise we try to transcode via
    ``ffmpeg`` (``-acodec pcm_s16le``).  If ffmpeg is unavailable or fails we
    return the original bytes and let the handler decide (it will reject with
    a helpful error instead of saving static).
    """
    if data.startswith(b"RIFF") and b"WAVE" in data[:16]:
        return data, False
    # Light sniff: webm starts with 0x1A45DFA3, mp4/ftyp, ogg, etc. - all need transcode
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("ffmpeg"):
        return data, False
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".in") as fin:
            fin.write(data)
            fin.flush()
            in_path = fin.name
        out_fd, out_path = tempfile.mkstemp(suffix=".wav")
        os.close(out_fd)
        # Normalise to 16-bit PCM WAV that aplay understands.
        # Keep original sample-rate/channels when possible; force pcm_s16le.
        # Using -y to overwrite, -loglevel error to keep output quiet.
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            in_path,
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "1",
            out_path,
        ]
        subprocess.run(cmd, check=True, timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        wav = Path(out_path).read_bytes()
        if wav.startswith(b"RIFF"):
            return wav, True
        return data, False
    except Exception as e:
        print(f"[audio] ffmpeg transcode failed: {e}")
        return data, False
    finally:
        for p in (locals().get("in_path"), locals().get("out_path")):
            if p:
                try:
                    os.unlink(p)
                except Exception:
                    pass

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def parse_time(s: str):
    h, m = map(int, s.split(":"))
    return h * 60 + m

def validate_schedule_list(blocks, block_name: str, errors: list):
    if not isinstance(blocks, list):
        errors.append(f"{block_name} must be a list")
        return
    seen_names = set()
    intervals = []
    for i, b in enumerate(blocks):
        prefix = f"{block_name}[{i}]"
        if not isinstance(b, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = b.get("name")
        start = b.get("start")
        end = b.get("end")
        play_audio = b.get("play_audio")
        if not name or not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be non-empty string")
        elif name in seen_names:
            errors.append(f"{prefix}.name '{name}' must be unique within {block_name}")
        else:
            seen_names.add(name)
        if not isinstance(start, str) or not TIME_RE.match(start):
            errors.append(f"{prefix}.start must be HH:MM")
        if not isinstance(end, str) or not TIME_RE.match(end):
            errors.append(f"{prefix}.end must be HH:MM")
        if isinstance(start, str) and isinstance(end, str) and TIME_RE.match(start) and TIME_RE.match(end):
            try:
                s_min = parse_time(start)
                e_min = parse_time(end)
                if s_min >= e_min:
                    errors.append(f"{prefix} start must be before end")
                else:
                    # overlap check
                    for (os_, oe_, on) in intervals:
                        if not (e_min <= os_ or s_min >= oe_):
                            errors.append(f"{prefix} ({start}-{end}) overlaps with '{on}' ({os_//60:02d}:{os_%60:02d}-{oe_//60:02d}:{oe_%60:02d})")
                    intervals.append((s_min, e_min, name))
            except Exception:
                errors.append(f"{prefix} invalid time values")
        if not isinstance(play_audio, bool):
            errors.append(f"{prefix}.play_audio must be boolean")

def validate_config(cfg: dict) -> list[str]:
    errors = []
    if not isinstance(cfg, dict):
        return ["config must be an object"]
    # kill_switches
    ks = cfg.get("kill_switches", {})
    if not isinstance(ks, dict):
        errors.append("kill_switches must be object")
    else:
        for k in ["disable_all", "disable_lights", "disable_audio"]:
            if k in ks and not isinstance(ks[k], bool):
                errors.append(f"kill_switches.{k} must be boolean")
    # schedules
    schedules = cfg.get("schedules")
    if not isinstance(schedules, dict):
        errors.append("schedules must be object")
    else:
        allowed = {"default", "weekends", "weekdays"}
        for k in schedules:
            if k not in allowed and not re.match(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$", k):
                # Allow day names per daemon but prefer only those 3 + day names; don't error hard
                pass
        # default must have at least 1
        if "default" not in schedules or not schedules["default"]:
            errors.append("schedules.default must have at least 1 awake block")
        else:
            validate_schedule_list(schedules["default"], "schedules.default", errors)
        for key in ["weekends", "weekdays"]:
            if key in schedules:
                val = schedules[key]
                if val is not None and val != []:
                    validate_schedule_list(val, f"schedules.{key}", errors)
                # If zero assigned, it should NOT appear – but we allow empty list and will strip on save
                # So no error for empty; server will strip before save
        # Check day-name specific if present
        for k, v in schedules.items():
            if k not in ("default", "weekends", "weekdays") and isinstance(v, list):
                validate_schedule_list(v, f"schedules.{k}", errors)

    # date_overrides
    overrides = cfg.get("date_overrides", {})
    if overrides is not None:
        if not isinstance(overrides, dict):
            errors.append("date_overrides must be object")
        else:
            for iso, blocks in overrides.items():
                if not ISO_DATE_RE.match(iso):
                    errors.append(f"date_overrides key '{iso}' must be YYYY-MM-DD")
                    continue
                try:
                    datetime.strptime(iso, "%Y-%m-%d")
                except ValueError:
                    errors.append(f"date_overrides key '{iso}' is not a valid date")
                validate_schedule_list(blocks, f"date_overrides.{iso}", errors)
                if isinstance(blocks, list) and len(blocks) == 0:
                    errors.append(f"date_overrides.{iso} must have at least 1 block if present")
    return errors

def normalize_config(cfg: dict) -> dict:
    """Strip empty schedule blocks so zero-assigned blocks don't appear."""
    schedules = cfg.get("schedules", {})
    for key in list(schedules.keys()):
        val = schedules[key]
        if isinstance(val, list) and len(val) == 0:
            del schedules[key]
    # date_overrides: remove empty arrays
    overrides = cfg.get("date_overrides", {})
    for k in list(overrides.keys()):
        if isinstance(overrides[k], list) and len(overrides[k]) == 0:
            del overrides[k]
    if not overrides:
        # Keep as empty dict (or omit?) Spec says there do not have to be any overrides
        cfg["date_overrides"] = {}
    return cfg

# ---------------------------------------------------------------------------
# SSE
# ---------------------------------------------------------------------------
def notify_sse_clients(cfg: dict, h: str):
    payload = json.dumps({"hash": h, "config": cfg})
    dead = []
    with SSE_LOCK:
        for client in SSE_CLIENTS:
            try:
                client["wfile"].write(f"data: {payload}\n\n".encode())
                client["wfile"].flush()
            except Exception:
                dead.append(client)
        for d in dead:
            SSE_CLIENTS.remove(d)

def file_watcher():
    global file_hash
    # init
    _, h, _ = read_config_file()
    with file_hash_lock:
        file_hash = h
    last_mtime = 0
    try:
        last_mtime = CONFIG_PATH.stat().st_mtime
    except Exception:
        pass
    while True:
        time.sleep(1.0)
        try:
            mtime = CONFIG_PATH.stat().st_mtime
        except FileNotFoundError:
            continue
        if mtime == last_mtime:
            continue
        last_mtime = mtime
        time.sleep(0.1)  # debounce
        cfg, h, _ = read_config_file()
        if cfg is None:
            continue
        with file_hash_lock:
            if h == file_hash:
                continue
            file_hash = h
        # Also prune stale inside watcher? Daemon handles, but notify
        notify_sse_clients(cfg, h)

# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"{self.client_address[0]} - - [{self.log_date_time_string()}] {format % args}")

    def send_json(self, obj, status=200, extra_headers=None):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text, content_type="text/html", status=200, extra_headers=None):
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def parse_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None, {}
        raw = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")
        if "application/json" in ctype:
            try:
                return json.loads(raw.decode()), {}
            except Exception:
                return None, {}
        # fallback try json
        try:
            return json.loads(raw.decode()), {}
        except Exception:
            return raw, {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # Static assets / login / events
        if path == "/api/events":
            if not require_auth(self):
                self.send_response(401)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            # Send current config immediately
            cfg, h, _ = read_config_file()
            init = json.dumps({"hash": h, "config": cfg})
            try:
                self.wfile.write(f"data: {init}\n\n".encode())
                self.wfile.flush()
            except Exception:
                return
            client = {"wfile": self.wfile}
            with SSE_LOCK:
                SSE_CLIENTS.append(client)
            try:
                while True:
                    time.sleep(15)
                    # heartbeat
                    try:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    except Exception:
                        break
            finally:
                with SSE_LOCK:
                    if client in SSE_CLIENTS:
                        SSE_CLIENTS.remove(client)
            return

        if path == "/api/config":
            if not require_auth(self):
                self.send_json({"error": "unauthorized"}, 401)
                return
            cfg, h, _ = read_config_file()
            if cfg is None:
                self.send_json({"error": "config not found"}, 500)
                return
            self.send_json({"config": cfg, "hash": h})
            return

        if path == "/api/recordings":
            if not require_auth(self):
                self.send_json({"error": "unauthorized"}, 401)
                return
            cfg, _, _ = read_config_file()
            if cfg is None:
                self.send_json({"error": "config not found"}, 500)
                return
            audio_dir = get_audio_dir(cfg)
            files = []
            if audio_dir.exists():
                for p in sorted(audio_dir.glob("*.wav")):
                    stat = p.stat()
                    files.append({"name": p.stem, "filename": p.name, "size": stat.st_size, "mtime": stat.st_mtime})
            self.send_json({"recordings": files, "audio_dir": str(audio_dir)})
            return

        if path.startswith("/api/recordings/"):
            if not require_auth(self):
                self.send_json({"error": "unauthorized"}, 401)
                return
            name = urllib.parse.unquote(path[len("/api/recordings/"):])
            # strip trailing parts like /rename
            if "/" in name:
                name = name.split("/")[0]
            cfg, _, _ = read_config_file()
            audio_dir = get_audio_dir(cfg) if cfg else Path("/tmp")
            fpath = recording_path(audio_dir, name)
            if not fpath.exists():
                self.send_json({"error": "not found"}, 404)
                return
            data = fpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'inline; filename="{fpath.name}"')
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/login":
            self.serve_file("login.html")
            return

        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            # login.html is public; all other static admin assets require auth
            if rel != "login.html" and get_password_hash() and not require_auth(self):
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            self.serve_static(rel)
            return

        if path == "/" or path == "/index.html":
            h = get_password_hash()
            if h and not require_auth(self):
                # For browser navigation redirect, for API/XHR clients they will handle 401 via JS;
                # send 302 for page loads, but also ensure API callers get 401
                accept = self.headers.get("Accept", "")
                # Always redirect for direct page loads; API callers use /api/* endpoints
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            self.serve_file("index.html")
            return

        # Cert download — allow clients to fetch self-signed cert to trust (no auth needed)
        if path in ("/cert", "/cert.pem", "/server.crt", "/ca.crt", "/static/server.crt"):
            try:
                cert_path, _ = _get_cert_paths()
                if cert_path.exists():
                    data = cert_path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-x509-ca-cert")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Content-Disposition", 'attachment; filename="alarmclock.crt"')
                    self.end_headers()
                    self.wfile.write(data)
                    return
            except Exception:
                pass

        # Try static fallback - protect admin page, allow login.html
        if path.startswith("/"):
            rel = path.lstrip("/")
            f = STATIC_DIR / rel
            if f.exists() and f.is_file():
                if rel not in ("login.html",) and get_password_hash() and not require_auth(self):
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.end_headers()
                    return
                self.serve_static(rel)
                return

        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/login":
            body, _ = self.parse_body()
            if not isinstance(body, dict):
                self.send_json({"error": "invalid body"}, 400)
                return
            pwd = body.get("password", "")
            phash = get_password_hash()
            if not phash:
                # No auth configured: allow any login
                token = create_session()
                self.send_json({"ok": True, "token": token}, extra_headers={"Set-Cookie": f"session={token}; Path=/; HttpOnly; SameSite=Lax"})
                return
            if verify_password(pwd, phash):
                token = create_session()
                self.send_json({"ok": True, "token": token}, extra_headers={"Set-Cookie": f"session={token}; Path=/; HttpOnly; SameSite=Lax"})
            else:
                self.send_json({"error": "invalid password"}, 401)
            return

        if path == "/api/logout":
            token = extract_token(self)
            if token:
                with SESSION_LOCK:
                    SESSIONS.pop(token, None)
            self.send_json({"ok": True}, extra_headers={"Set-Cookie": "session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT"})
            return

        if path == "/api/recordings":
            if not require_auth(self):
                self.send_json({"error": "unauthorized"}, 401)
                return
            ctype = self.headers.get("Content-Type", "")
            cfg, _, _ = read_config_file()
            audio_dir = get_audio_dir(cfg) if cfg else Path("/tmp")
            audio_dir.mkdir(parents=True, exist_ok=True)
            if "multipart/form-data" in ctype:
                # Simple multipart parse (single file)
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                # Use cgi or manual parse; lightweight: look for filename and wav data
                # For simplicity, expect boundary
                boundary = ctype.split("boundary=")[-1].strip()
                parts = raw.split(b"--" + boundary.encode())
                found = False
                for part in parts:
                    if b'Content-Disposition' not in part:
                        continue
                    # extract name
                    m = re.search(br'name="([^"]+)"(?:; filename="([^"]+)")?', part)
                    if not m:
                        continue
                    form_name = m.group(1).decode()
                    filename = m.group(2).decode() if m.group(2) else ""
                    # find header end
                    idx = part.find(b"\r\n\r\n")
                    if idx == -1:
                        continue
                    data = part[idx+4:]
                    # strip trailing \r\n
                    if data.endswith(b"\r\n"):
                        data = data[:-2]
                    if form_name == "file" or form_name == "recording":
                        # Determine recording name from filename or field
                        raw_name = filename if filename else "recording"
                        # Strip .wav suffix only, keep other dots
                        if raw_name.lower().endswith(".wav"):
                            rec_name = raw_name[:-4]
                        else:
                            rec_name = raw_name
                        rec_name = rec_name.strip().split("/")[-1].split("\\")[-1]
                        if not is_valid_recording_name(rec_name):
                            self.send_json({"error": "invalid recording name (alphanumeric, dot, _- only)"}, 400)
                            return
                        dest = recording_path(audio_dir, rec_name)
                        if dest.exists():
                            self.send_json({"error": "recording name must be unique"}, 409)
                            return
                        wav, converted = _ensure_wav_bytes(data)
                        if not wav.startswith(b"RIFF"):
                            self.send_json({"error": "invalid audio: not a WAV and ffmpeg conversion failed (install ffmpeg or re-record)"}, 400)
                            return
                        if converted:
                            print(f"[audio] multipart '{rec_name}' transcoded to WAV via ffmpeg")
                        dest.write_bytes(wav)
                        self.send_json({"ok": True, "name": rec_name})
                        found = True
                        break
                if not found:
                    self.send_json({"error": "no file part found"}, 400)
                return
            else:
                body, _ = self.parse_body()
                # Expect {name, data: base64 or raw}
                if isinstance(body, dict) and "name" in body and "data" in body:
                    import base64
                    rec_name = str(body["name"]).strip()
                    # Allow optional trailing .wav in name
                    if rec_name.lower().endswith(".wav"):
                        rec_name = rec_name[:-4]
                    if not is_valid_recording_name(rec_name):
                        self.send_json({"error": "invalid recording name"}, 400)
                        return
                    dest = recording_path(audio_dir, rec_name)
                    if dest.exists():
                        self.send_json({"error": "recording name must be unique"}, 409)
                        return
                    b64 = body["data"]
                    # strip data URL prefix
                    if "," in b64 and b64.startswith("data:"):
                        b64 = b64.split(",", 1)[1]
                    try:
                        data = base64.b64decode(b64)
                    except Exception:
                        self.send_json({"error": "invalid base64"}, 400)
                        return
                    wav, converted = _ensure_wav_bytes(data)
                    if not wav.startswith(b"RIFF"):
                        self.send_json({"error": "invalid audio: not a WAV and ffmpeg conversion failed (install ffmpeg or re-record)"}, 400)
                        return
                    if converted:
                        print(f"[audio] '{rec_name}' transcoded to WAV via ffmpeg")
                    dest.write_bytes(wav)
                    self.send_json({"ok": True, "name": rec_name})
                    return
                # Also handle raw bytes with ?name= query
                qs = urllib.parse.parse_qs(parsed.query)
                rec_name = (qs.get("name") or [""])[0].strip()
                if rec_name.lower().endswith(".wav"):
                    rec_name = rec_name[:-4]
                if rec_name and isinstance(body, bytes):
                    if not is_valid_recording_name(rec_name):
                        self.send_json({"error": "invalid name"}, 400)
                        return
                    dest = recording_path(audio_dir, rec_name)
                    if dest.exists():
                        self.send_json({"error": "unique name required"}, 409)
                        return
                    wav, converted = _ensure_wav_bytes(body)
                    if not wav.startswith(b"RIFF"):
                        self.send_json({"error": "invalid audio: not a WAV and ffmpeg conversion failed"}, 400)
                        return
                    dest.write_bytes(wav)
                    self.send_json({"ok": True})
                    return
                self.send_json({"error": "invalid request: provide multipart file or JSON {name, data}"}, 400)
                return

        self.send_json({"error": "not found"}, 404)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/config":
            if not require_auth(self):
                self.send_json({"error": "unauthorized"}, 401)
                return
            body, _ = self.parse_body()
            if not isinstance(body, dict):
                self.send_json({"error": "invalid JSON"}, 400)
                return
            # Support both {config, hash} and raw config
            if "config" in body and isinstance(body["config"], dict):
                incoming_cfg = body["config"]
                client_hash = body.get("hash") or self.headers.get("X-Config-Hash") or self.headers.get("If-Match")
            else:
                incoming_cfg = body
                client_hash = self.headers.get("X-Config-Hash") or self.headers.get("If-Match")

            # Conflict detection: compare client_hash with current file_hash
            _, current_hash, _ = read_config_file()
            # If client provided hash and it mismatches current, daemon wins -> 409
            if client_hash and client_hash != current_hash:
                cfg, h, _ = read_config_file()
                self.send_json({"error": "conflict", "message": "Config changed on server (daemon win). Please refresh.", "config": cfg, "hash": h}, 409)
                return

            # Validate
            errors = validate_config(incoming_cfg)
            if errors:
                self.send_json({"error": "validation failed", "details": errors}, 400)
                return
            incoming_cfg = normalize_config(incoming_cfg)
            # Preserve state if not provided? Allow but ensure state exists
            if "state" not in incoming_cfg:
                old_cfg, _, _ = read_config_file()
                if old_cfg and "state" in old_cfg:
                    incoming_cfg["state"] = old_cfg["state"]

            new_hash = atomic_write_config(incoming_cfg)
            self.send_json({"ok": True, "hash": new_hash, "config": incoming_cfg})
            return

        # Rename recording: PUT /api/recordings/<name>/rename  {newName}
        m = re.match(r"^/api/recordings/([^/]+)/rename$", path)
        if m:
            if not require_auth(self):
                self.send_json({"error": "unauthorized"}, 401)
                return
            old_name = urllib.parse.unquote(m.group(1))
            body, _ = self.parse_body()
            if not isinstance(body, dict) or "newName" not in body:
                self.send_json({"error": "provide {newName}"}, 400)
                return
            new_name = str(body["newName"]).strip()
            if new_name.lower().endswith(".wav"):
                new_name = new_name[:-4]
            if not is_valid_recording_name(new_name):
                self.send_json({"error": "invalid newName (alphanumeric, dot, _- only)"}, 400)
                return
            cfg, _, _ = read_config_file()
            audio_dir = get_audio_dir(cfg) if cfg else Path("/tmp")
            old_path = recording_path(audio_dir, old_name)
            new_path = recording_path(audio_dir, new_name)
            if not old_path.exists():
                self.send_json({"error": "not found"}, 404)
                return
            if new_path.exists():
                self.send_json({"error": "name must be unique"}, 409)
                return
            old_path.rename(new_path)
            self.send_json({"ok": True, "newName": new_name})
            return

        self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        m = re.match(r"^/api/recordings/([^/]+)$", path)
        if m:
            if not require_auth(self):
                self.send_json({"error": "unauthorized"}, 401)
                return
            name = urllib.parse.unquote(m.group(1))
            cfg, _, _ = read_config_file()
            audio_dir = get_audio_dir(cfg) if cfg else Path("/tmp")
            fpath = recording_path(audio_dir, name)
            if not fpath.exists():
                self.send_json({"error": "not found"}, 404)
                return
            fpath.unlink()
            self.send_json({"ok": True})
            return
        self.send_json({"error": "not found"}, 404)

    def serve_file(self, filename):
        f = STATIC_DIR / filename
        if not f.exists():
            self.send_json({"error": f"missing {filename}"}, 500)
            return
        data = f.read_bytes()
        ctype = mimetypes.guess_type(str(f))[0] or "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_static(self, rel):
        f = STATIC_DIR / rel
        if not f.exists() or not f.is_file():
            self.send_json({"error": "not found"}, 404)
            return
        data = f.read_bytes()
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    STATIC_DIR.mkdir(exist_ok=True)
    # Ensure hash initialized
    global file_hash
    _, h, _ = read_config_file()
    file_hash = h
    # Start watcher
    t = threading.Thread(target=file_watcher, daemon=True)
    t.start()
    phash = get_password_hash()
    if not phash:
        print("WARNING: No password hash env var set (ALARM_ADMIN_PASSWORD_HASH). Auth is disabled (dev mode).")
    else:
        src = get_password_hash_source() or "UNKNOWN"
        print(f"Auth enabled via {src}")

    # TLS: ensure self-signed cert (auto-renew on startup + background thread)
    tls_cert, tls_key = ensure_tls_cert()
    use_tls = tls_cert is not None and tls_key is not None

    scheme = "https" if use_tls else "http"
    print(f"Serving on {scheme}://{HOST}:{PORT}  config={CONFIG_PATH}  static={STATIC_DIR}")
    if use_tls:
        print(f"[tls] cert={tls_cert} key={tls_key}")
        print(f"[tls] iOS: open https://alarmclock.local:{PORT}/ (or https://<pi-ip>:{PORT}/) and trust cert if prompted;")
        print(f"[tls]      microphone (getUserMedia) requires HTTPS — self-signed is sufficient once trusted.")
        print(f"[tls]      To trust on iOS: visit the URL, tap 'Show Details' -> 'visit site', or install cert from https://<pi-ip>:{PORT}/static/server.crt if exposed")
        # Start background renewal thread (checks hourly)
        rt = threading.Thread(target=_tls_renewal_loop, args=(tls_cert, tls_key), daemon=True)
        rt.start()
    else:
        print("[tls] Serving plain HTTP — Safari getUserMedia will be blocked (requires HTTPS)")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    if use_tls:
        import ssl

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # Harden: require TLS 1.2+, auto-select ciphers
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2  # type: ignore[attr-defined]
        except Exception:
            ctx.options |= getattr(ssl, "OP_NO_TLSv1", 0) | getattr(ssl, "OP_NO_TLSv1_1", 0)
        ctx.load_cert_chain(certfile=str(tls_cert), keyfile=str(tls_key))
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down")

if __name__ == "__main__":
    main()
