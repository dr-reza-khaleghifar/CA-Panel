"""Install pinned Vazirmatn WOFF2 on the Docker host (never inside Docker build).

HTTPS certificate validation is always enabled. Offline import is supported and
the exact Git blob SHA-1 is validated before the font enters the image.
"""
from __future__ import annotations

import argparse
import hashlib
import ssl
import sys
import urllib.error
from http.client import HTTPSConnection
from urllib.parse import urlsplit
from pathlib import Path

UPSTREAM = (
    "https://raw.githubusercontent.com/rastikerdar/vazirmatn/"
    "6e553e33489a8f9dfaccc76860a2e3f3c1e66de7/"
    "fonts/webfonts/Vazirmatn%5Bwght%5D.woff2"
)
EXPECTED_GIT_BLOB = "a501289a85595158570b0c2badcb4608b042e748"
EXPECTED_SIZE = 111152
OUTPUT = Path(__file__).resolve().parents[1] / "app" / "static" / "fonts" / "Vazirmatn.woff2"


def install_font(source: Path | None = None) -> Path:
    if source is None:
        # Allow only this pinned HTTPS origin; never follow redirects or load
        # file:, custom or attacker-controlled URL schemes.
        parsed = urlsplit(UPSTREAM)
        if (parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com"
                or parsed.port is not None or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError("Invalid or unexpected pinned font origin")
        connection = HTTPSConnection("raw.githubusercontent.com", timeout=30,
                                     context=ssl.create_default_context())
        try:
            connection.request("GET", parsed.path)
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("Font server did not return exact HTTPS 200")
            content = response.read(EXPECTED_SIZE + 1)
        finally:
            connection.close()
    else:
        content = source.read_bytes()
    if len(content) != EXPECTED_SIZE or content[:4] != b"wOF2":
        raise ValueError("Invalid or unexpected Vazirmatn WOFF2 font bytes")
    header = b"blob " + str(len(content)).encode("ascii") + bytes([0])
    # Git blob object IDs are historically SHA-1 (a format compatibility check,
    # not a digital signature); HTTPS and the immutable upstream revision are
    # separately verified. This SHA-1 use is NOT a password or certificate hash.
    digest = hashlib.sha1(header + content, usedforsecurity=False).hexdigest()
    if digest != EXPECTED_GIT_BLOB:
        raise ValueError("Vazirmatn font integrity mismatch; file will not be installed")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(content)
    return OUTPUT


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the verified Persian font for CA-Panel")
    parser.add_argument("--file", type=Path, help="Use a downloaded WOFF2 file (still verified)")
    args = parser.parse_args()
    try:
        location = install_font(args.file)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"Font setup failed: {exc}", file=sys.stderr)
        print("Docker build is still safe to run without the optional font.", file=sys.stderr)
        print("For offline setup, try --file /path/to/Vazirmatn.woff2", file=sys.stderr)
        return 1
    print("Verified Vazirmatn installed at", location)
    print("Now run: docker compose up -d --build --force-recreate api")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
