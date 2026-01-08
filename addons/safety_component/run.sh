#!/usr/bin/with-contenv bashio
set -e

APPD_DIR=/data
APPD_CFG="${APPD_DIR}/appdaemon.yaml"
APPS_CFG="${APPD_DIR}/apps.yaml"

if [ ! -f "${APPD_CFG}" ]; then
  HA_URL="$(bashio::config 'ha_url')"
  TOKEN="$(bashio::config 'token')"
  if [ -z "${TOKEN}" ] || [ "${TOKEN}" = "null" ]; then
    TOKEN="${SUPERVISOR_TOKEN:-${HASSIO_TOKEN:-}}"
  fi
  if [ -z "${TOKEN}" ]; then
    bashio::log.warning "No Home Assistant token provided; AppDaemon may fail to connect."
  fi

  LOG_LEVEL="$(bashio::config 'log_level' | tr '[:lower:]' '[:upper:]')"
  TIME_ZONE="$(bashio::config 'time_zone')"
  LATITUDE="$(bashio::config 'latitude')"
  LONGITUDE="$(bashio::config 'longitude')"
  ELEVATION="$(bashio::config 'elevation')"

  {
    echo "appdaemon:"
    echo "  app_dir: /app"
    echo "  log_level: ${LOG_LEVEL}"
    echo "  time_zone: ${TIME_ZONE}"
    if [ "${LATITUDE}" != "null" ] && [ -n "${LATITUDE}" ]; then
      echo "  latitude: ${LATITUDE}"
    fi
    if [ "${LONGITUDE}" != "null" ] && [ -n "${LONGITUDE}" ]; then
      echo "  longitude: ${LONGITUDE}"
    fi
    if [ "${ELEVATION}" != "null" ] && [ -n "${ELEVATION}" ]; then
      echo "  elevation: ${ELEVATION}"
    fi
    echo "  plugins:"
    echo "    HASS:"
    echo "      type: hass"
    echo "      ha_url: ${HA_URL}"
    echo "      token: ${TOKEN}"
  } > "${APPD_CFG}"
fi

if [ ! -f "${APPS_CFG}" ]; then
  cp /app/app_cfg.yaml "${APPS_CFG}"
fi

exec appdaemon -c "${APPD_DIR}"
