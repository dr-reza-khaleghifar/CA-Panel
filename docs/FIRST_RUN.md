# راه‌اندازی اولیه CA-Panel

برای راه‌اندازی CA-Panel روی macOS یا Linux، از **`install.sh`** استفاده کنید. این ورودی به `install.py` متصل است و فقط Python 3 و Docker Compose v2 نیاز دارد. نصب سیستم را با دسترسی root اجرا نکنید.

## ۱. اگر قبلاً CA ساخته‌اید (حالت پیش‌فرض)

فایل‌های `issuer-key.pem`، `issuer-cert.pem` و `root-cert.pem` باید در `secrets/online/` موجود باشند (یا پوشه سفارشی تعریف‌شده در `.env`). کلید خصوصی Root را اینجا قرار ندهید.

```bash
git pull
bash install.sh
```

نصاب:

1. Docker و Compose و آماده‌بودن daemon را بررسی می‌کند.
2. هیچ فایل کلید یا گواهی موجودی را تغییر نمی‌دهد.
3. اگر `.env` وجود داشته باشد، آن را حفظ می‌کند و رمز موجود را دوباره نمی‌پرسد. اگر `.env` جدید باشد یا رمز Issuing CA هنوز تنظیم نشده باشد، رمز را بدون نمایش در ترمینال می‌گیرد و فایل را با سطح دسترسی `0600` ذخیره می‌کند.
4. مالک `APP_UID` و `APP_GID` را برای نصب تازه مطابق کاربر جاری تنظیم می‌کند، مسیرهای CA و Data را بررسی می‌کند و پوشه data را می‌سازد.
5. سرویس API را با `docker compose up -d --build --force-recreate api` اجرا می‌کند و `/healthz` را بررسی می‌کند.

نتیجه پیش‌فرض در `http://127.0.0.1:8080` در دسترس است؛ پنل از این طریق عمومی نمی‌شود.

## ۲. اگر هنوز Root/Issuing CA ندارید (نصب کاملاً تازه)

ساخت CA را **فقط روی یک کامپیوتر مدیریتی امن** انجام دهید:

```bash
# Python 3 + cryptography لازم است
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash install.sh --init-ca
```

این گزینه برای ساخت یک **CA کاملاً جدید** است. دو رمز متفاوت و قوی برای Root و Issuing CA پرسیده می‌شود و ایجاد CA فقط بعد از واردکردن متن `CREATE NEW CA` ادامه پیدا می‌کند.

خروجی در `secrets/offline` و `secrets/online` ساخته می‌شود. **نصاب عمداً در همین مرحله متوقف می‌شود.** پوشه `secrets/offline` شامل Root private key است و باید فوراً با روش امن به رسانه یا مکان آفلاین جداگانه منتقل و پشتیبان‌گیری شود. آن را روی سرور در معرض اینترنت نگه ندارید. فقط `secrets/online` روی سرور لازم است. در مرحله بعد، پس از تأیید انتقال امن و وجود فایل‌های online و `.env`:

```bash
bash install.sh
```

**هیچ‌وقت برای رفع خطای رمز عبور/خرابی CA قبلی از `--init-ca` استفاده نکنید.** این گزینه از بازنویسی کلیدهای موجود امتناع می‌کند.

## گزینه‌های دیگر

```bash
bash install.sh --check       # بررسی بدون تغییر فایل‌ها
bash install.sh --no-start    # آماده‌سازی .env و پوشه data بدون اجرای Docker
bash install.sh --help
```

### عیب‌یابی و نکات امنیتی

