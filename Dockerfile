FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser
COPY app ./app
# Bundle the open-source Persian variable font at image build time, not runtime.
# Pinned upstream commit and Git object SHA: fail closed on download corruption.
RUN python -c 'import hashlib,pathlib,urllib.request; u="https://raw.githubusercontent.com/rastikerdar/vazirmatn/6e553e33489a8f9dfaccc76860a2e3f3c1e66de7/fonts/webfonts/Vazirmatn%5Bwght%5D.woff2"; p=pathlib.Path("/app/app/static/fonts/Vazirmatn.woff2"); p.parent.mkdir(parents=True,exist_ok=True); b=urllib.request.urlopen(u,timeout=30).read(); h=hashlib.sha1(b"blob "+str(len(b)).encode()+b"\\0"+b).hexdigest(); assert h=="a501289a85595158570b0c2badcb4608b042e748", "Vazirmatn font integrity failed"; assert b[:4]==b"wOF2", "Invalid font"; p.write_bytes(b)'
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--workers", "1"]
