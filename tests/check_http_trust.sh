#!/usr/bin/env bash
# Exercise real Caddy HTTP onboarding and public Root CA downloads using throwaway files.
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
container="ca-panel-http-guide-$$"

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

mkdir -p "$tmp/tls" "$tmp/onboarding"

openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj "/CN=ca1.iravand.ir" \
  -keyout "$tmp/tls/privkey.pem" \
  -out "$tmp/tls/fullchain.pem" >/dev/null 2>&1

# Use only disposable public certificate material in this integration test.
openssl x509 -in "$tmp/tls/fullchain.pem" \
  -out "$tmp/onboarding/ca-panel-root-ca.pem"
openssl x509 -in "$tmp/tls/fullchain.pem" -outform DER \
  -out "$tmp/onboarding/ca-panel-root-ca.cer"
cp app/static/trust.html "$tmp/onboarding/index.html"
cp app/static/trust.js "$tmp/onboarding/trust.js"

docker run -d --name "$container" \
  -e PANEL_DOMAIN=ca1.iravand.ir \
  -p 127.0.0.1:18080:80 \
  -v "$PWD/Caddyfile.private:/etc/caddy/Caddyfile:ro" \
  -v "$tmp/onboarding:/srv/onboarding:ro" \
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
[[ "$guide" == *"مرکز راهنمای اعتماد و گواهی CA-Panel"* ]] || { echo "Guide HTML missing"; exit 1; }
[[ "$guide" == *"0E:3B:D2:5A:45:8A:0A:7E"* ]] || { echo "Current Root CA fingerprint missing"; exit 1; }
[[ "$guide" == *'src="/trust.js"'* ]] || { echo "Local guide script missing"; exit 1; }

script="$(curl --noproxy '*' --silent --show-error -H "Host: $host" "$base/trust.js")"
[[ "$script" == *"data-copy-target"* ]] || { echo "Guide helper script missing"; exit 1; }

for path in \
  /downloads/ca-panel-root-ca.pem \
  /downloads/ca-panel-root-ca.cer; do
  [[ "$(status "$base$path")" == 200 ]] || { echo "Public Root CA download unavailable: $path"; exit 1; }
done

for path in \
  /index.html /trust.css /root-ca.pem /favicon.ico /robots.txt \
  /downloads/anything /login /api/system /api/requests /api/ca.pem \
  /api/downloads/anything /static/app.js /.env /secret.key \
  /secrets/online/issuer-key.pem; do
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
grep -qi "script-src 'self'" <<<"$headers"
grep -qi "style-src 'unsafe-inline'" <<<"$headers"
grep -qi "img-src 'none'" <<<"$headers"
grep -qi "connect-src 'none'" <<<"$headers"
grep -qi '^cache-control: no-store' <<<"$headers"

echo "OK: HTTP exposes only the trust guide, its local script and the two public Root CA downloads."
