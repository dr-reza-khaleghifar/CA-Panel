# اعتماد خودکار به CA پردیس در Firefox معمولی (بدون مرورگر اختصاصی)

گواهی HTTPS سامانه `ca1.iravand.ir` با `Pardis AI Innovation Root CA` خصوصی امضا شده است. **Firefox عمومی این Root را پیش‌فرض نمی‌شناسد**؛ هیچ تنظیم سایت، جاوااسکریپت، افزونه عادی یا تنظیم Ubuntu نمی‌تواند از راه دور و بدون مجوز کاربر یک Root را در دستگاه او مورد اعتماد کند.

راهکار استاندارد Mozilla سیاست سازمانی `Certificates.Install` است. Firefox منتشرشده توسط Mozilla بدون تغییر و بدون مرورگر سفارشی اجرا می‌شود.

منبع رسمی:
- https://firefox-admin-docs.mozilla.org/reference/policies/certificates/
- https://firefox-admin-docs.mozilla.org/guides/policies-configuration/

## راهنمای HTTP برای اولین اتصال

اگر به دلیل عدم اعتماد به Root CA نمی‌توانید `https://ca1.iravand.ir` را باز کنید، راهنمای استاتیک و عمومی نصب Root روی **http://ca1.iravand.ir/** قابل مشاهده است (در صورت دسترسی به پورت ۸۰). **این صفحه مخصوص ورود یا صدور گواهی نیست** و هیچ API محرمانه‌ای روی HTTP ارائه نمی‌شود. HTTP فقط راهنمای متنی ارائه می‌کند و **گواهی Root را برای دانلود عرضه نمی‌کند**. گواهی ریشه باید از مدیر CA و از **کانالی مستقل و از قبل مورد اعتماد** دریافت و پس از تطبیق اثر انگشت SHA-256 نصب شود. انتقال خودکار از شکست TLS به HTTP ممکن نیست؛ در حالت HTTPS-Only یا HSTS، از کانال مستقل مدیریتی برای دریافت Root استفاده کنید.

## گام ۱: تهیه عمومی Root CA از Ubuntu

روی سرور CA-Panel:

```bash
cd ~/CA-Panel
openssl x509 -in secrets/online/root-cert.pem -outform DER -out ~/pardis-root.cer
openssl x509 -in secrets/online/root-cert.pem -noout -fingerprint -sha256
```

**فقط گواهی عمومی Root** (`pardis-root.cer`) را منتشر کنید، هرگز `root-key.pem`، `issuer-key.pem` یا `.env` را منتشر نکنید. اثر انگشت SHA-256 را از یک کانال مستقل و تأییدشده با مدیران و کاربران به اشتراک بگذارید. به فایلی که از اینترنت دریافت شده، صرفاً به خاطر نام آن اعتماد نکنید.

## گام ۲ (سازمانی): فعال‌سازی بدون اقدام کاربر با Group Policy / Intune

اگر دستگاه‌ها تحت مدیریت شما هستند، اول فایل `pardis-root.cer` را با ابزار مدیریت کلاینت پس از بررسی fingerprint به این مسیر یکسان روی هر رایانه منتقل کنید:

```text
C:\ProgramData\Pardis\Certificates\pardis-root.cer
```

سپس با Firefox Administrative Templates (GPO) یا Intune سیاست زیر را فعال کنید:

```text
Certificates > Install
C:\ProgramData\Pardis\Certificates\pardis-root.cer
```

این مسیر نمونه برای Windows است. قالب و ساختار دقیق GPO در مستندات Mozilla بالا آمده است.

پس از اعمال سیاست و راه‌اندازی مجدد Firefox، در آدرس `about:policies#active` باید بخش `Certificates.Install` دیده شود؛ سپس `https://ca1.iravand.ir` را باز کنید. این روش روی Firefox استاندارد نصب‌شده کار می‌کند و روی دستگاه‌های سازمانی می‌تواند **کاملاً بدون اقدام کاربر نهایی** باشد؛ دسترسی مدیر سازمان و ابزار مدیریت دستگاه لازم است.

اگر Windows Root store از قبل به‌صورت سازمانی مدیریت می‌شود، یک گزینه جایگزین `Certificates.ImportEnterpriseRoots=true` است که Firefox را به Rootهای نصب‌شده در مخزن گواهی سیستم‌عامل Windows/macOS متصل می‌کند. **این گزینه برای Linux کار نمی‌کند** و دامنه اعتماد سیستم‌عامل را وارد Firefox می‌کند؛ برای کنترل محدودتر به خود Firefox، از `Certificates.Install` استفاده کنید.

