"""Registry of accounts created on job sites / ATSs. All sites share one password
set by the user in .env as ACCOUNT_PASSWORD. Prints JSON.

  python tools/accounts.py get <domain-or-url>
  python tools/accounts.py create <domain-or-url> [--email you@example.com]
  python tools/accounts.py mark-verified <domain-or-url>
  python tools/accounts.py password
  python tools/accounts.py list
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, connect  # noqa: E402

ENV_FILE = ROOT / ".env"
PROFILE_FILE = ROOT / "data" / "profile.yaml"


def norm_domain(value: str) -> str:
    """Full host, so per-tenant ATSs (acme.wd5.myworkdayjobs.com) stay distinct."""
    value = value.strip().lower()
    host = urlsplit(value).netloc if "://" in value else value.split("/")[0]
    return host.removeprefix("www.")


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def profile_email() -> str | None:
    if not PROFILE_FILE.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(PROFILE_FILE.read_text(encoding="utf-8")) or {}
        email = (data.get("contact") or {}).get("email") or data.get("email")
        if email:
            return str(email)
    except Exception:
        pass
    m = re.search(r"^\s*email:\s*['\"]?([^'\"\s]+)", PROFILE_FILE.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("get", "create", "mark-verified"):
        sp = sub.add_parser(name)
        sp.add_argument("domain")
        if name == "create":
            sp.add_argument("--email")
    sub.add_parser("password")
    sub.add_parser("list")
    args = p.parse_args(argv)

    if args.cmd == "password":
        pw = load_env().get("ACCOUNT_PASSWORD")
        out = {"password": pw} if pw else {"error": f"ACCOUNT_PASSWORD not set in {ENV_FILE}"}
        print(json.dumps(out))
        return 0 if pw else 1

    with connect() as conn:
        if args.cmd == "list":
            out = {"accounts": [dict(r) for r in conn.execute("SELECT * FROM accounts ORDER BY created_at")]}
        else:
            domain = norm_domain(args.domain)
            if args.cmd == "get":
                r = conn.execute("SELECT * FROM accounts WHERE domain=?", (domain,)).fetchone()
                out = {"exists": bool(r), "domain": domain,
                       "email": r["email"] if r else profile_email(),
                       "verified": bool(r["verified"]) if r else False}
            elif args.cmd == "create":
                email = args.email or profile_email()
                if not email:
                    print(json.dumps({"error": "no email given and none found in data/profile.yaml"}))
                    return 1
                conn.execute("INSERT OR IGNORE INTO accounts (domain, email) VALUES (?, ?)", (domain, email))
                conn.commit()
                out = {"created": True, "domain": domain, "email": email}
            else:  # mark-verified
                cur = conn.execute("UPDATE accounts SET verified=1 WHERE domain=?", (domain,))
                conn.commit()
                out = {"updated": cur.rowcount > 0, "domain": domain}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
