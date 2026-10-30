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
cp "$tmp/tls/fullchain.pem" "$tmp/root-ca.pem"

docker run -d --name "$container" \
  -e PANEL_DOMAIN=ca1.iravand.ir \
  -p 127.0.0.1:18080:80 \
  -v "$PWD/Caddyfile.private:/etc/caddy/Caddyfile:ro" \
  -v "$PWD/app/static/trust.html:/srv/onboarding/index.html:ro" \
  -v "$PWD/app/static/trust.css:/srv/onboarding/trust.css:ro" \
  -v "$tmp/root-ca.pem:/srv/onboarding/root-ca.pem:ro" \
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

for path in / /trust.css /root-ca.pem; do
  got="$(status "$base$path")"
  [[ "$got" == 200 ]] || { echo "ERROR: HTTP trust $path -> $got"; exit 1; }
done
cert_data="$(curl --noproxy '*' --silent --show-error -H "Host: $host" "$base/root-ca.pem")"
[[ "$cert_data" == *"BEGIN CERTIFICATE"* ]] || { echo "Root CA public certificate missing"; exit 1; }

for path in /login /api/system /api/requests /api/ca.pem /api/downloads/anything \
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
grep -qi '^cache-control: no-store' <<<"$headers"
echo "OK: Caddy HTTP onboarding serves only public Root and static instructions; protected routes inaccessible."
