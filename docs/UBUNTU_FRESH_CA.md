# نصب صفر تا صد CA-Panel روی Ubuntu با CA کاملاً جدید

این روش برای سرور Ubuntu **کاملاً خالی**، بدون کلید یا گواهی CA قبلی، بدون Docker و بدون فایل .env نوشته شده است. خروجی: پنل روی https://ca1.iravand.ir با گواهی اختصاصی صادرشده از Root/Issuing CA جدید «پردیس هوش مصنوعی و نوآوری دیجیتال ایران».

**هشدار امنیتی:** امن‌ترین الگو ساخت Root CA روی رایانه مدیریت آفلاین و انتقال فقط فایل‌های Issuing CA به سرور است. اگر طبق درخواست، CA را روی Ubuntu تولید می‌کنید، در همین فرآیند کلید Root روی سرور ایجاد می‌شود و ممکن است در snapshot/backup ارائه‌دهنده زیرساخت باقی بماند. برای محیط عملیاتی حساس، Root را از ابتدا روی رایانه آفلاین بسازید. دستورهای زیر راه‌اندازی روی سرور را با الزام به **خارج‌کردن کلید Root پیش از اجرای عمومی پنل** انجام می‌دهند.

## ۰. پیش‌نیازها
- یک سرور تازه Ubuntu Server 24.04 LTS یا نسخه پشتیبانی‌شده Docker؛ کاربر مدیریتی عادی دارای sudo و دسترسی SSH، نه اجرای همه دستورات با root.
- دسترسی Git به مخزن CA-Panel (اگر خصوصی است، SSH key یا credential مخصوص مخزن).
- کنترل DNS برای iravand.ir و امکان افزودن A/AAAA و TXT برای ca1.iravand.ir.
- دستگاه/حافظه جداگانه و رمزگذاری‌شده برای نگهداری امن **کلید Root**؛ Root private key نباید روی سرور CA-Panel باقی بماند.
- نام‌های گواهی در نمونه انگلیسی و ساده هستند تا با ابزارهای X.509 سازگارتر باشند؛ عنوان فارسی صفحه مستقل است.

## ۱. نصب پیش‌نیازها و Docker

روی Ubuntu در SSH:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git openssl python3 python3-venv

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

در سرور کاملاً جدید، امکان اجرای Docker به‌عنوان کاربر عادی را تنظیم کنید. هشدار: گروه docker تقریباً معادل دسترسی root است:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker compose version
docker info
```

مرجع: https://docs.docker.com/engine/install/ubuntu/

## ۲. دریافت مخزن و ساخت .env تازه

```bash
cd "$HOME"
git clone https://github.com/dr-reza-khaleghifar/CA-Panel.git
cd CA-Panel
cp .env.example .env
chmod 600 .env
sed -i "s/^APP_UID=.*/APP_UID=$(id -u)/; s/^APP_GID=.*/APP_GID=$(id -g)/" .env
nano .env
```

اگر مخزن خصوصی است، برای clone از روش احراز هویت GitHub یا SSH key استفاده کنید. در `.env` مقدارهای زیر را **پیش از ایجاد CA** تنظیم کنید و بقیه متغیرهای موجود فایل را حفظ کنید. هر متغیر را دقیقاً یک بار تعریف کنید:

```dotenv
APP_UID=1000
APP_GID=1000
CA_DISPLAY_NAME='پردیس هوش مصنوعی و نوآوری دیجیتال ایران'
CA_ORGANIZATION='Pardis AI and Digital Innovation'

# هویت واقعی گواهی‌های Root و Issuing هنگام نخستین ساخت
CA_ROOT_CN=Pardis AI Innovation Root CA
CA_ISSUER_CN=Pardis AI Innovation Issuing CA
CA_ROOT_ORGANIZATION=Pardis AI and Digital Innovation
CA_ISSUER_ORGANIZATION=Pardis AI and Digital Innovation