- مشکل `CA_KEY_PASSWORD` معمولاً به تفاوت رمز **Issuing CA** با Root CA مربوط است. رمز، کلید خصوصی یا فایل کامل `.env` را در پیام‌ها و لاگ‌های عمومی قرار ندهید.
- برای تغییر تنظیمات بعد از نصب، `.env` را ویرایش کرده و `docker compose up -d --build --force-recreate api` را اجرا کنید. تنظیمات مجاز در `docs/OPERATIONS.md` آمده‌اند.
- این نصاب **فونت را دانلود نمی‌کند** و مشکل گواهی HTTPS شبکه برای GitHub را با غیرفعال‌کردن TLS دور نمی‌زند.
- هنگام ساخت CA جدید، اگر نصب بسته‌های Python به‌دلیل SSL شبکه شکست خورد، گواهی‌های معتبر شبکه را تنظیم یا از محیط پکیج‌های قابل اعتماد/آفلاین استفاده کنید؛ `pip --trusted-host` و `curl -k` راه‌حل امنی نیستند.
- چون اجرای پروژه کلیدهای TLS کاربران را موقتاً در RAM سرور می‌سازد، انتشار عمومی فقط با HTTPS معتبر و کنترل دسترسی اضافی توصیه می‌شود.


## تنظیم مشخصات CA قبل از ساخت اولیه

در نصب کاملاً جدید، **پیش از اجرای** `bash install.sh --init-ca`، فایل `.env.example` را به `.env` کپی کنید و مشخصات دلخواه را داخل `.env` تنظیم کنید. اگر `.env` موجود است آن را بازنویسی نکنید.

```dotenv
# مشخصات واقعی Subject در گواهی‌های Root و Issuing
CA_ROOT_CN=Example Offline Root CA
CA_ISSUER_CN=Example Issuing CA
CA_ROOT_ORGANIZATION=Example Organization
CA_ISSUER_ORGANIZATION=Example Organization

# اعتبار و کلیدهای خود CA
CA_ROOT_VALIDITY_DAYS=3650
CA_ISSUER_VALIDITY_DAYS=365
CA_ROOT_KEY_BITS=3072
CA_ISSUER_KEY_BITS=3072

# نام فایل‌های PEM ایجادشده
CA_ROOT_KEY_FILE=root-key.pem
CA_ROOT_CERT_FILE=root-cert.pem
CA_ISSUER_KEY_FILE=issuer-key.pem
CA_ISSUER_CERT_FILE=issuer-cert.pem
```

در مرحله ساخت `install.sh --init-ca`، مشخصات بررسی و سپس برای ساخت **CA جدید** استفاده می‌شوند؛ این گزینه هیچ‌وقت یک CA موجود را دوباره صادر نمی‌کند. Root Key فقط در `secrets/offline` تولید می‌شود، در حالی که فایل‌های `issuer-key.pem`، `issuer-cert.pem` و گواهی عمومی Root در `secrets/online` قرار دارند (یا نام‌های تنظیم‌شده در env).

- نام‌های گواهی حداکثر ۶۴ بایت UTF-8 هستند. نام نمایشی رابط `CA_DISPLAY_NAME` جدا از `CA_ROOT_CN` و `CA_ISSUER_CN` است.
- اعتبار Root بین ۳۶۵ و ۷۳۰۰ روز، و Issuing CA بین ۳۰ و ۳۶۵۰ روز است؛ Issuing باید حداقل ۷ روز زودتر از Root منقضی شود.
- کلیدهای RSA خود Root/Issuing CA می‌توانند ۳۰۷۲ یا ۴۰۹۶ بیت باشند. `SERVER_KEY_BITS` صرفاً اندازه کلید گواهی‌های صادرشده برای دامنه‌ها را تنظیم می‌کند.
- `CA_ROOT_KEY_FILE` فقط مربوط به فایل رمزگذاری‌شده آفلاین است؛ به کانتینر منتقل نمی‌شود. سایر سه نام PEM با تنظیمات اجرای فعلی نیز یکسان‌اند.
- ویرایش این مشخصات در `.env` **پس از ساخت CA**، نام، اعتبار یا اندازه کلید گواهی‌های موجود را عوض نمی‌کند. برای تغییر هویت CA، فرایند رسمی تعویض/چرخش CA و توزیع اعتماد جدید لازم است.

برای اجرای اسکریپت سنتی ساخت CA نیز می‌توانید روی کامپیوتر امن از `python scripts/init_ca.py --env .env --output secrets` استفاده کنید.
