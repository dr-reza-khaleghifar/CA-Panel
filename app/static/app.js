'use strict';
// UI state is intentionally ephemeral; never put DNS tokens or private ZIP links in storage.
let currentRequest = null;
let issuedLinks = null;
let deadlineMs = 0;
let zipDeadlineMs = 0;
let stage = 1;
const $ = id => document.getElementById(id);
const show = id => $(id).classList.remove('hidden');
const hide = id => $(id).classList.add('hidden');
const formatFa = date => new Intl.DateTimeFormat('fa-IR', {dateStyle:'medium', timeStyle:'short'}).format(date);

function setLabelSafe(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function displayTransportStatus() {
  const secure = location.protocol === 'https:';
  const local = location.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  setLabelSafe('transport-status', secure ? 'اتصال HTTPS' : local ? 'محیط توسعه محلی' : 'اتصال ناامن');
  setLabelSafe('transport-detail', secure ? 'رمزنگاری در مرورگر برقرار است' : local ? 'دسترسی محدود به localhost' : 'برای صدور، اتصال HTTPS لازم است');
}
// Fetch only intentionally public CA identity and policy (never secrets or paths).
async function loadSystemInformation() {
  try {
    const data = await api('/api/system');
    const setLabel = (id, value) => {
      const el = $(id);
      if (el && typeof value === 'string') el.textContent = value;
    };
    // Branding is the product identity, while these are live PKI metadata.
    setLabel('ca-sidebar-org', data.organization);
    setLabel('ca-topbar-name', 'سرویس صدور فعال');
    setLabel('service-status', 'آماده صدور');
    $('service-status-dot')?.classList.remove('pending', 'unhealthy');
    $('service-status-dot')?.classList.add('healthy');
    $('header-health')?.classList.add('ready');
    $('header-health')?.classList.remove('unavailable');
    setLabel('ca-issuer-name', data.issuer_common_name);
    setLabel('ca-root-name', data.root_common_name);
    setLabel('ca-root-fingerprint', data.root_sha256);
    if (Number.isInteger(data.certificate_validity_days)) {
      setLabel('hero-validity-days', String(data.certificate_validity_days));
      setLabel('dashboard-validity-days', data.certificate_validity_days.toLocaleString('fa-IR'));
    }
    if (Number.isInteger(data.certificate_validity_days)) {
      setLabel('certificate-validity', data.certificate_validity_days.toLocaleString('fa-IR') + ' روز (حداکثر)');
    }
    if (Number.isInteger(data.download_ttl_seconds)) {
      setLabel('zip-max-age', Math.ceil(data.download_ttl_seconds / 60).toLocaleString('fa-IR') + ' دقیقه');
    }
  } catch (_) {
    setLabelSafe('service-status', 'ارتباط برقرار نشد');
    setLabelSafe('ca-topbar-name', 'اتصال نامشخص');
    $('service-status-dot')?.classList.remove('pending', 'healthy');
    $('service-status-dot')?.classList.add('unhealthy');
    $('header-health')?.classList.remove('ready');
    $('header-health')?.classList.add('unavailable');
    // A failed public metadata fetch must not disable the issuance flow.
  }
}


let toastClearTimer = null;
function notify(text, success = false) {
  const banner = $('message');
  banner.textContent = text;
  banner.classList.toggle('good', success);
  banner.classList.remove('hidden');
  const toast = $('toast');
  if (toast) {
    toast.textContent = text;
    toast.classList.toggle('good', success);
    toast.classList.remove('hidden');
    if (toastClearTimer) clearTimeout(toastClearTimer);
    toastClearTimer = setTimeout(() => toast.classList.add('hidden'), 6000);
  }
}
function clearNotice() {
  hide('message');
  $('message').textContent = '';
  const toast = $('toast');
  if (toast) toast.classList.add('hidden');
  if (toastClearTimer) clearTimeout(toastClearTimer);
}
function setStage(value) {
  stage = value;
  for (let n = 1; n <= 3; n++) {
    const node = $('step-' + n);
    node.classList.toggle('selected', n === value);
    node.classList.toggle('complete', n < value);
    if (n === value) node.setAttribute('aria-current', 'step');
    else node.removeAttribute('aria-current');
  }
  for (const [n, id] of [[1, 'domain-panel'], [2, 'dns-panel'], [3, 'issue-panel']]) {
    if (n === value) show(id); else hide(id);
  }
  hide('success-panel');
}
function showSuccess() {
  setStage(3);
  hide('issue-panel');
  show('success-panel');
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: 'no-store', credentials: 'same-origin', ...options,
    headers: {'Content-Type':'application/json', ...(options.headers || {})}
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof result?.detail === 'string' ? result.detail : '';
    const error = new Error(detail || 'اتصال با سرور برقرار نشد؛ دوباره تلاش کنید.');
    error.status = response.status;
    throw error;
  }
  if (!result) throw new Error('پاسخ سرور معتبر نیست. لطفاً دوباره تلاش کنید.');
  return result;
}
function describeError(error, context) {
  if (!error || !error.status) return error?.message || 'ارتباط با سرور ممکن نیست؛ اینترنت و اتصال پنل را بررسی کنید.';
  switch (error.status) {
    case 410: return 'اعتبار این درخواست تمام شده است. برای ادامه، درخواست جدید ثبت کنید.';
    case 429: return 'تعداد تلاش‌های مجاز تمام شده است؛ درخواست تازه ایجاد کنید یا بعداً دوباره تلاش کنید.';
    case 409: return 'برای این درخواست قبلاً گواهی صادر شده است. برای دریافت کلید جدید، درخواست تازه بسازید.';
    case 503: return 'ظرفیت موقت صدور تکمیل شده است؛ کمی بعد دوباره امتحان کنید.';
    case 403: return 'برای صدور، ابتدا باید مالکیت دامنه با رکورد TXT تأیید شود.';
    case 422:
      if (context === 'dns') return 'رکورد TXT مورد انتظار پیدا نشد یا با درخواست فعلی تطابق ندارد. نام رکورد، توکن و انتشار DNS را بررسی کنید.';
      return error.message;
    default: return error.message;
  }
}
async function busy(button, callback, text = 'در حال پردازش…') {
  if (button.disabled) return;
  const label = button.querySelector('span') || button;
  const original = label.textContent;
  button.disabled = true;
  label.textContent = text;
  clearNotice();
  try { await callback(); }
  catch (error) {
    const kind = button.id === 'verify-button' ? 'dns' : 'general';
    notify(describeError(error, kind));
  } finally {
    button.disabled = false;
    label.textContent = original;
    updateTimers();
  }
}
function safeURL(href) {
  if (typeof href !== 'string' || !href.startsWith('/api/') || href.startsWith('//')) throw new Error('لینک دانلود معتبر نیست.');
  const url = new URL(href, location.origin);
  if (url.origin !== location.origin || !url.pathname.startsWith('/api/') || url.username || url.password) {
    throw new Error('لینک دانلود معتبر نیست.');
  }
  return url.pathname + url.search;
}
function bindLinks(data) {
  const links = {
    'download-button': data.download_url,
    'leaf-link': data.certificate_url,
    'fullchain-link': data.fullchain_url,
    'issuer-link': data.issuer_url,
    'root-link': data.root_url
  };
  const validated = Object.fromEntries(Object.entries(links).map(([id, url]) => [id, safeURL(url)]));
  for (const [id, url] of Object.entries(validated)) $(id).href = url;
}
async function issueAutomatically() {
  if (!currentRequest) throw new Error('ابتدا دامنه را ثبت کنید.');
  const rid = encodeURIComponent(currentRequest.request_id);
  const data = await api('/api/requests/' + rid + '/issue-server', {method:'POST'});
  bindLinks(data);
  issuedLinks = data;
  zipDeadlineMs = Date.now() + (Number(data.download_expires_in_seconds) || 600) * 1000;
  $('issued-domain').textContent = data.domain;
  $('certificate-expiry').textContent = formatFa(new Date(data.expires_at));
  showSuccess();
  notify('گواهی با موفقیت صادر شد. ابتدا ZIP حاوی کلید خصوصی را دانلود کنید؛ لینک فقط یک‌بار قابل استفاده است.', true);
}
function isSafeTransport() {
  return location.protocol === 'https:' || (location.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname));
}
function updateTimers() {
  if (currentRequest && stage === 2) {
    const remaining = Math.max(0, Math.ceil((deadlineMs - Date.now()) / 60000));
    $('challenge-expiry').textContent = remaining ? `${remaining.toLocaleString('fa-IR')} دقیقه باقی مانده` : 'منقضی شده؛ درخواست جدید بسازید';
    $('verify-button').disabled = !remaining;
  }
  if (issuedLinks && stage === 3 && !$('success-panel').classList.contains('hidden')) {
    const remaining = Math.max(0, Math.ceil((zipDeadlineMs - Date.now()) / 60000));
    $('download-expiry').textContent = remaining ? `حداکثر ${remaining.toLocaleString('fa-IR')} دقیقه فرصت دانلود دارید` : 'مهلت دانلود ZIP تمام شده؛ درخواست تازه بسازید';
    const expired = !remaining;
    $('download-button').classList.toggle('disabled-link', expired);
    $('download-button').setAttribute('aria-disabled', String(expired));
    $('download-button').tabIndex = expired ? -1 : 0;
    $('download-button').closest('.private-download').classList.toggle('expired', expired);
  }
}
function resetFlow() {
  if (issuedLinks && !window.confirm('لینک خصوصی ZIP پس از ترک این صفحه قابل بازیابی نیست. آیا برای گواهی جدید ادامه می‌دهید؟')) return;
  currentRequest = null;
  issuedLinks = null;
  deadlineMs = 0;
  zipDeadlineMs = 0;
  $('domain-form').reset();
  $('download-button').removeAttribute('href');
  clearNotice();
  setStage(1);
  $('domain').focus();
  document.getElementById('workspace').scrollIntoView({behavior:'smooth', block:'start'});
}

