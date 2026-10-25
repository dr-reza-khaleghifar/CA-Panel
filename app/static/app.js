'use strict';
let currentRequest = null;
let generated = null; // In-memory only: contains browser-generated private key and signed CSR.
let issuedArchive = null;
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
  const response = await fetch(path, {cache: 'no-store', ...options,
    headers: {'Content-Type':'application/json', ...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'درخواست ناموفق بود.');
    error.status = response.status;
    throw error;
  }
  return data;
}
async function busy(button, callback, label = 'در حال پردازش…') {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = label;
  hide('message');
  try { await callback(); } catch (err) { message(err.message || 'خطای غیرمنتظره'); }
  finally { button.disabled = false; button.textContent = original; }
}
function downloadArchive() {
  if (!issuedArchive || !currentRequest) return;
  const url = URL.createObjectURL(issuedArchive);
  const link = document.createElement('a');
  link.href = url;
  link.download = currentRequest.domain + '-certificates.zip';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
async function issueAutomatically() {
  if (!CAPanelCert.isSupported()) {
    throw new Error('برای صدور خودکار باید پنل را با HTTPS یا localhost باز کنید (Web Crypto الزامی است).');
  }
  if (!generated) generated = await CAPanelCert.generateCSR(currentRequest.domain);
  const rid = encodeURIComponent(currentRequest.request_id);
  let result;
  try {
    result = await api('/api/requests/' + rid + '/issue', {
      method:'POST', body:JSON.stringify({csr_pem:generated.csrPem})
    });
  } catch (error) {
    if (error.status === 409) {
      throw new Error('گواهی این درخواست قبلاً صادر شده است. برای جلوگیری از تحویل کلید نامنطبق، درخواست جدید ایجاد کنید.');
    }
    throw error;
  }
  const files = CAPanelCert.makeBundleFiles(result, generated.privateKeyPem);
  issuedArchive = CAPanelCert.createZip(files);
  $('issued-domain').textContent = result.domain;
  $('certificate-expiry').textContent = 'انقضا: ' + new Date(result.expires_at).toLocaleString('fa-IR');
  hide('issue-panel'); hide('dns-panel'); show('success-panel'); step(3);
  message('صدور گواهی انجام شد. اگر دانلود خودکار شروع نشد، از دکمه دانلود ZIP استفاده کنید.', true);
  downloadArchive();
}
$('domain-form').addEventListener('submit', event => {
  event.preventDefault();
  busy($('domain-submit'), async () => {
    if (!CAPanelCert.isSupported()) {
      throw new Error('برای ساخت کلید خصوصی باید پنل را از طریق HTTPS یا localhost باز کنید.');
    }
    const data = await api('/api/requests', {method:'POST', body:JSON.stringify({domain:$('domain').value})});
    currentRequest = data;
    generated = null;
    issuedArchive = null;
    $('dns-name').textContent = data.dns_name;
    $('dns-value').textContent = data.dns_value;
    hide('domain-panel'); show('dns-panel'); step(2);
  });
});
$('verify-button').addEventListener('click', () => busy($('verify-button'), async () => {
  if (!CAPanelCert.isSupported()) {
    throw new Error('Web Crypto فقط روی HTTPS یا localhost قابل استفاده است.');
  }
  const rid = encodeURIComponent(currentRequest.request_id);
  const result = await api('/api/requests/' + rid + '/verify', {method:'POST'});
  if (!result.verified) throw new Error('مالکیت دامنه تأیید نشد.');
  hide('dns-panel'); show('issue-panel'); step(3);
  message('مالکیت دامنه تأیید شد؛ کلید و گواهی در حال ایجاد هستند.', true);
  await issueAutomatically();
}, 'در حال تأیید و ساخت گواهی…'));
$('issue-button').addEventListener('click', () => busy($('issue-button'), issueAutomatically,
  'در حال ساخت گواهی…'));
$('download-button').addEventListener('click', downloadArchive);
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
  const value = $(button.dataset.copy).textContent;
  try { await navigator.clipboard.writeText(value); message('در حافظه کپی شد.', true); }
  catch { message('کپی خودکار در این مرورگر ممکن نیست؛ متن را دستی کپی کنید.'); }
}));
