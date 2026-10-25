'use strict';
let currentRequest = null;
let issuedLinks = null;
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
  const response = await fetch(path, {cache:'no-store', ...options,
    headers: {'Content-Type':'application/json', ...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'درخواست ناموفق بود.');
    error.status = response.status;
    throw error;
  }
  return data;
}
async function busy(button, callback, progress='در حال پردازش…') {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = progress;
  hide('message');
  try { await callback(); } catch (err) { message(err.message || 'خطای غیرمنتظره'); }
  finally { button.disabled = false; button.textContent = original; }
}
function assignLink(id, href) {
  // Server returns relative same-origin URLs only; never allow an attacker-controlled redirect.
  const url = new URL(href, location.origin);
  if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) throw new Error('لینک دانلود نامعتبر است.');
  $(id).href = url.pathname + url.search;
}
async function issueAutomatically() {
  const rid = encodeURIComponent(currentRequest.request_id);
  let data;
  try {
    data = await api('/api/requests/' + rid + '/issue-server', {method:'POST'});
  } catch (error) {
    if (error.status === 409) {
      throw new Error('این درخواست قبلاً گواهی دریافت کرده است. برای دریافت کلید خصوصی جدید، یک درخواست تازه بسازید.');
    }
    throw error;
  }
  issuedLinks = data;
  assignLink('download-button', data.download_url);
  assignLink('leaf-link', data.certificate_url);
  assignLink('fullchain-link', data.fullchain_url);
  assignLink('issuer-link', data.issuer_url);
  assignLink('root-link', data.root_url);
  $('issued-domain').textContent = data.domain;
  $('certificate-expiry').textContent = 'اعتبار گواهی تا: ' + new Date(data.expires_at).toLocaleString('fa-IR');
  hide('dns-panel'); hide('issue-panel'); show('success-panel'); step(3);
  message('گواهی صادر شد؛ لینک ZIP خصوصی فقط یک بار و تا ۱۰ دقیقه قابل دریافت است. هم‌اکنون دانلود کنید.', true);
}
$('domain-form').addEventListener('submit', event => {
  event.preventDefault();
  busy($('domain-submit'), async () => {
    const data = await api('/api/requests', {method:'POST', body:JSON.stringify({domain:$('domain').value})});
    currentRequest = data;
    issuedLinks = null;
    $('dns-name').textContent = data.dns_name;
    $('dns-value').textContent = data.dns_value;
    hide('domain-panel'); show('dns-panel'); hide('success-panel'); step(2);
  });
});
$('verify-button').addEventListener('click', () => busy($('verify-button'), async () => {
  const rid = encodeURIComponent(currentRequest.request_id);
  const result = await api('/api/requests/' + rid + '/verify', {method:'POST'});
  if (!result.verified) throw new Error('مالکیت دامنه تأیید نشد.');
  hide('dns-panel'); show('issue-panel'); step(3);
  await issueAutomatically();
}, 'در حال تأیید DNS و صدور گواهی…'));
$('issue-button').addEventListener('click', () => busy($('issue-button'), issueAutomatically, 'در حال امضای گواهی…'));
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
  const value = $(button.dataset.copy).textContent;
  try { await navigator.clipboard.writeText(value); message('در حافظه کپی شد.', true); }
  catch { message('کپی خودکار ممکن نیست؛ متن را دستی کپی کنید.'); }
}));
