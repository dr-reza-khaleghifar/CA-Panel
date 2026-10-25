# راهنمای رابط کاربری CA-Panel

## اصول طراحی
- زبان فارسی و چیدمان RTL، با نمایش LTR برای دامنه، TXT و نام فایل‌ها.
- نمایش واکنش‌گرا در موبایل ۳۲۰، ۳۹۰، ۷۶۸، ۱۰۲۴ و دسکتاپ ۱۴۴۰ پیکسل.
- دو تم روشن و تیره با دکمه تغییر تم؛ فقط **انتخاب تم** در localStorage ذخیره می‌شود. هیچ توکن DNS یا لینک ZIP در storage ثبت نمی‌شود.
- سه مرحله دیداری: ثبت دامنه، اثبات مالکیت با DNS TXT، و دانلود نتیجه صدور.
- کنترل‌های قابل استفاده با صفحه‌کلید، برچسب فرم، وضعیت live برای خطا/موفقیت و پشتیبانی از prefers-reduced-motion.
- فایل‌های JS/CSS محلی و بدون وابستگی به CDN؛ سازگار با Content-Security-Policy فعلی.

## جریان‌های اصلی
1. **شروع:** دامنه یا URL وارد می‌شود و POST /api/requests صدا زده می‌شود. برای حفاظت از کلید، دسترسی اینترنتی از طریق HTTP ناامن در رابط مسدود شده و HTTPS توصیه می‌شود (localhost برای توسعه مجاز است).
2. **DNS:** نام و مقدار TXT با دکمه کپی، دامنه در حال تأیید، و زمان باقی‌مانده درخواست نمایش داده می‌شوند. POST /verify نتیجه را مشخص می‌کند و پس از موفقیت POST /issue-server اجرا می‌شود.
3. **صدور:** اگر صدور با خطا متوقف شود، مرحله سوم و دکمه تلاش مجدد نمایش داده می‌شوند. اگر صدور قبلاً اتفاق افتاده باشد، باید درخواست جدید ایجاد شود.
4. **دانلود:** لینک ZIP شامل کلید خصوصی بسیار واضح از سایر فایل‌های PEM/CRT جدا شده است. ZIP فقط یک بار و تا ۱۰ دقیقه قابل دریافت است و زمان تقریبی باقی‌مانده نمایش داده می‌شود. لینک‌های گواهی عمومی جداگانه باقی می‌مانند.
5. **شروع دوباره:** با شروع درخواست جدید، شناسه درخواست و لینک‌ها از حافظه جاوااسکریپت پاک می‌شوند. پیش از ترک نتیجه صدور، هشدار از دست‌رفتن لینک خصوصی نمایش داده می‌شود.
6. **خطاها:** 403، 409، 410، 422، 429 و 503 پیام‌های قابل فهم فارسی دارند. مشکل انتشار DNS و تطبیق توکن به‌صورت راهنما توضیح داده شده است.

## نکات امنیتی و محدودیت‌ها
- رابط ظاهر و تجربه کاربر را بهتر می‌کند، اما **سیاست اعتبارسنجی DNS یا سرور CA** را تغییر نمی‌دهد.
- لینک خصوصی نباید برای پیش‌نمایش یا fetch خودکار درخواست شود؛ دانلود با navigation بومی مرورگر انجام می‌شود.
- زمان انقضای نمایشی بر اساس ساعت مرورگر است. **اعتبار نهایی همیشه توسط سرور بررسی می‌شود.**
- این یک **Private CA** است؛ گواهی‌های صادرشده به‌طور پیش‌فرض مورد اعتماد مرورگرهای عمومی نیستند.
- تم تیره و واکنش‌گرایی در Chromium بررسی شده‌اند؛ برای استقرار عمومی، آزمون مرورگرها و بازبینی دسترس‌پذیری بیشتر توصیه می‌شود.

## اجرای محلی
```bash
docker compose up -d --build --force-recreate api
curl http://127.0.0.1:8080/healthz
```

سپس صفحه را بازخوانی کامل کنید (Shift + Reload) تا CSS و JavaScript جدید بارگذاری شوند.


## تایپوگرافی و طراحی V3

در این نسخه فونت فارسی **Vazirmatn** (وزیرمتن) به جای Tahoma استفاده شده و ترکیب رنگی به سرمه‌ای عمیق + سبز فیروزه‌ای تغییر کرده است. اندازه فونت پایه از ۱۴ به ۱۶ پیکسل افزایش یافته و تیترها، راهنماهای DNS و دکمه‌های دانلود برای نمایش موبایل و دسکتاپ خواناتر شده‌اند.

**مجوز فونت:** Copyright 2015 Vazirmatn Project Authors؛ SIL Open Font License 1.1 — https://github.com/rastikerdar/vazirmatn

فونت **Vazirmatn** در نسخه فعلی به‌صورت اختیاری از داخل برنامه بارگذاری می‌شود؛ دانلود اولیه آن باید روی میزبان با `python3 scripts/install_font.py` انجام شده باشد. در زمان Docker build یا استفاده از پنل هیچ تماس اجباری با Google Fonts وجود ندارد. در صورت نصب‌نبودن فایل، فونت سیستمی جایگزین می‌شود.

فایل اصلی `style.css` برای سازگاری حفظ شده و override جدید در `app/static/v3.css` قرار دارد. API امضا، اعتبارسنجی مالکیت و لینک یک‌بارمصرف خصوصی بدون تغییر باقی مانده‌اند.

