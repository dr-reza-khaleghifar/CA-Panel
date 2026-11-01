// Static behavior checks for the local, HTTP-safe trust guide helper.
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');

const html = fs.readFileSync('app/static/trust.html', 'utf8');
const script = fs.readFileSync('app/static/trust.js', 'utf8');

assert.equal((html.match(/<script\b/ig) || []).length, 1,
  'The guide must load one local helper script');
assert.match(html, /<script\s+src=["']\/trust\.js["']\s+defer>/i,
  'The guide must load the local helper, not inline or remote JavaScript');
assert.doesNotMatch(html, /<script(?!\s+src=)[^>]*>/i,
  'The guide must not contain inline JavaScript');

assert.match(script, /addEventListener\("input"/,
  'Platform search must react to input');
assert.match(script, /querySelectorAll\("\.platform-card"\)/,
  'Search must target platform guide cards');
assert.match(script, /data-expand-all/,
  'The guide must provide expand-all behavior');
assert.match(script, /data-collapse-all/,
  'The guide must provide collapse-all behavior');
assert.match(script, /data-copy-target/,
  'Copy controls must use explicit target selectors');
assert.match(script, /navigator\.clipboard\.writeText/,
  'Copy should use the Clipboard API in secure contexts');
assert.match(script, /document\.execCommand\("copy"\)/,
  'Copy should include a fallback for the HTTP bootstrap page');

assert.doesNotMatch(script, /\bfetch\s*\(/,
  'The helper must not make network requests');
assert.doesNotMatch(script, /XMLHttpRequest|new Image\s*\(/,
  'The helper must not probe external resources');
assert.doesNotMatch(script, /location\.replace|window\.open/,
  'The helper must not redirect or open external windows');

console.log('Trust guide behavior checks passed: search, accordions, copy fallback and no network probes.');
