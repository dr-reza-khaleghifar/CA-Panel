'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {webcrypto} = require('node:crypto');
const ctx = {crypto: webcrypto, isSecureContext: true, Uint8Array, TextEncoder, Blob, DataView, btoa};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('app/static/cert.js', 'utf8'), ctx);
const lib = ctx.CAPanelCert;
(async () => {
  assert.equal(lib.isSupported(), true);
  const {csrPem, privateKeyPem} = await lib.generateCSR('tizpo.ir');
  assert.match(csrPem, /BEGIN CERTIFICATE REQUEST/);
  assert.match(privateKeyPem, /BEGIN PRIVATE KEY/);
  const output = process.argv[2] || '/tmp';
  fs.writeFileSync(path.join(output, 'ca-panel-generated.csr'), csrPem);
  fs.writeFileSync(path.join(output, 'ca-panel-generated.key'), privateKeyPem, {mode: 0o600});
  let threw = false;
  try { lib.makeBundleFiles({domain:'../oops',certificate_pem:'',chain_pem:''},privateKeyPem); } catch { threw=true; }
  assert.equal(threw,true);
  const fakePem = `-----BEGIN CERTIFICATE-----\nQUJD\n-----END CERTIFICATE-----\n`;
  const files = lib.makeBundleFiles({domain:'tizpo.ir', certificate_pem:fakePem, chain_pem:fakePem + fakePem},privateKeyPem);
  const zip = lib.createZip(files);
  fs.writeFileSync(path.join(output, 'ca-panel-generated.zip'), Buffer.from(await zip.arrayBuffer()));
  assert.equal(files.length,6);
  console.log('browser key/CSR and ZIP generation passed');
})().catch(err => {console.error(err);process.exitCode=1});
