'use strict';
const byId = id => document.getElementById(id);
function setText(id, value) {
  const node = byId(id);
  if (node && typeof value === 'string') node.textContent = value;
}
async function loadPublicInformation() {
  try {
    const response = await fetch('/api/system', {cache:'no-store', credentials:'same-origin'});
    if (!response.ok) throw new Error('metadata unavailable');
    const data = await response.json();
    setText('landing-root-name', data.root_common_name || '—');
    setText('landing-issuer-name', data.issuer_common_name || '—');
    setText('landing-root-fingerprint', data.root_sha256 || '—');
    if (Number.isInteger(data.certificate_validity_days)) {
      setText('landing-validity-days', data.certificate_validity_days.toLocaleString('fa-IR'));
    }
    const enabled = data.public_issuance_enabled === true;
    setText('landing-service-status', enabled ? 'سامانه آماده دریافت درخواست است' : 'صدور عمومی در انتظار تنظیمات مدیر است');
    byId('landing-status-dot')?.classList.toggle('is-ready', enabled);
    byId('landing-status-dot')?.classList.toggle('is-pending', !enabled);
    document.querySelectorAll('.site-button[href="/issue"]').forEach(link => {
      link.setAttribute('aria-disabled', String(!enabled));
      link.classList.toggle('is-unavailable', !enabled);
    });
  } catch (_) {
    setText('landing-service-status', 'وضعیت سرویس در حال حاضر قابل دریافت نیست');
    byId('landing-status-dot')?.classList.add('is-pending');
  }
}
byId('copy-fingerprint')?.addEventListener('click', async () => {
  const value = byId('landing-root-fingerprint')?.textContent || '';
  if (!value || value === 'در حال دریافت…' || value === '—') return;
  try {
    await navigator.clipboard.writeText(value);
    const button = byId('copy-fingerprint');
    const original = button.innerHTML;
    button.textContent = 'کپی شد';
    window.setTimeout(() => { button.innerHTML = original; }, 1800);
  } catch (_) {
    const range = document.createRange();
    range.selectNodeContents(byId('landing-root-fingerprint'));
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
});
loadPublicInformation();