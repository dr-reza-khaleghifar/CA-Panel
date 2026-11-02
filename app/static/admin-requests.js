'use strict';
const $ = id => document.getElementById(id);
let csrfToken = null;
const dateFa = value => new Intl.DateTimeFormat('fa-IR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(Number(value)*1000));
function message(value){$('queue-message').textContent=value;}
async function api(path,options={}){
 const method=String(options.method||'GET').toUpperCase();
 const headers={'Content-Type':'application/json',...(options.headers||{})};
 if(method!=='GET'&&method!=='HEAD')headers['X-CSRF-Token']=csrfToken;
 const response=await fetch(path,{cache:'no-store',credentials:'same-origin',...options,headers});
 const body=await response.json().catch(()=>null);
 if(response.status===401){location.replace('/login');throw new Error('نشست مدیر منقضی شده است.');}
 if(!response.ok)throw new Error(typeof body?.detail==='string'?body.detail:'عملیات انجام نشد.');
 return body;
}
function addText(parent,tag,className,text){
 const el=document.createElement(tag);if(className)el.className=className;el.textContent=text;parent.append(el);return el;
}
function renderRequest(item){
 const card=document.createElement('article');card.className='request-card';card.dataset.id=item.request_id;
 const head=document.createElement('div');head.className='request-card-head';card.append(head);
 addText(head,'h2','',item.domain);
 addText(head,'span','request-state '+item.approval_status,item.approval_status==='pending'?'در انتظار بررسی':item.approval_status==='approved'?'تأیید شده':'رد شده');
 const meta=document.createElement('div');meta.className='request-meta';card.append(meta);
 addText(meta,'span','','ثبت: '+dateFa(item.created_at));
 addText(meta,'span','','انقضا: '+dateFa(item.expires_at));
 addText(meta,'span','',item.verified?'اثبات DNS: تأیید شده':'اثبات DNS: انجام نشده');
 if(item.issued)addText(meta,'span','','گواهی صادر شده');
 if(item.reviewed_at)addText(meta,'span','','بررسی: '+dateFa(item.reviewed_at));
 if(item.review_note)addText(meta,'p','','یادداشت مدیر: '+item.review_note);
 if(item.approval_status==='pending'){
  const note=document.createElement('textarea');note.className='request-review-note';note.placeholder='یادداشت داخلی برای رد درخواست (اختیاری)';note.maxLength=254;card.append(note);
  const actions=document.createElement('div');actions.className='request-actions';card.append(actions);
  const approve=document.createElement('button');approve.type='button';approve.className='approve';approve.dataset.action='approve';approve.textContent='تأیید درخواست';approve.disabled=!item.verified||Number(item.expires_at)*1000<=Date.now();actions.append(approve);
  const reject=document.createElement('button');reject.type='button';reject.className='reject';reject.dataset.action='reject';reject.textContent='رد درخواست';actions.append(reject);
 }
 return card;
}
async function loadQueue(){
 const list=$('request-list');list.replaceChildren();message('در حال دریافت درخواست‌ها…');
 try{
  const data=await api('/api/admin/requests?status='+encodeURIComponent($('status-filter').value));
  if(!data.requests.length){addText(list,'div','empty-queue','درخواستی در این وضعیت وجود ندارد.');message('');return;}
  for(const item of data.requests)list.append(renderRequest(item));
  message(data.requests.length.toLocaleString('fa-IR')+' درخواست نمایش داده شد.');
 }catch(error){message(error.message);}
}
async function init(){
 try{
  const response=await fetch('/api/auth/status',{cache:'no-store',credentials:'same-origin'});const status=await response.json();
  if(!response.ok||!status.authenticated||typeof status.csrf_token!=='string'){location.replace('/login');return;}
  csrfToken=status.csrf_token;await loadQueue();
 }catch{message('اتصال به سرویس مدیریت برقرار نشد.');}
}
$('status-filter').addEventListener('change',loadQueue);
$('refresh-queue').addEventListener('click',loadQueue);
$('request-list').addEventListener('click',async event=>{
 const button=event.target.closest('button[data-action]');if(!button||button.disabled)return;
 const card=button.closest('.request-card');const id=card?.dataset.id;if(!id)return;
 const action=button.dataset.action;const path='/api/admin/requests/'+encodeURIComponent(id)+'/'+action;
 const body=action==='reject'?JSON.stringify({note:card.querySelector('.request-review-note')?.value||''}):undefined;
 button.disabled=true;message(action==='approve'?'در حال تأیید درخواست…':'در حال رد درخواست…');
 try{await api(path,{method:'POST',...(body?{body}:{})});message('وضعیت درخواست به‌روزرسانی شد.');await loadQueue();}
 catch(error){message(error.message);button.disabled=false;}
});
init();
