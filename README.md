# CA-Panel — Lightweight, Docker-based private Certificate Authority

پنل سبک صدور گواهی TLS با CA اختصاصی، رابط فارسی و استقرار Docker. کاربر دامنه را وارد می‌کند، مالکیت DNS را با TXT ثابت می‌کند و مرورگر پس از تأیید DNS **کلید خصوصی و CSR را خودکار روی دستگاه کاربر تولید می‌کند**. سرور فقط CSR را امضا می‌کند و یک **گواهی ۳۰روزه** تحویل می‌دهد؛ فایل‌های گواهی و کلید در یک ZIP دانلود می‌شوند. کلید خصوصی وب‌سایت **هرگز** به سرور فرستاده نمی‌شود.

> **مهم:** این پروژه یک **Private CA** است. گواهی‌های صادرشده به‌صورت پیش‌فرض نزد Chrome/Firefox/Safari/سیستم‌عامل‌های عمومی trusted نیستند. نصب ریشه CA در کلاینت‌ها اقدامی حساس و مدیریتی است. اگر به SSL معتبر عمومی برای بازدیدکنندگان اینترنت نیاز دارید، از یک CA مورد اعتماد عمومی مثل Let's Encrypt استفاده کنید. گواهی HTTPS خود **پنل** در حالت public توسط Caddy/ACME تأمین می‌شود و ربطی به گواهی‌های صادرشده از CA خصوصی ندارد.

## امکانات MVP

- رابط فارسی RTL، بدون پایگاه‌داده سنگین و بدون نیاز به اکانت کاربری
- ثبت دامنه/URL و اثبات مالکیت با DNS TXT؛ چالش تصادفی و انقضای یک‌ساعته
- بررسی مجدد DNS درست لحظه امضا؛ محدودسازی نرخ ثبت و تلاش برای تأیید
- امضای CSR (RSA >= 2048 یا P-256/P-384) و محدود کردن **CN/SAN** به یک دامنه
- Root CA آفلاین و کلید CA صادرکننده آنلاین، هر دو با رمز عبور رمزنگاری‌شده
- دانلود گواهی، زنجیره و ریشه عمومی؛ ثبت سریال/وضعیت درخواست با SQLite
- Docker Compose، محدودیت CPU/RAM، فایل‌سیستم read-only و اجرای غیر-root
- پیکربندی اختیاری Caddy برای HTTPS عمومی پنل

## نیازمندی‌ها

- سرور لینوکس با Docker Engine و Docker Compose v2؛ حدود **۴۰۰ مگابایت RAM** برای API و Caddy، به‌اضافه سربار سیستم‌عامل. اجرای API به‌تنهایی حداکثر 256MiB RAM و 0.75 CPU در Compose محدود شده است؛ این‌ها سقف منابع‌اند، نه اندازه‌گیری مصرف.
- Python 3.12+ روی سیستم مدیریت کلید برای اجرای اسکریپت اولیه، با بسته `cryptography`. بهتر است ساخت CA روی دستگاه امن و جداگانه انجام شود.
- دامنه پنل (فقط برای استفاده public) با DNS صحیح و پورت‌های ورودی 80/443 باز.

## راه‌اندازی — کلید ریشه را آفلاین نگه دارید

**۱. ساخت Root/Issuing CA روی یک سیستم مدیریتی امن، ترجیحاً نه سرور برنامه:**

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/init_ca.py --output secrets
```

دو گذرواژه قوی و متفاوت (حداقل ۱۲ کاراکتر) تعیین کنید. اسکریپت خروجی زیر را ایجاد می‌کند و fingerprint گواهی ریشه را چاپ می‌کند:

```
secrets/
├── offline/
│   ├── root-key.pem      # SECRET - NEVER UPLOAD TO SERVER
│   └── root-cert.pem
└── online/
    ├── issuer-key.pem    # SECRET - encrypted
    ├── issuer-cert.pem
    └── root-cert.pem     # public trust anchor
