# نصب از صفر روی Ubuntu با CA فعلی و HTTPS اختصاصی روی ۴۴۳

هدف: `https://ca1.iravand.ir` با Caddy، گواهی صادرشده از CA خودتان و پشتیبانی مرورگر Firefox سفارشی شما. **اگر مرورگر قبلاً به Root CA فعلی اعتماد دارد، CA تازه نسازید.** فقط فایل‌های Issuing CA موجود و گواهی عمومی Root را به سرور جدید منتقل کنید. Root **private** key باید کاملاً خارج از سرور و آفلاین باقی بماند.

این راهنما برای Ubuntu 22.04/24.04/26.04 (64-bit) و Docker Compose v2 است. دستورها را با حساب کاربری عادی دارای دسترسی `sudo` اجرا کنید؛ خود نصاب را با `sudo` یا به‌عنوان `root` اجرا نکنید. در نمونه‌های SSH، `YOUR_USER` و `SERVER_IP` را با اطلاعات خودتان جایگزین کنید.

## ۱. پیش‌نیازهای Ubuntu و Docker

روی Ubuntu اجرا کنید:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git python3 python3-venv openssl

# Docker Engine from the official Docker apt repository:
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

اگر Docker یا containerd از منبع دیگری نصب شده است، **قبل از نصب مجدد** طبق راهنمای رسمی Docker بسته‌های متعارض را بررسی کنید؛ سرویس موجود را بدون برنامه‌ریزی حذف نکنید.

برای دادن مجوز Docker به یک مدیر مورد اعتماد (عضویت در گروه `docker` دسترسی تقریباً معادل root می‌دهد):

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker info >/dev/null
docker compose version
```

[راهنمای رسمی نصب Docker روی Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

## ۲. کلون‌کردن CA-Panel

```bash
cd "$HOME"
git clone https://github.com/dr-reza-khaleghifar/CA-Panel.git
cd CA-Panel
```

برای مخزن خصوصی باید SSH key یا توکن دارای مجوز دسترسی به مخزن روی این ماشین تنظیم شده باشد.

## ۳. انتقال امن CA فعلی از Mac/سرور قدیمی

در **ماشین قدیمی** و داخل پوشه پروژه فعلی:

```bash
ssh YOUR_USER@SERVER_IP 'mkdir -p ~/CA-Panel/secrets/online'
scp secrets/online/issuer-key.pem \
    secrets/online/issuer-cert.pem \
    secrets/online/root-cert.pem \
    YOUR_USER@SERVER_IP:~/CA-Panel/secrets/online/
