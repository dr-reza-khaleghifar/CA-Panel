# CA-Panel — Lightweight, Docker-based private Certificate Authority

پنل سبک صدور گواهی TLS با CA اختصاصی، رابط فارسی و استقرار Docker. کاربر دامنه را وارد می‌کند، مالکیت DNS را با TXT ثابت می‌کند، CSR می‌دهد و یک **گواهی ۳۰روزه** دریافت می‌کند. کلید خصوصی وب‌سایت **هرگز** به سرور فرستاده نمی‌شود.

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

## روش دریافت گواهی

1. در رابط پنل، `example.org` را وارد کنید.
2. یک رکورد TXT با نام `_ca-panel.example.org` و مقدار تصادفی اعلام‌شده توسط پنل ایجاد کنید. اگر DNS Provider نام را نسبی می‌گیرد، host را فقط `_ca-panel` بگذارید.
3. روی «بررسی DNS» بزنید (ممکن است propagation زمان ببرد).
4. در **دستگاه خود** کلید/CSR بسازید؛ دامنه را جایگزین کنید:

```bash
openssl req -new -newkey rsa:2048 -nodes \
  -keyout site.key -out site.csr \
  -subj "/CN=example.org" -addext "subjectAltName=DNS:example.org"
```

5. محتویات `site.csr` را در پنل Paste کنید، **نه** `site.key` را. خروجی `example.org-fullchain.pem` را دانلود کنید. فایل خروجی شامل گواهی سرور، intermediate و root است؛ در اکثر وب‌سرورها برای fullchain کافی است leaf + intermediate نگه دارید و root را جداگانه در trust store کلاینت پیکربندی کنید.
6. فایل `site.key` و گواهی را در وب‌سرور قرار دهید. **گواهی خودکار تمدید نمی‌شود** و ۳۰ روز اعتبار دارد؛ پیش از انقضا دوباره درخواست بدهید.

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
