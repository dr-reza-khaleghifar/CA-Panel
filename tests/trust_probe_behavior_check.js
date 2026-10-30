// Deterministic browser-like smoke tests for HTTP-only HTTPS resource probe.
// No external HTTP requests, secrets, certificates or production endpoints.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('app/static/trust.html', 'utf8');
const match = html.match(/<script>\s*([\s\S]*?)<\/script>/i);
assert.ok(match, 'HTTP guide must include exactly one small inline script');
const script = match[1];
assert.equal((html.match(/<script\b/ig) || []).length, 1);

function simulate(event) {
  const classes = new Set();
  let onReady;
  let probe;
  let alarm;
  let redirected = null;
  let cleared = 0;
  function Image() { probe = this; }
  const sandbox = {
    document: {
      documentElement: {
        classList: {
          add(name) { classes.add(name); },
          remove(name) { classes.delete(name); }
        }
      },
      addEventListener(name, callback) {
        assert.equal(name, 'DOMContentLoaded');
        onReady = callback;
      }
    },
    window: {
      location: {
        hostname: 'ca1.iravand.ir',
        replace(url) { redirected = url; }
      },
      setTimeout(fn, millis) {
        assert.equal(millis, 6500);
        alarm = fn;
        return 42;
      },
      clearTimeout(id) { assert.equal(id, 42); cleared++; }
    },
    Image,
    Date: { now: () => 1590000000000 }
  };
  vm.runInNewContext(script, sandbox, { timeout: 2000 });
  assert.ok(classes.has('checking'), 'Guide must enter checking state');
  onReady();
  assert.equal(probe.src, 'https://ca1.iravand.ir/static/favicon.svg?trust_probe=1590000000000');
  assert.equal(redirected, null);
  assert.ok(!probe.src.includes('password'));
  assert.ok(!probe.src.includes('csrf'));
  if (event === 'load') {
    probe.onload();
    assert.equal(redirected, 'https://ca1.iravand.ir/');
    assert.ok(!classes.has('probe-failed'));
    alarm(); // late timeout must not replace successful navigation
    assert.ok(!classes.has('probe-failed'));
  } else if (event === 'error') {
    probe.onerror();
    assert.equal(redirected, null);
    assert.ok(classes.has('probe-failed'));
    assert.ok(!classes.has('checking'));
    probe.onload(); // a delayed late response must never redirect
    assert.equal(redirected, null);
  } else if (event === 'timeout') {
    alarm();
    assert.equal(redirected, null);
    assert.ok(classes.has('probe-failed'));
    assert.ok(!classes.has('checking'));
    probe.onload();
    assert.equal(redirected, null);
  }
  assert.equal(cleared, 1);
}
for (const event of ['load', 'error', 'timeout']) simulate(event);
console.log('HTTP onboarding probe simulated: HTTPS load redirects; failures/timeout show help.');
