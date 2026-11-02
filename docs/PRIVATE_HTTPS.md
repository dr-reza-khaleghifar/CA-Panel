# مهاجرت HTTPS پرتال به ACME عمومی

> **وضعیت این راهنما:** روش قدیمی استفاده از گواهی TLS صادرشده توسط CA خصوصی برای خود سایت بازنشسته شده است. این روش باعث نمایش خطای `SEC_ERROR_UNKNOWN_ISSUER` در Firefox و سایر مرورگرهایی می‌شود که Root خصوصی را نصب نکرده‌اند. برای پرتال عمومی، از Caddy/ACME استفاده کنید.

## روش فعلی

Caddy برای `PANEL_DOMAIN` گواهی عمومی دریافت و تمدید می‌کند. کاربران برای بازکردن خود پرتال نیازی به نصب Root CA اختصاصی ندارند. CA-Panel خصوصی همچنان فقط برای گواهی‌های دامنه‌ای کاربران استفاده می‌شود.

پیش‌نیازها:
- رکورد DNS دامنه `PANEL_DOMAIN` به IP عمومی همین سرور اشاره کند.
- TCP پورت ۸۰ و ۴۴۳ از اینترنت به سرور برسند.
- پورت API فقط روی `127.0.0.1:8080` باقی بماند.
- داده Caddy در volume پایدار `caddy_private_data` نگهداری شود.

استقرار:

```bash
cd ~/CA-Panel
git pull --ff-only
bash install.sh --public-https
```

گزینه قدیمی `--private-https` همچنان به‌عنوان alias پذیرفته می‌شود تا دستورهای قبلی نشکنند؛ اما دیگر از Issuing CA خصوصی برای TLS خود سایت گواهی صادر نمی‌کند. نام profile در Compose نیز به دلایل سازگاری `private-tls` باقی مانده است.

## بررسی

```bash
docker compose --env-file "$HOME/CA-Panel-production.env" \
  -f compose.yaml --profile private-tls ps

curl --noproxy '*' --resolve ca1.iravand.ir:443:127.0.0.1 \
  https://ca1.iravand.ir/healthz

openssl s_client -connect 127.0.0.1:443 \
  -servername ca1.iravand.ir -verify_return_error </dev/null
```

بررسی HTTPS پرتال باید با trust store عمومی سیستم انجام شود؛ از `--cacert` برای Root CA خصوصی استفاده نکنید. اگر ACME ناموفق بود، لاگ Caddy، رکوردهای A/AAAA و دسترسی عمومی پورت‌های ۸۰ و ۴۴۳ را بررسی کنید:

```bash
docker compose --env-file "$HOME/CA-Panel-production.env" \
  -f compose.yaml --profile private-tls logs --tail=100 caddy-private
```

## درباره گواهی‌های صادرشده برای کاربران

تغییر بالا فقط TLS خود وب‌سایت را عمومی می‌کند. گواهی‌هایی که CA-Panel برای دامنه کاربران صادر می‌کند همچنان توسط Private CA امضا می‌شوند؛ برای اعتماد به آن‌ها باید Root CA را از کانال معتبر دریافت، SHA-256 آن را مستقل بررسی و طبق سیاست دستگاه نصب کنید. این Root خصوصی را در مرورگر یا سیستم‌عامل دستگاه‌های ناشناس بدون مجوز نصب نکنید.

فایل‌های قدیمی `scripts/issue_panel_tls.py` و `scripts/setup_private_tls.py` برای مهاجرت‌های تاریخی باقی مانده‌اند؛ برای راه‌اندازی جدید پرتال از آن‌ها استفاده نکنید.