scp .env YOUR_USER@SERVER_IP:~/CA-Panel/.env
```

این `scp`ها فقط نمونه‌اند؛ نام فایل‌ها را مطابق `.env` فعلی تنظیم کنید. **کلید خصوصی Root یعنی `secrets/offline/root-key.pem` را منتقل نکنید.** `.env` محرمانه است و فقط باید با کانال امن منتقل شود.

روی Ubuntu:

```bash
cd ~/CA-Panel
chmod 700 secrets secrets/online
chmod 600 secrets/online/* .env
```

با `nano .env` تنظیمات را بدون حذف `CA_KEY_PASSWORD` موجود اصلاح کنید:

```dotenv
APP_UID=1000
APP_GID=1000
CA_ONLINE_HOST_DIR=./secrets/online
CA_DIR=/run/ca
PANEL_DOMAIN=ca1.iravand.ir
PANEL_TLS_HOST_DIR=./secrets/tls
PANEL_TLS_BIND_IP=0.0.0.0
```

`APP_UID` و `APP_GID` را با مقادیر واقعی `id -u` و `id -g` کاربر Ubuntu تطبیق دهید. اگر سرور فقط باید در VPN یا شبکه داخلی در دسترس باشد، `PANEL_TLS_BIND_IP` را روی همان IP محلی Ubuntu بگذارید و محدودیت شبکه/فایروال را نیز اعمال کنید. Docker publish ممکن است برخی قوانین UFW را دور بزند؛ قواعد امنیتی cloud firewall و `DOCKER-USER` را هم بررسی کنید.

**اگر CA را هنوز نساخته‌اید:** روی یک کامپیوتر مدیریتی *امن و آفلاین* با دستور `bash install.sh --init-ca` آن را بسازید، کلید Root را همان‌جا آفلاین نگه دارید، فقط خروجی `secrets/online/` را به Ubuntu انتقال دهید و `CA_KEY_PASSWORD` همان Issuing CA را در env سرور وارد کنید. ساخت CA تازه اعتماد مرورگر به Root قبلی را جایگزین نمی‌کند.

## ۴. راه‌اندازی اولیه فقط روی localhost

```bash
cd ~/CA-Panel
bash install.sh --check
bash install.sh
docker compose ps
curl http://127.0.0.1:8080/healthz
```

پاسخ مورد انتظار `{"status":"ok"}` است. API فعلاً فقط به `127.0.0.1:8080` میزبان bind شده؛ برای دسترسی از Mac، روی Mac یک SSH tunnel باز کنید:

```bash
ssh -L 8080:127.0.0.1:8080 YOUR_USER@SERVER_IP
```

و در مرورگر Mac پنل را با `http://localhost:8080` باز کنید. `localhost` برای Web Crypto (ساخت CSR/کلید مرورگر) secure context محسوب می‌شود.

## ۵. صدور گواهی سرور برای ca1.iravand.ir (اختیاری؛ روش دستی)

**روش ساده‌تر جدید:** روی Ubuntu مستقیماً `bash install.sh --private-https` اجرا کنید؛ گواهی TLS برای دامنه `PANEL_DOMAIN` را از Issuing CA شما می‌سازد و نیاز به TXT یا دانلود ZIP نیست. مراحل زیر فقط برای صدور دستی جایگزین هستند.

داخل پنل دامنه `ca1.iravand.ir` را ثبت کنید، رکورد DNS TXT اعلام‌شده با نام `_ca-panel.ca1.iravand.ir` را در DNS قرار دهید و بعد از تأیید مالکیت، گواهی سرور را صادر کنید. ZIP حاوی کلید خصوصی سرور یک‌بارمصرف است؛ آن را به‌صورت امن دانلود کنید.

روی Mac، فایل ZIP دانلودشده را با `scp` به پوشه خانگی Ubuntu (نه Git) منتقل کنید:

```bash
scp "$HOME/Downloads/ca1.iravand.ir-certificates.zip" \
    YOUR_USER@SERVER_IP:~/ca1.iravand.ir-certificates.zip
```

روی Ubuntu:

```bash
cd ~/CA-Panel
python3 scripts/setup_private_tls.py --zip "$HOME/ca1.iravand.ir-certificates.zip"
```

اسکریپت نام دامنه در SAN، زنجیره تا Root CA، انقضا و انطباق کلید خصوصی و گواهی را با OpenSSL بررسی می‌کند و فقط `secrets/tls/fullchain.pem` و `secrets/tls/privkey.pem` را با مجوز محدود نصب می‌کند. **از کلید Issuing CA به‌جای کلید HTTPS استفاده نکنید.**

## ۶. فعال‌کردن HTTPS روی پورت ۴۴۳

```bash
# فقط اگر سرویس ACME Caddy قبلی روی همین سرور فعال است:
docker compose --profile public stop caddy

bash install.sh --private-https
docker compose --profile private-tls ps
```

اگر `PANEL_TLS_BIND_IP=0.0.0.0` باشد Caddy روی TCP/UDP 443 گوش می‌دهد. اگر bind به IP داخلی مشخص کرده‌اید، تست محلی پیش‌فرض نصاب روی 127.0.0.1 در دسترس نخواهد بود؛ در این حالت به جای نصاب، `docker compose --profile private-tls up -d --build api caddy-private` را اجرا کنید و سلامت را با IP مناسب و DNS/SNI بررسی کنید.

تست روی Ubuntu با گواهی عمومی Root خودتان:

```bash
curl --noproxy '*' \
  --cacert secrets/online/root-cert.pem \
  --resolve ca1.iravand.ir:443:127.0.0.1 \
  https://ca1.iravand.ir/healthz
```

پاسخ مورد انتظار `{"status":"ok"}` است. اگر `PANEL_TLS_BIND_IP` را به IP دیگری تغییر داده‌اید، در `--resolve` همان IP را جایگزین کنید. اگر Root PEM نام سفارشی دارد مسیر `--cacert` را متناسب تغییر دهید.

## ۷. DNS، شبکه و اعتماد مرورگر

- رکورد `A`/درصورت استفاده `AAAA` برای `ca1.iravand.ir` باید به IP قابل دسترس **برای کلاینت‌ها** برسد؛ اگر در شبکه خصوصی هستید از DNS داخلی یا VPN استفاده کنید.
- فایروال میزبان و cloud security group باید اتصال TCP 443 (و در صورت نیاز QUIC روی UDP 443) را فقط برای شبکه‌های مجاز باز کنند. SSH خود را قبل از تغییر قواعد فایروال مسدود نکنید.
- مرورگر سفارشی Firefox شما به‌شرط داشتن **Root CA فعلی** در trust store، اعتبار گواهی سایت را تأیید می‌کند. سایر مرورگرها ممکن است خطای اعتماد نشان دهند.
- گواهی برگ نهایی پیش‌فرض ۳۰ روز اعتبار دارد و **خودکار تمدید نمی‌شود**. پیش از انقضا گواهی جدید بگیرید و با `setup_private_tls.py --replace` نصب کنید و `caddy-private` را ریستارت کنید.
- این سامانه هنوز **احراز هویت داخلی ندارد** و HTTPS به‌تنهایی مانع صدور گواهی توسط اشخاصی که مالکیت DNS را اثبات می‌کنند نیست؛ برای انتشار اینترنتی، احراز هویت/محدودیت دسترسی، ممیزی و نظارت اضافه کنید.
- در لاگ‌های عمومی یا چت، رمز Issuing CA، فایل `.env` کامل، کلیدهای PEM یا ZIP حاوی کلید را منتشر نکنید.

## عیب‌یابی

```bash
docker compose --profile private-tls ps
docker compose --profile private-tls logs --tail=80 api caddy-private
sudo ss -lntp | grep ':443'
```

خطای `Address already in use` یعنی پورت ۴۴۳ توسط سرویس دیگری مانند Nginx/Apache/Caddy اشغال شده است. خطای SSL در HTTPS ممکن است از نام دامنه نادرست، زنجیره نادرست یا نصب‌نشدن Root CA در مرورگر باشد. هرگز `curl -k` را به‌عنوان راهکار اعتماد به CA استفاده نکنید.
