#!/usr/bin/env bash
# Exercise real Caddy HTTP routing using a throwaway (never production) X.509.
set -euo pipefail
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
container="iran-ca-http-onboarding-$$"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT
mkdir -p "$tmp/tls"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj "/CN=ca1.iravand.ir" \
  -keyout "$tmp/tls/privkey.pem" \
  -out "$tmp/tls/fullchain.pem" >/dev/null 2>&1

docker run -d --name "$container" \
  -e PANEL_DOMAIN=ca1.iravand.ir \
  -p 127.0.0.1:18080:80 \
  -v "$PWD/Caddyfile.private:/etc/caddy/Caddyfile:ro" \
  -v "$PWD/app/static/trust.html:/srv/onboarding/index.html:ro" \
  -v "$tmp/tls:/etc/caddy/tls:ro" \
  caddy:2.10 >/dev/null

base=http://127.0.0.1:18080
host=ca1.iravand.ir
status() {
  curl --noproxy '*' --silent --show-error --max-time 3 \
    -H "Host: $host" -o /dev/null -w '%{http_code}' "$@"
}

for n in {1..35}; do
  if [[ "$(status "$base/" 2>/dev/null || true)" == "200" ]]; then break; fi
  sleep .3
done

[[ "$(status "$base/")" == 200 ]] || { echo "Guide not available on HTTP root"; exit 1; }
guide="$(curl --noproxy '*' --silent --show-error -H "Host: $host" "$base/")"
[[ "$guide" == *"گواهی دیجیتال ایران"* ]] || { echo "Guide HTML missing"; exit 1; }
[[ "$guide" != *'href="/root-ca.pem"'* ]] || { echo "HTTP guide must not offer downloads"; exit 1; }
for path in /index.html /trust.css /root-ca.pem /favicon.ico /robots.txt /login /api/system /api/requests /api/ca.pem /api/downloads/anything \
            /static/app.js /.env /secret.key /secrets/online/issuer-key.pem; do
  got="$(status "$base$path")"
  [[ "$got" == 404 ]] || { echo "SECURITY FAILURE: HTTP $path returned $got"; exit 1; }
done
for method in POST PUT DELETE; do
  got="$(status -X "$method" "$base/")"
  [[ "$got" == 404 || "$got" == 405 ]] || {
    echo "SECURITY FAILURE: HTTP $method / returned $got"; exit 1;
  }
done
headers="$(curl --noproxy '*' --silent --show-error -D - -o /dev/null -H "Host: $host" "$base/")"
grep -qi '^x-content-type-options: nosniff' <<<"$headers"
grep -qi '^x-frame-options: DENY' <<<"$headers"
grep -qi '^content-security-policy:' <<<"$headers"
grep -qi "img-src https://ca1.iravand.ir" <<<"$headers"
grep -qi "script-src 'unsafe-inline'" <<<"$headers"
grep -qi '^cache-control: no-store' <<<"$headers"
echo "OK: Caddy HTTP serves ONLY GET/HEAD / guide; certificate and all other paths are inaccessible."
