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
PANEL_TLS_BIND_IP=0.0.0.0
PANEL_HTTP_BIND_IP=0.0.0.0
```

`APP_UID` و `APP_GID` را با مقادیر واقعی `id -u` و `id -g` کاربر Ubuntu تطبیق دهید. اگر سرور فقط باید در VPN یا شبکه داخلی در دسترس باشد، `PANEL_TLS_BIND_IP` را روی همان IP محلی Ubuntu بگذارید و محدودیت شبکه/فایروال را نیز اعمال کنید. Docker publish ممکن است برخی قوانین UFW را دور بزند؛ قواعد امنیتی cloud firewall و `DOCKER-USER` را هم بررسی کنید.

**اگر CA را هنوز نساخته‌اید:** روی یک کامپیوتر مدیریتی *امن و آفلاین* با دستور `bash install.sh --init-ca` آن را بسازید، کلید Root را همان‌جا آفلاین نگه دارید، فقط خروجی `secrets/online/` را به Ubuntu انتقال دهید و `CA_KEY_PASSWORD` همان Issuing CA را در env سرور وارد کنید. ساخت CA تازه اعتماد مرورگر به Root قبلی را جایگزین نمی‌کند.

## ۴. راه‌اندازی API و بررسی سلامت محلی

```bash
cd ~/CA-Panel
bash install.sh --check
bash install.sh
docker compose ps
curl http://127.0.0.1:8080/healthz
```

پاسخ مورد انتظار `{"status":"ok"}` است. API فقط روی `127.0.0.1:8080` میزبان bind شده و نباید مستقیماً در اینترنت منتشر شود. برای پرتال عمومی از Caddy روی HTTPS استفاده می‌کنیم؛ رابط صدور را از پورت داخلی API باز نکنید.

## ۵. فعال‌کردن HTTPS عمومی و پرتال کاربران

برای `PANEL_DOMAIN` باید رکورد DNS عمومی به IP همین سرور اشاره کند و TCP پورت‌های ۸۰ و ۴۴۳ از اینترنت قابل دسترسی باشند. Caddy از ACME عمومی برای گواهی HTTPS خود سایت استفاده می‌کند؛ نیازی به صدور TLS leaf از CA خصوصی یا ساخت فایل در `secrets/tls/` نیست.

```bash
cd ~/CA-Panel
git pull --ff-only
python3 scripts/setup_admin.py   # فقط اگر مدیر هنوز راه‌اندازی نشده است
bash install.sh --public-https
```

گزینه قدیمی `--private-https` نیز برای سازگاری پذیرفته می‌شود، اما همان ACME عمومی را فعال می‌کند. پروفایل Compose با نام تاریخی `private-tls` حفظ شده است. Caddy روی TCP/UDP 443 پرتال HTTPS را ارائه می‌کند و روی TCP 80 فقط راهنمای Root CA، دو دانلود عمومی Root و مسیرهای لازم ACME را در دسترس می‌گذارد.

بررسی سلامت پرتال:

```bash
curl --noproxy '*' https://ca1.iravand.ir/healthz
curl --noproxy '*' -I https://ca1.iravand.ir/
curl --noproxy '*' -I https://ca1.iravand.ir/admin/requests
```

پاسخ‌های مورد انتظار به‌ترتیب 200، 200 و 303 به صفحه ورود مدیر هستند. برای ورود مدیر از `https://ca1.iravand.ir/login` استفاده کنید؛ کاربران عمومی مستقیماً از `https://ca1.iravand.ir/` درخواست گواهی ثبت می‌کنند.

**توجه:** گواهی‌های دامنه‌ای که CA-Panel صادر می‌کند همچنان از Private CA امضا می‌شوند و برای اعتماد به آن‌ها باید Root CA را با اثر انگشت مستقل روی دستگاه مقصد نصب کرد. این موضوع با TLS عمومی خود پرتال متفاوت است.

## ۶. DNS، شبکه و اعتماد گواهی‌ها

- رکورد `A` و در صورت استفاده `AAAA` برای `PANEL_DOMAIN` باید به IP عمومی همین سرور اشاره کند.
- فایروال میزبان و cloud security group باید TCP پورت‌های ۸۰ و ۴۴۳ را برای کاربران عمومی باز بگذارند؛ Caddy برای ACME و راهنمای HTTP به پورت ۸۰ نیاز دارد. API روی `127.0.0.1:8080` باقی می‌ماند و نباید عمومی شود.
- گواهی HTTPS خود سایت از ACME عمومی است و مرورگرهای معمولی باید آن را بدون نصب Root خصوصی بشناسند.
- گواهی‌هایی که CA-Panel برای دامنه کاربران صادر می‌کند همچنان Private CA هستند؛ برای اعتماد به آن‌ها Root CA را فقط پس از تطبیق SHA-256 از کانال مستقل، روی دستگاه مقصد نصب کنید.
- گواهی‌های صادرشده برای دامنه کاربران پیش‌فرض ۳۰ روز اعتبار دارند و در این نسخه خودکار تمدید نمی‌شوند. Caddy فقط گواهی HTTPS خود پرتال را خودکار تمدید می‌کند.
- پرتال عمومی برای ثبت درخواست حساب مدیر نمی‌خواهد، اما هر صدور نیازمند اثبات DNS و تصویب مدیر است. مدیر با MFA وارد `/login` می‌شود و درخواست‌ها را در `/admin/requests` بررسی می‌کند.
- رمز Issuing CA، فایل کامل `.env`، کلیدهای PEM یا ZIP حاوی کلید خصوصی را در لاگ، چت یا GitHub منتشر نکنید.

## عیب‌یابی

```bash
docker compose --env-file "$HOME/CA-Panel-production.env" \
  -f compose.yaml --profile private-tls ps
docker compose --env-file "$HOME/CA-Panel-production.env" \
  -f compose.yaml --profile private-tls logs --tail=80 api caddy-private
sudo ss -lntp | grep -E ':(80|443)\\b'
```

خطای `Address already in use` یعنی پورت ۸۰ یا ۴۴۳ توسط سرویس دیگری مانند Nginx/Apache اشغال شده است. خطای ACME را در لاگ Caddy، رکوردهای DNS و دسترسی عمومی TCP 80/443 بررسی کنید. اگر TLS پرتال با `SEC_ERROR_UNKNOWN_ISSUER` مواجه شد، زنجیره عمومی ACME و گواهی زنده Caddy را بررسی کنید؛ Root خصوصی CA-Panel نباید برای TLS خود سایت لازم باشد. برای گواهی‌های صادرشده توسط Private CA، نصب Root جداگانه همچنان لازم است.
