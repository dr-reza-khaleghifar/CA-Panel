'use strict';
const $ = id => document.getElementById(id);
let currentRequest = null;
let issuedLinks = null;
let pollTimer = null;
let pollBusy = false;
let downloadDeadline = 0;
function notify(message, good = false) {
  const box = $('message'); box.textContent = message; box.classList.toggle('good', good); box.hidden = false;
}
function clearMessage() { $('message').hidden = true; $('message').textContent = ''; }
function safeApiPath(value) {
  if (typeof value !== 'string' || !value.startsWith('/api/') || value.startsWith('//')) throw new Error('لینک دریافتی از سرور معتبر نیست.');
  const url = new URL(value, location.origin);
  if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) throw new Error('لینک دریافتی از سرور معتبر نیست.');
  return url.pathname + url.search;
}
async function api(path, options = {}) {
  const response = await fetch(path, {cache:'no-store',credentials:'same-origin',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
  const body = await response.json().catch(() => null);
  if (!response.ok) { const error = new Error(typeof body?.detail === 'string' ? body.detail : 'ارتباط با سرور برقرار نشد.'); error.status = response.status; throw error; }
  return body;
}
function faDate(seconds) { return new Intl.DateTimeFormat('fa-IR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(Number(seconds)*1000)); }
function showOnly(ids) { for (const id of ['dns-step','review-step','issue-step','issued-step','rejected-step','already-issued-step']) $(id).hidden = !ids.includes(id); }
function stopPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = null; }
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    if (pollBusy || !currentRequest || document.visibilityState === 'hidden') return;
    pollBusy = true;
    try { const data = await api('/api/requests/' + encodeURIComponent(currentRequest.request_id)); renderStatus(data); }
    catch (error) { if (error.status === 410) { stopPolling(); notify('مهلت درخواست تمام شده است. برای ادامه، درخواست تازه‌ای ثبت کنید.'); } }
    finally { pollBusy = false; }
  }, 12000);
}
function renderStatus(data) {
  currentRequest = data; $('flow-panel').hidden = false; $('request-domain').textContent = data.domain;
  $('request-expiry').textContent = faDate(data.expires_at); $('dns-name').textContent = data.dns_name; $('dns-value').textContent = data.dns_value;
  const expired = Number(data.expires_at)*1000 <= Date.now() && !data.issued; const pill = $('status-pill'); pill.className = 'status-pill';
  if (data.issued) { pill.textContent = 'صادر شده'; pill.classList.add('good'); showOnly(data.download_ready ? ['issued-step'] : ['already-issued-step']); stopPolling(); return; }
  if (expired) { pill.textContent = 'منقضی شده'; pill.classList.add('bad'); showOnly([]); stopPolling(); notify('مهلت درخواست تمام شده است. برای ادامه، درخواست تازه‌ای ثبت کنید.'); return; }
  if (data.approval_status === 'rejected') { pill.textContent = 'رد شده'; pill.classList.add('bad'); showOnly(['rejected-step']); stopPolling(); return; }
  if (!data.verified) { pill.textContent = 'در انتظار DNS'; showOnly(['dns-step']); stopPolling(); return; }
  if (data.approval_status === 'approved') { pill.textContent = 'تأیید مدیر'; pill.classList.add('good'); $('review-title').textContent = 'مالکیت دامنه تأیید و درخواست تصویب شد'; $('review-copy').textContent = 'مدیر CA درخواست را تأیید کرده است. اکنون می‌توانید گواهی را صادر و دریافت کنید.'; showOnly(['review-step','issue-step']); stopPolling(); return; }
  pill.textContent = 'در انتظار بررسی'; $('review-title').textContent = 'مالکیت دامنه تأیید شد'; $('review-copy').textContent = 'درخواست برای بررسی مدیر CA ارسال شده است. وضعیت به‌صورت خودکار به‌روزرسانی می‌شود.'; showOnly(['review-step']); startPolling();
}
function setRequestFragment(id) { history.replaceState(null,'','#request='+encodeURIComponent(id)); }
function clearRequestFragment() { history.replaceState(null,'',location.pathname+location.search); }
async function createRequest(event) {
  event.preventDefault(); clearMessage();
  if (location.protocol !== 'https:' && !['localhost','127.0.0.1','[::1]'].includes(location.hostname)) { notify('برای ثبت درخواست و دریافت امن کلید خصوصی، از نسخه HTTPS سایت استفاده کنید.'); return; }
  const button=$('create-request'); button.disabled=true; button.querySelector('span').textContent='در حال ثبت…';
  try {
    const data=await api('/api/requests',{method:'POST',body:JSON.stringify({domain:$('domain').value.trim()})});
    setRequestFragment(data.request_id); issuedLinks=null; renderStatus(data); notify('درخواست ساخته شد. رکورد TXT را در DNS دامنه ثبت کنید.',true);
  } catch(error) {
    notify(error.status===403?'این دامنه با سیاست فعلی صدور CA مجاز نیست.':error.status===429?'تعداد درخواست‌های مجاز در این بازه به پایان رسیده است؛ بعداً دوباره تلاش کنید.':error.status===503?'سامانه هنوز برای صدور عمومی آماده نیست. لطفاً بعداً مراجعه کنید.':error.message);
  } finally { button.disabled=false; button.querySelector('span').textContent='ثبت درخواست'; }
}
async function verifyDomain() {
  if(!currentRequest)return; const button=$('verify-button'); button.disabled=true; button.querySelector('span').textContent='در حال بررسی…'; clearMessage();
  try { const data=await api('/api/requests/'+encodeURIComponent(currentRequest.request_id)+'/verify',{method:'POST'}); renderStatus(data); if(data.verified)notify('مالکیت دامنه تأیید شد. درخواست اکنون در صف بررسی مدیر قرار دارد.',true); }
  catch(error){notify(error.status===422?'رکورد TXT هنوز در DNS عمومی پیدا نشده یا مقدار آن صحیح نیست.':error.status===429?'تعداد تلاش‌های بررسی تمام شده است.':error.message);}
  finally{button.disabled=false;button.querySelector('span').textContent='بررسی رکورد DNS';}
}
function bindIssuedLinks(data) {
  $('download-button').href=safeApiPath(data.download_url); $('leaf-link').href=safeApiPath(data.certificate_url); $('fullchain-link').href=safeApiPath(data.fullchain_url);
  downloadDeadline=Date.now()+Number(data.download_expires_in_seconds||600)*1000; issuedLinks=data; showOnly(['issued-step']);
  $('status-pill').textContent='صادر شده'; $('status-pill').className='status-pill good';
  $('download-expiry').textContent='لینک خصوصی تا '+faDate(Math.floor(downloadDeadline/1000))+' معتبر است و فقط یک‌بار استفاده می‌شود.';
}
async function issueCertificate() {
  if(!currentRequest)return; const button=$('issue-button'); button.disabled=true; button.querySelector('span').textContent='در حال صدور…'; clearMessage();
  try { const data=await api('/api/requests/'+encodeURIComponent(currentRequest.request_id)+'/issue-server',{method:'POST'}); bindIssuedLinks(data); notify('گواهی صادر شد. بسته ZIP حاوی کلید خصوصی را فوراً و فقط یک‌بار دانلود کنید.',true); stopPolling(); }
  catch(error){notify(error.status===409?'درخواست هنوز در انتظار تأیید مدیر است یا قبلاً صادر شده است.':error.status===403?'اثبات DNS دیگر معتبر نیست یا درخواست رد شده است.':error.status===410?'مهلت درخواست تمام شده است؛ درخواست تازه‌ای ثبت کنید.':error.message);}
  finally{button.disabled=false;button.querySelector('span').textContent='صدور و آماده‌سازی دانلود';}
}
async function restoreRequest() {
  const params=new URLSearchParams(location.hash.slice(1)); const id=params.get('request');
  if(!id||!/^[A-Za-z0-9_-]{32}$/.test(id))return;
  try{const data=await api('/api/requests/'+encodeURIComponent(id));renderStatus(data);notify('درخواست قبلی بازیابی شد. این پیوند محرمانه است؛ آن را به اشتراک نگذارید.',true);}
  catch{clearRequestFragment();notify('درخواست پیدا نشد یا مهلت آن پایان یافته است. در صورت نیاز درخواست تازه‌ای ثبت کنید.');}
}
$('domain-form').addEventListener('submit',createRequest);
$('verify-button').addEventListener('click',verifyDomain);
$('issue-button').addEventListener('click',issueCertificate);
$('copy-request-link').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(location.href);notify('پیوند پیگیری کپی شد؛ آن را محرمانه نگه دارید.',true);}catch{notify('کپی خودکار در این مرورگر فعال نیست. پیوند داخل نوار آدرس را محرمانه نگه دارید.');}});
for(const button of document.querySelectorAll('[data-copy]'))button.addEventListener('click',async()=>{const value=$(button.dataset.copy).textContent;try{await navigator.clipboard.writeText(value);notify('رکورد کپی شد.',true);}catch{notify('کپی خودکار ممکن نیست؛ متن رکورد را انتخاب و کپی کنید.');}});
$('download-button').addEventListener('click',event=>{if(!issuedLinks||Date.now()>=downloadDeadline){event.preventDefault();$('download-button').classList.add('disabled');notify('مهلت دانلود تمام شده است. برای کلید خصوصی جدید، درخواست تازه ثبت کنید.');return;}notify('دانلود آغاز شد. فایل ZIP را در محل امن نگهداری کنید؛ لینک فقط یک‌بار قابل استفاده است.',true);});
restoreRequest();