```

پوشه `secrets/offline` را **فوراً از سرور اجرا جدا** کرده و در محل ایمن آفلاین با نسخه پشتیبان رمزنگاری‌شده نگه دارید. فقط `secrets/online` را به سرور منتقل کنید. ریشه عمومی را پیش از نصب در کلاینت‌ها با fingerprint چاپ‌شده از مسیر مستقل مقایسه کنید. حتی در محیط تست نیز **هیچ کلید خصوصی را در GitHub یا image Docker قرار ندهید**.

**۲. راه‌اندازی روی سرور:**

```bash
git clone https://github.com/dr-reza-khaleghifar/CA-Panel.git CA-Panel
cd CA-Panel
mkdir -p data secrets/online
# Copy ONLY the three secrets/online files from the administrative machine.
cp .env.example .env
id -u; id -g
# Edit APP_UID and APP_GID to match the owner of data/ and secrets/online/.
# Set CA_KEY_PASSWORD to the Issuing CA passphrase (NOT the root passphrase).
chmod 600 .env
# Ensure the container UID can read issuer-key.pem and write ./data.
docker compose up --build -d
curl http://127.0.0.1:8080/healthz
```

به‌صورت پیش‌فرض پنل فقط روی `127.0.0.1:8080` قابل دسترس است و مستقیماً از اینترنت منتشر نمی‌شود. از طریق SSH tunnel نیز می‌توان آن را مشاهده کرد.

**۳. HTTPS عمومی خود پنل (اختیاری):**

رکورد A/AAAA برای `PANEL_DOMAIN` را روی IP سرور تنظیم کنید. سپس `.env` را به‌روزرسانی کنید و با این دستور بالا بیاورید:

```bash
docker compose --profile public up --build -d
```

Caddy گواهی معتبر عمومی برای دامنه **پنل** می‌گیرد. وقتی تمام ترافیک اینترنت صرفاً از Caddy عبور کند، `TRUST_PROXY_HEADERS=1` را برای Rate Limit مبتنی بر IP واقعی قرار دهید و کانتینر API را به‌صورت عمومی در شبکه یا روی پورت خارجی منتشر نکنید. استفاده از API روی localhost جداگانه ممکن است هدر جعلی بپذیرد؛ پورت localhost باید فقط برای مدیر قابل دسترسی باشد. قبل از ارائه عمومی، کنترل‌های بیشتر مثل احراز هویت، سهمیه و مانیتورینگ توصیه می‌شوند.

## دریافت خودکار گواهی (بدون OpenSSL و CSR دستی)

1. پنل را با **HTTPS** باز کنید (یا برای تست از `http://localhost:8080` / `http://127.0.0.1:8080` استفاده کنید). Web Crypto در HTTP با IP شبکه محلی یا دامنه بدون TLS فعال نیست.
2. دامنه را وارد کنید؛ برای مثال `example.org`.
3. رکورد TXT اعلام‌شده را در DNS منتشر کنید، مثلاً `_ca-panel.example.org` با مقدار `ca-panel-verification=...`.
4. روی «تأیید DNS، صدور خودکار و دانلود ZIP» کلیک کنید. مرورگر RSA-2048 و CSR دارای SAN را می‌سازد؛ **کلید خصوصی هرگز به سرور ارسال نمی‌شود**. API بعد از بررسی دوباره TXT گواهی را امضا می‌کند.
5. دانلود ZIP خودکار آغاز می‌شود؛ اگر مرورگر دانلود خودکار را مسدود کرد، روی دکمه «دانلود همه فایل‌های گواهی (ZIP)» کلیک کنید. فایل ZIP شامل موارد زیر است:
    - `example.org.key`: کلید خصوصی بدون رمزگذاری؛ **بسیار محرمانه**
    - `example.org.crt`: گواهی سرور
    - `example.org-fullchain.pem`: گواهی سرور + CA واسط (برای nginx/Apache)
    - `issuing-ca.pem`: گواهی واسط
    - `root-ca.pem`: گواهی عمومی ریشه (CA خصوصی)
    - `README.txt`: توضیح نحوه نصب فایل‌ها

کلید خصوصی فقط تا زمانی که صفحه باز است در حافظه مرورگر باقی می‌ماند؛ پس از بستن/رفرش‌کردن صفحه، دانلود مجدد **کلید** ممکن نیست. ZIP را در محل امن نگه دارید و بعد از استخراج دسترسی فایل `.key` را محدود کنید (`chmod 600 example.org.key`). مرورگر ممکن است ZIP را خودکار دانلود نکند؛ از دکمه دانلود روی صفحه استفاده کنید. این ZIP **رمزگذاری‌شده نیست** و باید محرمانه نگه‌داری شود. گواهی ۳۰ روزه است و تمدید خودکار در پس‌زمینه هنوز وجود ندارد.

برای برنامه‌نویسان، مسیر `POST /api/requests/{id}/issue` هنوز CSR خارجی را نیز قبول می‌کند. تغییر جدید مسیر صدور در **رابط کاربری** را خودکار می‌کند؛ احراز مالکیت DNS همچنان اجباری است.

## مستندات

- [معماری و مدل اعتماد](docs/ARCHITECTURE.md)
- [راهنمای API](docs/API.md)
- [امنیت، محدودیت‌ها، پشتیبان‌گیری و عملیات](docs/OPERATIONS.md)

## توسعه و تست

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
```

> وضعیت: **MVP**؛ این پروژه **CA عمومی مورد اعتماد مرورگر**، سامانه ACME، CRL/OCSP، سیستم احراز هویت یا سرویس HSM نیست. برای کاربردهای حساس/گسترده نیازمند hardening و بازبینی امنیتی است.


## خطای راه‌اندازی `Incorrect password, could not decrypt key`

مقدار `CA_KEY_PASSWORD` باید **رمز Issuing CA** باشد، نه رمز Root CA. در صورت وجود کاراکتر `$` در رمز، مقدار را در `.env` داخل تک‌نقل‌قول قرار دهید تا Compose آن را تغییر ندهد. سپس `docker compose up -d --force-recreate api` را اجرا کنید. برای بررسی امن و بدون نمایش رمز، [بخش Troubleshooting در راهنمای عملیات](docs/OPERATIONS.md#startup-fails-incorrect-password-could-not-decrypt-key) را بخوانید. **کلید یا رمز را برای کسی ارسال نکنید.**


## مشکل DNS داخل Docker

اگر رکورد TXT از DNS عمومی قابل مشاهده است ولی `app.dns_debug` در Docker نتیجه `NXDOMAIN` می‌دهد، از گزینه اختیاری `DNS_RESOLVERS=1.1.1.1,1.0.0.1` در فایل `.env` استفاده کنید و کانتینر API را بازسازی کنید. تنظیم پیش‌فرض همچنان از DNS داخلی کانتینر استفاده می‌کند. [دستور تشخیص و راهنمای کامل](docs/OPERATIONS.md#docker-resolver-returns-nxdomain-but-a-public-resolver-finds-the-exact-txt).
