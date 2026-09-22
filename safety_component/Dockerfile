FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM ghcr.io/home-assistant/base-python:3.12-alpine3.24

ARG BUILD_ARCH=amd64
ARG BUILD_VERSION=0.2.0

SHELL ["/bin/ash", "-o", "pipefail", "-c"]

RUN apk add --no-cache nginx

COPY safety_component/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY backend/ /opt/safety-component/backend/
COPY --from=frontend-builder /build/frontend/dist/ /opt/safety-component/frontend/
COPY safety_component/rootfs/ /

RUN chmod a+x \
        /etc/s6-overlay/scripts/init-safety-component \
        /etc/s6-overlay/s6-rc.d/safety-backend/run \
        /etc/s6-overlay/s6-rc.d/safety-backend/finish \
        /etc/s6-overlay/s6-rc.d/safety-config-api/run \
        /etc/s6-overlay/s6-rc.d/safety-config-api/finish \
        /etc/s6-overlay/s6-rc.d/safety-frontend/run \
        /etc/s6-overlay/s6-rc.d/safety-frontend/finish

LABEL \
    io.hass.name="SafetyComponent" \
    io.hass.description="Safety monitoring backend and Safety Home UI for Home Assistant" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.version="${BUILD_VERSION}" \
    org.opencontainers.image.source="https://github.com/Arkaqius/SafetyComponent" \
    org.opencontainers.image.licenses="MIT"