$('domain-form').addEventListener('submit', event => {
  event.preventDefault();
  busy($('domain-submit'), async () => {
    if (!isSafeTransport()) throw new Error('برای حفاظت از کلید خصوصی، پنل باید با HTTPS باز شود (یا روی localhost باشد).');
    const data = await api('/api/requests', {method:'POST', body:JSON.stringify({domain:$('domain').value.trim()})});
    currentRequest = data;
    issuedLinks = null;
    deadlineMs = Number(data.expires_at) * 1000;
    $('dns-name').textContent = data.dns_name;
    $('dns-value').textContent = data.dns_value;
    $('request-domain').textContent = data.domain;
    setStage(2);
    updateTimers();
  }, 'در حال ثبت…');
});
$('verify-button').addEventListener('click', () => busy($('verify-button'), async () => {
  if (!currentRequest) throw new Error('ابتدا درخواست دامنه ثبت کنید.');
  const rid = encodeURIComponent(currentRequest.request_id);
  const verified = await api('/api/requests/' + rid + '/verify', {method:'POST'});
  if (!verified.verified) throw new Error('تأیید مالکیت انجام نشد.');
  setStage(3);
  await issueAutomatically();
}, 'در حال تأیید و صدور…'));
$('issue-button').addEventListener('click', () => busy($('issue-button'), issueAutomatically, 'در حال صدور…'));
for (const button of document.querySelectorAll('[data-reset]')) button.addEventListener('click', resetFlow);
for (const button of document.querySelectorAll('[data-copy]')) {
  button.addEventListener('click', async () => {
    const value = $(button.dataset.copy)?.textContent || '';
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(value);
      notify('مقدار در کلیپ‌بورد کپی شد.', true);
    } catch {
      notify('کپی خودکار در این مرورگر در دسترس نیست؛ متن را انتخاب و دستی کپی کنید.');
    }
  });
}
$('download-button').addEventListener('click', event => {
  if (Date.now() >= zipDeadlineMs || !issuedLinks) { event.preventDefault(); updateTimers(); return; }
  // Do not fetch/preview a one-time bearer URL. Native navigation handles the download.
  notify('درخواست دانلود ارسال شد. ZIP را در مکانی امن ذخیره کنید؛ لینک فقط یک بار قابل استفاده است.', true);
});

// Enterprise UI is dark-only; no user-controlled theme or saved preference.
document.documentElement.setAttribute('data-theme', 'dark');
displayTransportStatus();
setInterval(updateTimers, 20000);
setStage(1);
loadSystemInformation();
