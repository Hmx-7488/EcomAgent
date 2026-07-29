FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini
COPY backend/app /app/app
COPY backend/scripts /app/scripts
COPY docs/demo/products.json /app/demo/products.json
COPY backend/docker-entrypoint.sh /usr/local/bin/ecomagent-entrypoint

RUN addgroup --system --gid 10001 ecomagent \
    && adduser --system --uid 10001 --ingroup ecomagent --home /app ecomagent \
    && mkdir -p /app/uploads \
    && chown -R ecomagent:ecomagent /app /usr/local/bin/ecomagent-entrypoint \
    && chmod 0555 /usr/local/bin/ecomagent-entrypoint

USER ecomagent
EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/ecomagent-entrypoint"]