# Official Python index and its linux/amd64 manifest verified against Docker Hub.
# Explicit tag + immutable digest: Supervisor no longer supplies BUILD_FROM.
FROM python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e

ARG BUILD_VERSION=0.1.1
ARG BUILD_ARCH=amd64
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.title="HAHAPent Suite Manager" \
      org.opencontainers.image.source="https://github.com/djeZo888/HAHAPent"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HAHAPENT_DATA_DIR=/data \
    HAHAPENT_CONFIG_DIR=/homeassistant

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --disable-pip-version-check --no-cache-dir --no-compile \
    --only-binary=:all: --require-hashes -r /app/requirements.txt

COPY hahapent/ /app/hahapent/
COPY schemas/ /app/schemas/
COPY hahapent.json /app/hahapent.json
COPY test-catalog.json /app/test-catalog.json
COPY THIRD_PARTY_NOTICES.md /app/THIRD_PARTY_NOTICES.md
COPY run.sh /run.sh
RUN chmod 0755 /run.sh

CMD ["/run.sh"]
