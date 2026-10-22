FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-production.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt
COPY config config
COPY portal portal
COPY templates templates
COPY static static
COPY manage.py ./
RUN useradd --uid 10001 --create-home vindex && mkdir -p staticfiles tmp && chown -R vindex:vindex /app
USER vindex
CMD ["gunicorn","config.wsgi:application","--bind","0.0.0.0:8000","--workers","2","--timeout","90","--error-logfile","-","--log-level","warning"]
