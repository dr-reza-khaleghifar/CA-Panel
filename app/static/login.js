'use strict';
const form = document.getElementById('login-form');
const submit = document.getElementById('login-submit');
const notice = document.getElementById('login-notice');
const showError = text => { notice.textContent = text; notice.classList.remove('hidden'); };
if (location.protocol !== 'https:' && !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)) {
  form.querySelectorAll('input, button').forEach(element => element.disabled = true);
  showError('برای ورود مدیر، ابتدا از HTTPS مورد اعتماد استفاده کنید. گذرواژه را روی HTTP ارسال نکنید.');
} else {
  fetch('/api/auth/status', {cache:'no-store', credentials:'same-origin'})
    .then(response => response.json())
    .then(data => {
      if (data.authenticated) location.replace('/');
      else if (!data.configured) showError('حساب مدیر هنوز روی سرور فعال نشده است؛ ابتدا راه‌اندازی اولیه را انجام دهید.');
    }).catch(() => showError('اتصال به سرور برقرار نشد. وضعیت HTTPS و سرویس را بررسی کنید.'));
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (submit.disabled) return;
  notice.classList.add('hidden');
  submit.disabled = true;
  submit.textContent = 'در حال اعتبارسنجی…';
  try {
    const response = await fetch('/api/auth/login', {
      method:'POST', credentials:'same-origin', cache:'no-store',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        username:document.getElementById('login-username').value.trim(),
        password:document.getElementById('login-password').value,
        code:document.getElementById('login-code').value.trim()
      })
    });
    document.getElementById('login-password').value = '';
    document.getElementById('login-code').value = '';
    if (!response.ok) {
      showError(response.status === 503 ? 'حساب مدیر هنوز روی سرور راه‌اندازی نشده است.' :
        response.status === 429 ? 'تلاش‌های ورود بیش از حد مجاز است؛ بعداً دوباره امتحان کنید.' :
        'ورود انجام نشد؛ نام کاربری، رمز و کد یک‌بارمصرف را بررسی کنید.');
      return;
    }
    location.replace('/');
  } catch {
    showError('برقراری ارتباط امن با سرور ممکن نشد.');
  } finally {
    submit.disabled = false;
    submit.textContent = 'ورود امن به سامانه';
  }
});