## گام ۳ (یک رایانه Windows): نصب آسان روی Firefox معمولی

برای یک رایانه دارای مالک/مدیر مشخص، به جای مرورگر اختصاصی می‌توانید اسکریپت `scripts/configure_firefox_trust.ps1` این مخزن را از PowerShell مدیر اجرا کنید.

۱. روی رایانه ویندوزی، فایل DER گواهی را از Ubuntu با کانال SSH بگیرید:

```powershell
scp ca1@194.225.146.90:/home/ca1/pardis-root.cer "$env:USERPROFILE\Downloads\pardis-root.cer"
```

۲. اثر انگشت عمومی SHA-256 را **مستقل** از سرور دریافت و بررسی کنید. سپس PowerShell را با گزینه **Run as administrator** باز کنید. از داخل نسخه دریافت‌شده و مورد اعتماد مخزن اجرا کنید:

```powershell
& ".\scripts\configure_firefox_trust.ps1" -RootCertificatePath "$env:USERPROFILE\Downloads\pardis-root.cer" -ExpectedSha256 "FINGERPRINT_FROM_UBUNTU"
```

جای `FINGERPRINT_FROM_UBUNTU` مقدار ۶۴ کاراکتری واقعی `openssl -fingerprint -sha256` را قرار دهید؛ دو نقطه‌ها قابل قبول‌اند. با Root اشتباه، فایل دارای چند گواهی یا هویت اشتباه ابزار اجرا نخواهد شد. از دانلود و اجرای خودکار PowerShell با `Invoke-Expression` یا غیرفعال‌کردن سیاست اجرای اسکریپت‌ها پرهیز کنید. برای توزیع انبوه، بهتر است این ابزار توسط سازمان امضای کد و از طریق کانال مدیریت معتبر تحویل داده شود.

این اسکریپت:
- تنها در حالت administrator و برای Firefox نصب‌شده معمولی اجرا می‌شود؛
- فقط Root با CN مشخص `Pardis AI Innovation Root CA` و fingerprint تطبیق‌داده‌شده را می‌پذیرد؛
- گواهی عمومی را در `C:\ProgramData\Pardis\Certificates\pardis-root.cer` کپی می‌کند؛
- فایل `distribution\policies.json` را با حفظ سایر تنظیمات و نگهداری نسخه backup تنظیم می‌کند؛
- **به Windows Trusted Root Certificates چیزی اضافه نمی‌کند**؛
- اجرای آن باعث نصب خودکار و بی‌اجازه در دستگاه‌های شخصی دیگر نمی‌شود.

اگر Firefox در مسیر غیرعادی نصب شده، از پارامتر `-FirefoxInstallDir` استفاده کنید. اگر قبلاً GPO یا Intune سیاستی اعمال می‌کند، باید سیاست را در سامانه مدیریت سازمانی تغییر دهید و صرفاً به `policies.json` محلی اتکا نکنید. اجرای script روی Windows و Firefox نصب‌شده باید ابتدا روی یک دستگاه آزمایشی تأیید شود.

## گام ۴: عیب‌یابی

۱. Firefox را کامل ببندید و دوباره اجرا کنید.
۲. در Firefox آدرس `about:policies#active` را باز کنید و از اجرای `Certificates` مطمئن شوید.
۳. صفحه `https://ca1.iravand.ir/healthz` باید بدون خطای `SEC_ERROR_UNKNOWN_ISSUER` باز شود.
۴. اگر سیاست اعمال نشده، مطمئن شوید Firefox همان نصب/پروفایل مدنظر را اجرا می‌کند و دستگاه تحت GPO متناقض نیست.
۵. مرورگر Chrome/Edge مستقل از این سیاست‌اند و لزوماً از نصب Firefox تأثیر نمی‌گیرند.

## هشدار امنیتی

**اعتماد به Root CA، تنها برای یک دامنه محدود نمی‌شود.** هر Root مورد اعتماد توان اعتبارسنجی گواهی‌های دامنه‌های دیگر را نیز دارد؛ از این رو کلید خصوصی Root پردیس باید آفلاین بماند، دسترسی Issuing CA محدود شود و سیاست نصب فقط روی دستگاه‌های مجاز با هویت قابل بررسی اعمال گردد.

هیچ وب‌سایتی نمی‌تواند بدون تأیید مدیر یا مالک دستگاه، Root جدید را در مرورگر ناشناس نصب کند. برای مخاطبان عمومی بدون کنترل دستگاه، با CA خصوصی همچنان خطای اعتبارسنجی اولیه طبیعی است.