## نسخه ۰.۴ — ارتقای هویت بصری و فونت

- بازطراحی ظریف با فضای سفید بیشتر، تایپوگرافی درشت‌تر، کارت گواهی چندلایه، نشان‌های شیشه‌ای، نشانگر پیشرفت و نمای دانلود برجسته؛ تمامی بخش‌ها برای فارسی RTL طراحی شده‌اند.
- فونت متغیر **Vazirmatn** از پروژه آزاد [Vazirmatn](https://github.com/rastikerdar/vazirmatn) (مجوز SIL OFL 1.1) به‌صورت **اختیاری روی میزبان** دریافت و با SHA قفل‌شده تأیید می‌شود. Docker آن را بدون درخواست شبکه داخل تصویر کپی می‌کند. مجوز OFL همراه فایل‌های static توزیع می‌شود.
- رنگ‌بندی اصلی: فضای روشن خنثی و سرمه‌ایِ عمیق، تأکید فیروزه‌ای و نارنجی محدود. تم تیره سازگار، کنتراست و Focus قابل مشاهده، پشتیبانی از `prefers-reduced-motion` و وضعیت‌های فعال/خطا حفظ شده‌اند.
- فایل `app/static/v4.css` یک لایه بصری مستقل روی استایل پایه است تا مسیرهای API، شناسه دکمه‌ها و رفتار امنیتی تغییر نکنند.
- برای بررسی، پنل را پس از Docker build کامل با Hard Refresh باز کنید. اگر فونت را روی میزبان نصب کرده‌اید، درخواست `GET /static/fonts/Vazirmatn.woff2` باید 200 باشد. در غیر این صورت فایل اختیاری نصب نیست و 404 طبیعی است.


## Fix for SSL CERTIFICATE_VERIFY_FAILED during Docker font download

Previous Dockerfile downloaded the font during image construction. In TLS-intercepted environments it could fail with `[SSL: CERTIFICATE_VERIFY_FAILED] ... self-signed certificate`, preventing the **entire CA-Panel** from starting.

The current Dockerfile **does not fetch a font or make any HTTPS connection during the font-install step**. It builds even when the font is not installed, using the system font fallback. For best Persian typography, run this **on the Docker host, outside the container**, before building (macOS Python/curl may have access to different trusted certificates):

```bash
python3 scripts/install_font.py
docker compose up -d --build --force-recreate api
curl -I http://127.0.0.1:8080/static/fonts/Vazirmatn.woff2
```

The helper downloads a **pinned version** of the open-source Vazirmatn variable font over certificate-verified HTTPS, verifies its exact Git object digest, and writes to `app/static/fonts/Vazirmatn.woff2`; the Docker `COPY app ./app` step then bundles the verified binary. The file is intentionally gitignored; the OFL license is included in the repository.

If host-side certificate verification also fails, **do not disable TLS checks**. Download the font from its [pinned upstream link](https://raw.githubusercontent.com/rastikerdar/vazirmatn/6e553e33489a8f9dfaccc76860a2e3f3c1e66de7/fonts/webfonts/Vazirmatn%5Bwght%5D.woff2) through a trusted network/browser and run `python3 scripts/install_font.py --file /path/to/downloaded.woff2`. The same cryptographic digest validation is required.

You may instead skip the optional font setup: `git pull && docker compose up -d --build --force-recreate api` now works without it. HTTP 404 for the optional font in that case is expected; no certificate or issuance features are affected.


## نسخه ۰.۵ — ناوبری واقعی و بازطراحی جزئیات
- منوها اکنون به بخش‌های واقعی «صدور گواهی»، «مراحل دریافت»، «سؤالات متداول» و «راهنمای امنیت» متصل هستند؛ بخش فعال هنگام اسکرول و کلیک به‌روزرسانی می‌شود.
- در موبایل و تبلت (تا ۹۸۰px) منوی کناری به کشوی قابل باز و بسته‌کردن تبدیل شده است. دکمه منو وضعیت `aria-expanded` دارد و بستن با دکمه، بیرون منو و کلید Escape کار می‌کند.
- پیمایش منو بدون ریفرش صفحه انجام می‌شود، بنابراین DNS token و لینک یک‌بارمصرف ZIP در حافظه از دست نمی‌رود.
- بخش پرسش‌های متداول با پنل‌های بازشونده اضافه شد. لینک‌های منو به بخش‌های واقعی اشاره می‌کنند؛ هیچ مسیر یا API جعلی اضافه نشده است.
- فایل‌های `v5.css` و `navigation.js` محلی هستند و با CSP سخت‌گیرانه فعلی کار می‌کنند؛ هیچ وابستگی خارجی یا فونت جدیدی برای Docker build اضافه نشده است.
- این تغییر فقط UI است و منطق FastAPI، اعتبارسنجی TXT، امضا و دانلود خصوصی ZIP را تغییر نمی‌دهد.


## Environment-driven public CA information
The sidebar and top bar display `CA_DISPLAY_NAME` and `CA_ORGANIZATION` from `GET /api/system`. The Security panel displays the Issuing and Root certificate Common Names and the public Root SHA-256 fingerprint, all sourced from actual mounted PEM files. The issuance success screen reads the configured maximum leaf validity and download-link TTL. UI fields are populated using `textContent`, never injected HTML. The metadata request does not log or persist private ZIP tokens. A failed metadata request does not block issuance.
