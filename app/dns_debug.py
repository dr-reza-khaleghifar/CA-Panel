"""Inspect the *same container resolver* and stored DNS challenge as CA-Panel.

Run: docker compose exec api python -m app.dns_debug example.org
Optional: docker compose exec api python -m app.dns_debug --request-id REQUEST_ID
Never paste full challenge tokens in public issue reports.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import dns.exception
import dns.resolver

from app.main import Settings, connect, normalize_domain


def probe_txt(name: str, expected: str, resolver=None):
    """Returns (match, all TXT values, resolver error); matches exact joined TXT RDATA."""
    if resolver is None:
        resolver = dns.resolver.Resolver()
    resolver.timeout = 2
    resolver.lifetime = 5
    try:
        answers = resolver.resolve(name, "TXT", search=False)
        values = [b"".join(answer.strings).decode("utf-8", errors="replace")
                  for answer in answers]
        return expected in values, values, None
    except dns.exception.DNSException as exc:
        return False, [], f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose CA-Panel TXT validation in the API container")
    parser.add_argument("domain", nargs="?", help="Exact domain entered in CA-Panel")
    parser.add_argument("--request-id", help="Exact CA-Panel request_id, to avoid selecting an older/newer request")
    args = parser.parse_args()
    if bool(args.domain) == bool(args.request_id):
        parser.error("Provide either a domain or --request-id")

    settings = Settings()
    if args.domain:
        try:
            domain = normalize_domain(args.domain)
        except ValueError as exc:
            parser.error(str(exc))
        query = "SELECT * FROM challenges WHERE domain=? ORDER BY created_at DESC LIMIT 1"
        parameter = domain
    else:
        query = "SELECT * FROM challenges WHERE id=?"
        parameter = args.request_id

    with connect(settings.db_path) as con:
        row = con.execute(query, (parameter,)).fetchone()
    if row is None:
        print("No matching request found in the panel database.")
        return 2

    name = "_ca-panel." + row["domain"] + "."
    expected = "ca-panel-verification=" + row["token"]
    expired = row["expires_at"] < int(time.time())
    resolver = dns.resolver.Resolver()
    print("Domain:", row["domain"])
    print("Request ID:", row["id"])
    print("DNS TXT name queried:", name)
    print("Expected exact TXT value:", repr(expected))
    print("Challenge expires (UTC):", datetime.fromtimestamp(row["expires_at"], timezone.utc).isoformat())
    print("Challenge expired:", expired)
    print("Container DNS resolver(s):", ", ".join(str(x) for x in resolver.nameservers))
    matches, values, error = probe_txt(name, expected, resolver)
    if error:
        print("DNS lookup error:", error)
    else:
        print("TXT values returned:", len(values))
        for value in values:
            print("  ", repr(value))
    print("DNS verification:", "MATCH" if matches else "NO MATCH")
    if matches and expired:
        print("ACTION: Create a new challenge in the panel; this one has expired.")
    elif not matches:
        print("ACTION: Ensure the TXT record name and value are exact; then check DNS propagation and container resolver.")
    else:
        print("The TXT record is visible and matches. Retry verification for this request.")
    return 0 if matches and not expired else 1


if __name__ == "__main__":
    raise SystemExit(main())