# طول عمر و قدرت کلیدهای امضاکننده CA
CA_ROOT_VALIDITY_DAYS=3650
CA_ISSUER_VALIDITY_DAYS=365
CA_ROOT_KEY_BITS=3072
CA_ISSUER_KEY_BITS=3072

# نام جدید فایل‌های CA
CA_ROOT_KEY_FILE=pardis-root-key.pem
CA_ROOT_CERT_FILE=pardis-root-cert.pem
CA_ISSUER_KEY_FILE=pardis-issuer-key.pem
CA_ISSUER_CERT_FILE=pardis-issuer-cert.pem
CA_ONLINE_HOST_DIR=./secrets/online
CA_DIR=/run/ca

# آدرس پنل و فایل‌های HTTPS
PANEL_DOMAIN=ca1.iravand.ir
PANEL_TLS_BIND_IP=0.0.0.0
PANEL_HTTP_BIND_IP=0.0.0.0

# گواهی‌های سرور صادرشده: مستقل از Root/Issuer
CERT_VALIDITY_DAYS=30
SERVER_KEY_BITS=2048
```

UID و GID فقط نمونه‌اند؛ خروجی دستور `id -u` و `id -g` باید در فایل حفظ شود. **CA_KEY_PASSWORD را فعلاً همان مقدار placeholder نمونه بگذارید**؛ نصاب پس از پرسیدن رمز Issuing آن را امن تنظیم خواهد کرد. از قرار دادن کلید خصوصی در فایل env پرهیز کنید.

## ۳. نصب Python cryptography برای تولید CA تازه

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

این مرحله فقط برای نصاب CA است؛ خود API داخل Docker اجرا می‌شود.

## ۴. تولید دو CA جدید و اختصاصی

```bash
bash install.sh --init-ca
```

نصاب نیاز به تأیید صریح دارد: عبارت `CREATE NEW CA` را وارد کنید. سپس دو رمز **متفاوت و قوی** برای Root و Issuing CA انتخاب کنید؛ هنگام تایپ نشان داده نمی‌شوند. Root Password را در محل امن آفلاین نگهداری کنید. Issuing Password پس از ساخت به‌صورت مخفی در `.env` ذخیره می‌شود.

فایل‌های تولیدشده:

```text
secrets/
├── offline/
│   ├── pardis-root-key.pem       ← کلید خصوصی رمزگذاری‌شده Root (نباید روی سرور بماند)
│   └── pardis-root-cert.pem      ← گواهی عمومی Root
└── online/
    ├── pardis-issuer-key.pem     ← کلید خصوصی رمزگذاری‌شده Issuing
    ├── pardis-issuer-cert.pem    ← گواهی عمومی Issuing
    └── pardis-root-cert.pem      ← گواهی عمومی Root برای تأیید زنجیره
