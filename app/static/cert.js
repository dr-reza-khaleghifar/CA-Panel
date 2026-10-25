/* CA-Panel: browser-only key generation, PKCS#10 CSR and zero-dependency ZIP.
 * Private keys are never sent to the server. Serve the page over HTTPS or localhost.
 */
'use strict';
(function (scope) {
  const utf8 = text => new TextEncoder().encode(text);
  function join(...arrays) {
    const out = new Uint8Array(arrays.reduce((n, arr) => n + arr.length, 0));
    let offset = 0;
    for (const arr of arrays) { out.set(arr, offset); offset += arr.length; }
    return out;
  }
  function der(tag, bytes) {
    const n = bytes.length;
    let length;
    if (n < 128) length = Uint8Array.of(n);
    else if (n < 256) length = Uint8Array.of(0x81, n);
    else if (n < 65536) length = Uint8Array.of(0x82, n >>> 8, n & 255);
    else throw new Error('ASN.1 data too large');
    return join(Uint8Array.of(tag), length, bytes);
  }
  const sequence = (...parts) => der(0x30, join(...parts));
  const oid = (...bytes) => der(0x06, Uint8Array.of(...bytes));
  const rsaSha256 = () => sequence(oid(0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x0b), der(0x05, new Uint8Array()));
  function pem(label, bytes) {
    const raw = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    let base64 = '';
    for (let i = 0; i < raw.length; i += 0x3fff) {
      base64 += btoa(String.fromCharCode(...raw.subarray(i, i + 0x3fff)));
    }
    // Chunk base64 on 64-character lines; above chunks are multiples of 3.
    return `-----BEGIN ${label}-----\n${base64.match(/.{1,64}/g).join('\n')}\n-----END ${label}-----\n`;
  }
  function isSupported() {
    return scope.isSecureContext === true && typeof scope.crypto?.subtle?.generateKey === 'function';
  }
  async function generateCSR(domain) {
    if (!isSupported()) {
      throw new Error('ساخت امن کلید فقط با HTTPS یا localhost پشتیبانی می‌شود. پنل را از آدرس HTTPS باز کنید.');
    }
    if (!/^(?=.{3,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])$/.test(domain) || domain.includes('..')) {
      throw new Error('نام دامنه نامعتبر است.');
    }
    // RSASSA-PKCS1-v1_5 / SHA-256 for broad nginx, Apache and hosting compatibility.
    const pair = await scope.crypto.subtle.generateKey(
      {name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048,
        publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256'},
      true, ['sign', 'verify']
    );
    const publicKey = new Uint8Array(await scope.crypto.subtle.exportKey('spki', pair.publicKey));
    const privateKey = new Uint8Array(await scope.crypto.subtle.exportKey('pkcs8', pair.privateKey));
    // Subject CN=domain, encoded as UTF8String.
    const subject = sequence(der(0x31, sequence(oid(0x55, 0x04, 0x03), der(0x0c, utf8(domain)))));
    // pkcs-9 extensionRequest {subjectAltName = DNS:domain}.
    const san = sequence(der(0x82, utf8(domain)));
    const extension = sequence(oid(0x55, 0x1d, 0x11), der(0x04, san));
    const extensions = sequence(extension);
    const requestAttribute = sequence(
      oid(0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x09, 0x0e),
      der(0x31, extensions)
    );
    // PKCS#10 CertificationRequestInfo includes [0] IMPLICIT SET OF Attribute.
    const requestInfo = sequence(der(0x02, Uint8Array.of(0)), subject, publicKey, der(0xa0, requestAttribute));
    const signature = new Uint8Array(await scope.crypto.subtle.sign('RSASSA-PKCS1-v1_5', pair.privateKey, requestInfo));
    const csr = sequence(requestInfo, rsaSha256(), der(0x03, join(Uint8Array.of(0), signature)));
    return {csrPem: pem('CERTIFICATE REQUEST', csr), privateKeyPem: pem('PRIVATE KEY', privateKey)};
  }
  function getCerts(text) {
    return text.match(/-----BEGIN CERTIFICATE-----\s*[A-Za-z0-9+/=\s]+?-----END CERTIFICATE-----/g)?.map(s => s.trim() + '\n') || [];
  }
  function makeBundleFiles(result, privateKeyPem) {
    const domain = result.domain;
    if (!/^[a-z0-9][a-z0-9.-]{0,252}$/.test(domain) || domain.includes('..')) {
      throw new Error('Invalid issued domain');
    }
    const leaf = getCerts(result.certificate_pem);
    const chain = getCerts(result.chain_pem);
    if (leaf.length !== 1 || chain.length !== 2 || !privateKeyPem.startsWith('-----BEGIN PRIVATE KEY-----\n')) {
      throw new Error('بسته گواهی ناقص است؛ لطفاً با مدیر سامانه تماس بگیرید.');
    }
    const fullChain = leaf[0] + chain[0]; // Root is a trust anchor, not normally sent by a TLS server.
    const instructions = `CA-Panel private CA certificate for ${domain}\n\n` +
      `${domain}.key           Private key (SECRET) - never upload/share it\n` +
      `${domain}.crt           Issued server/leaf certificate\n` +
      `${domain}-fullchain.pem Leaf + issuing intermediate for nginx/Apache\n` +
      `issuing-ca.pem         Issuing CA certificate\n` +
      `root-ca.pem            PRIVATE CA trust anchor (verify fingerprint out of band)\n\n` +
      `For nginx: ssl_certificate ${domain}-fullchain.pem; ssl_certificate_key ${domain}.key;\n` +
      `This certificate is NOT publicly browser-trusted. Manage private root trust separately.\n` +
      `Store and back up the private key securely; this panel cannot recover it.\n`;
    return [
      {name: `${domain}.key`, content: privateKeyPem},
      {name: `${domain}.crt`, content: leaf[0]},
      {name: `${domain}-fullchain.pem`, content: fullChain},
      {name: 'issuing-ca.pem', content: chain[0]},
      {name: 'root-ca.pem', content: chain[1]},
      {name: 'README.txt', content: instructions}
    ];
  }
  function crc32(bytes) {
    let crc = -1;
    for (const byte of bytes) {
      crc ^= byte;
      for (let j = 0; j < 8; j++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
    return (crc ^ -1) >>> 0;
  }
  function createZip(files) {
    // Minimal ZIP 'store' format, compatible with macOS Archive Utility/unzip/Windows.
    const output = [], central = [];
    let offset = 0;
    const emit = (buffer, target) => { target.push(buffer); };
    function record(length, values) {
      const buffer = new Uint8Array(length), dv = new DataView(buffer.buffer);
      for (const [size, pos, value] of values) {
        if (size === 2) dv.setUint16(pos, value, true);
        else dv.setUint32(pos, value >>> 0, true);
      }
      return buffer;
    }
    if (files.length > 65535) throw new Error('Too many files');
    for (const file of files) {
      if (!/^[a-zA-Z0-9._-]+$/.test(file.name)) throw new Error('Invalid ZIP filename');
      const name = utf8(file.name), data = utf8(file.content), checksum = crc32(data);
      if (data.length > 0xffffffff) throw new Error('File too large');
      const local = record(30, [[4, 0, 0x04034b50], [2, 4, 20], [2, 8, 0], [4, 14, checksum],
        [4, 18, data.length], [4, 22, data.length], [2, 26, name.length]]);
      // Local version flags 0, compression method 0, timestamp 0, data descriptor not used.
      emit(local, output); emit(name, output); emit(data, output);
      // Unix file modes: restrict secret key to owner on capable unzip clients.
      const mode = file.name.endsWith('.key') ? 0o100600 : 0o100644;
      const entry = record(46, [[4, 0, 0x02014b50], [2, 4, 0x0314], [2, 6, 20],
        [4, 16, checksum],
        [4, 20, data.length], [4, 24, data.length], [2, 28, name.length],
        [4, 38, mode << 16], [4, 42, offset]]);
      emit(entry, central); emit(name, central);
      offset += local.length + name.length + data.length;
      if (offset > 0xffffffff) throw new Error('Archive too large');
    }
    const centralLength = central.reduce((n, part) => n + part.length, 0);
    const end = record(22, [[4, 0, 0x06054b50], [2, 8, files.length], [2, 10, files.length],
      [4, 12, centralLength], [4, 16, offset]]);
    return new Blob([...output, ...central, end], {type: 'application/zip'});
  }
  scope.CAPanelCert = Object.freeze({isSupported, generateCSR, makeBundleFiles, createZip});
})(typeof window === 'undefined' ? globalThis : window);
