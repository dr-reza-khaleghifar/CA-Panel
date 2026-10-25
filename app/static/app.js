'use strict';
let currentRequest = null;
let issuedPem = null;
const $ = id => document.getElementById(id);
function show(id) { $(id).classList.remove('hidden'); }
function hide(id) { $(id).classList.add('hidden'); }
function message(text, good = false) {
  $('message').textContent = text;
  $('message').classList.toggle('good', good);
  show('message');
}
function step(n) {
  for (let i = 1; i <= 3; i++) $('step-' + i).classList.toggle('selected', i <= n);
}
async function api(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options, headers: {'Content-Type':'application/json', ...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'درخواست ناموفق بود.');
  return data;
}
async function busy(button, callback) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = 'در حال پردازش…';
  hide('message');
  try { await callback(); } catch (err) { message(err.message || 'خطای غیرمنتظره'); }
  finally { button.disabled = false; button.textContent = original; }
}
$('domain-form').addEventListener('submit', event => {
  event.preventDefault();
  busy($('domain-submit'), async () => {
    const data = await api('/api/requests', {method:'POST', body:JSON.stringify({domain:$('domain').value})});
    currentRequest = data;
    $('dns-name').textContent = data.dns_name;
    $('dns-value').textContent = data.dns_value;
    hide('domain-panel'); show('dns-panel'); step(2);
  });
});
$('verify-button').addEventListener('click', () => busy($('verify-button'), async () => {
  const result = await api('/api/requests/' + encodeURIComponent(currentRequest.request_id) + '/verify', {method:'POST'});
  if (!result.verified) throw new Error('مالکیت دامنه تأیید نشد.');
  const d = currentRequest.domain;
  const shell = `openssl req -new -newkey rsa:2048 -nodes -keyout site.key -out site.csr -subj "/CN=${d}" -addext "subjectAltName=DNS:${d}"`;
  $('csr-command').textContent = shell;
  hide('dns-panel'); show('issue-panel'); step(3);
  message('مالکیت DNS تأیید شد.', true);
}));
$('issue-button').addEventListener('click', () => busy($('issue-button'), async () => {
  const result = await api('/api/requests/' + encodeURIComponent(currentRequest.request_id) + '/issue', {method:'POST',body:JSON.stringify({csr_pem:$('csr').value})});
  issuedPem = result.fullchain_pem;
  $('issued-domain').textContent = result.domain;
  $('certificate-expiry').textContent = 'تاریخ انقضا: ' + new Date(result.expires_at).toLocaleString('fa-IR');
  hide('issue-panel'); show('success-panel'); hide('message');
}));
function downloadPem(content, name) {
  const blob = new Blob([content], {type:'application/x-pem-file'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = name; document.body.appendChild(link); link.click(); link.remove();
  URL.revokeObjectURL(url);
}
$('download-button').addEventListener('click', () => {
  if (issuedPem) downloadPem(issuedPem, currentRequest.domain + '-fullchain.pem');
});
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
  const value = $(button.dataset.copy).textContent;
  try { await navigator.clipboard.writeText(value); message('در حافظه کپی شد.', true); }
  catch { message('کپی خودکار در این مرورگر ممکن نیست؛ متن را دستی کپی کنید.'); }
}));