```

نام فایل‌های فوق از `.env` خوانده می‌شوند. فایل‌ها را در Git یا فضای عمومی آپلود نکنید.

## ۵. انتقال کلید Root از سرور به محل آفلاین

**پیش از اجرای پنل در محیط عملیاتی**، پوشه `secrets/offline` را از سرور به رسانه رمزگذاری‌شده و مجزای مدیریت کلید منتقل و از آن نسخه پشتیبان امن تهیه کنید. نمونه انتقال با SCP (دستور زیر روی رایانه مدیریتی، نه داخل Ubuntu):

```bash
# USER و SERVER_IP را جایگزین کنید. مقصد باید فضای امن و رمزگذاری‌شده باشد.
scp -r USER@SERVER_IP:~/CA-Panel/secrets/offline /PATH/TO/ENCRYPTED/OFFLINE_STORAGE/
```

در دستگاه مدیریت، نام فایل‌ها، وجود هر دو فایل و اثر انگشت Root را بررسی و با اثر انگشت نمایش‌داده‌شده هنگام ساخت مقایسه کنید:

```bash
openssl x509 -in /PATH/TO/ENCRYPTED/OFFLINE_STORAGE/offline/pardis-root-cert.pem -noout -fingerprint -sha256
```

**فقط پس از تأیید انتقال و تهیه نسخه پشتیبان آفلاین**، در Ubuntu و داخل پروژه پوشه offline را از سرور بردارید. `rm` حذف امن قطعی داده‌های ذخیره‌شده در snapshot/SSD مجازی را تضمین نمی‌کند؛ برای PKI حساس توصیه اکید ساخت Root از ابتدا روی دستگاه آفلاین است.

```bash
cd ~/CA-Panel
ls -la secrets/offline
# فقط بعد از اطمینان از وجود نسخه آفلاین معتبر و امن:
rm -i secrets/offline/pardis-root-key.pem secrets/offline/pardis-root-cert.pem
rmdir secrets/offline
```

نصاب اگر پوشه offline هنوز حاوی داده باشد، از اجرای عمومی خودداری می‌کند.

## ۶. بالا آوردن API روی localhost

```bash
cd ~/CA-Panel
bash install.sh --check
bash install.sh
docker compose ps
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/api/system
```

سلامت API باید `{"status":"ok"}` باشد و `/api/system` نام‌های واقعی Root/Issuing جدید و fingerprint عمومی Root را نمایش دهد. اگر پنل هنوز گواهی HTTPS ندارد، پورت 8080 عمداً فقط روی localhost است.

## ۷. فعال‌سازی HTTPS عمومی پرتال

برای **خود پرتال ca1.iravand.ir** نیازی به صدور leaf از Issuing CA خصوصی یا ثبت رکورد TXT نیست. Caddy از ACME عمومی برای دریافت و تمدید خودکار گواهی HTTPS سایت استفاده می‌کند. رکورد DNS دامنه باید به IP عمومی سرور اشاره کند و TCP پورت‌های ۸۰ و ۴۴۳ از اینترنت قابل دسترسی باشند.

پس از انتقال Root private key به محل آفلاین و تکمیل `.env`:

```bash
cd ~/CA-Panel
git pull --ff-only
python3 scripts/setup_admin.py
bash install.sh --public-https
curl --noproxy '*' https://ca1.iravand.ir/healthz
```

گزینه قدیمی `--private-https` برای سازگاری همچنان پذیرفته می‌شود، اما همان ACME عمومی را فعال می‌کند. پروفایل Compose با نام تاریخی `private-tls` حفظ شده است. بررسی سلامت HTTPS از trust store عمومی سیستم انجام می‌شود؛ از `--cacert` برای Root خصوصی استفاده نکنید.

## ۸. پرتال عمومی و روند صدور گواهی کاربران

کاربر عمومی از `https://ca1.iravand.ir/` وارد می‌شود و بدون حساب مدیر دامنه را ثبت می‌کند. سامانه یک رکورد TXT تصادفی برای اثبات مالکیت دامنه می‌دهد. پس از انتشار و تأیید TXT، درخواست در صف مدیر قرار می‌گیرد. مدیر از `https://ca1.iravand.ir/login` وارد شده و درخواست را در `/admin/requests` تأیید یا رد می‌کند. فقط پس از تصویب مدیر، صاحب پیوند پیگیری می‌تواند گواهی و بسته کلید خصوصی یک‌بارمصرف را دریافت کند.

**تفاوت دو نوع گواهی را در نظر داشته باشید:**
- TLS خود سایت CA-Panel: از ACME عمومی است و مرورگرها باید آن را به‌طور پیش‌فرض معتبر بدانند.
- گواهی دامنه کاربران: توسط Private CA ساخته‌شده در این راهنما امضا می‌شود؛ برای اعتماد به آن باید Root CA را با تطبیق SHA-256 مستقل و طبق سیاست دستگاه نصب کرد.

برای راهنمای نصب Root روی Windows، macOS، iOS/iPadOS، Android، Linux و مرورگرها، صفحه راهنمای Root CA را از `http://ca1.iravand.ir/` باز کنید. این صفحه فقط راهنما و دو فایل عمومی Root را ارائه می‌کند؛ ثبت درخواست، ورود مدیر و صدور فقط روی HTTPS انجام می‌شود.
