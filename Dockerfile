# فرصتي — صورة Docker بديلة للنشر (Render / Railway / Fly.io / أي سحابة)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000
EXPOSE 5000

# عامل واحد فقط — المحرك التلقائي (البحث كل 12 ساعة) يعمل داخل العملية
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
