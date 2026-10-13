#!/usr/bin/env python3
"""Local-only SIP REGISTER reproducer for Kamailio #4991 / PR #4992.

Requires a disposable registrar with max_contacts=3, no authentication for
test identities, min_expires=1, and usrloc timer_interval >= 30.
Four cases: ordinary 4th binding rejected, duplicate removals, expired revival,
and per-Contact +sip.instance. Reports status codes, not the final usrloc dump;
always confirm final live binding count with kamcmd ul.dump.
"""
import argparse
import ipaddress
import re
import socket
import time
import uuid

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--port", type=int, default=5060)
p.add_argument("--run", action="store_true")
p.add_argument("--allow-remote", action="store_true")
p.add_argument("--sleep", type=float, default=3.0)
args = p.parse_args()
if not args.run:
    p.error("pass --run only for a disposable localhost Kamailio registrar")
try:
    ip = ipaddress.ip_address(args.host)
except ValueError:
    p.error("numeric --host IP required")
if not ip.is_loopback and not args.allow_remote:
    p.error("non-loopback destinations require explicit --allow-remote")
if not 0 < args.port < 65536 or args.sleep < 2.0:
    p.error("invalid port or sleep (>=2s needed for expiration)")
suffix = uuid.uuid4().hex[:8]
server = (args.host, args.port)
s = socket.socket(socket.AF_INET6 if ip.version == 6 else socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(3.0)
s.bind(("::1" if ip.version == 6 else "127.0.0.1", 0))
local_host, local_port = s.getsockname()[:2]

def contact(username, n, expires=3600, instance=None):
    address = f"sip:{username}{n}@198.51.100.{n}:5060"
    value = f"<{address}>;expires={expires}"
    if instance:
        value += f';+sip.instance="<urn:uuid:{instance}>"'
    return value

def register(user, contacts, callid=None, seq=1, expected=200):
    callid = callid or uuid.uuid4().hex
    target_host = f"[{args.host}]" if ip.version == 6 else args.host
    uri = f"sip:{target_host}:{args.port}"
    via_host = f"[{local_host}]" if ip.version == 6 else local_host
    hdrs = [
        f"REGISTER {uri} SIP/2.0",
        f"Via: SIP/2.0/UDP {via_host}:{local_port};branch=z9hG4bK{uuid.uuid4().hex};rport",
        "Max-Forwards: 70",
        f"From: <sip:{user}@example.com>;tag={suffix}",
        f"To: <sip:{user}@example.com>",
        f"Call-ID: {callid}",
        f"CSeq: {seq} REGISTER",
        "Contact: " + ", ".join(contacts),
        "Content-Length: 0",
        "",
        "",
    ]
    s.sendto("\r\n".join(hdrs).encode("ascii"), server)
    data, _ = s.recvfrom(8192)
    m = re.match(rb"SIP/2.0\s+(\d{3})", data)
    if not m:
        raise AssertionError(f"Invalid SIP response: {data[:150]!r}")
    code = int(m.group(1))
    status = "PASS" if code == expected else "FAIL"
    print(f"{status} {user}: expected={expected}, actual={code}", flush=True)
    if code != expected:
        raise AssertionError(f"{user}: wanted {expected}, got {code}: {data[:300]!r}")
    return callid

def name(s):
    return f"{s}-{suffix}"

# Control: three distinct bindings, fourth new one must be rejected.
who = name("control")
register(who, [contact(who, 11), contact(who, 12), contact(who, 13)])
register(who, [contact(who, 14)], expected=503)

# Case 1: duplicate removals must NOT count as removing 2 bindings.
who = name("duplicate")
register(who, [contact(who, 21), contact(who, 22), contact(who, 23)])
register(who, [
    contact(who, 21, 0), contact(who, 21, 0),
    contact(who, 24), contact(who, 25)], expected=503)

# Case 2: expired-but-not-yet-cleaned binding revival counts as new.
who = name("revive")
register(who, [contact(who, 31, 1)])
register(who, [contact(who, 32), contact(who, 33)])
time.sleep(args.sleep)
register(who, [contact(who, 34)])
register(who, [contact(who, 31)], expected=503)

# Case 3: each Contact must use its own +sip.instance.
who = name("instance")
ins = "00000000-0000-4000-8000-000000000011"
cid = register(who, [contact(who, 41, instance=ins),
                     contact(who, 42), contact(who, 43)])
register(who, [contact(who, 41, instance=ins), contact(who, 46)],
         callid=cid, seq=2, expected=503)

print("PASS: SIP status assertions. NEXT: independently check kamcmd ul.dump.")
