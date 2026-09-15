"""Constants for PGNIG Gas Sensor."""

DOMAIN = "pgnig_gas_sensor"
CONF_AUTH_METHOD = "auth_method"
CONF_MFA_CODE = "mfa_code"
CONF_ORLEN_SESSION = "orlen_session"
CONF_MFA_ENABLED = "mfa_enabled"
DEFAULT_AUTH_METHOD = "api_login"
AUTH_METHOD_ORLEN_ID = "orlen_id"
# Orlen drops an idle EBOK session well before 30 minutes, so a refresh on a
# 30 minute timer always arrived after the session had already lapsed. Keep
# this comfortably under that window: every call resets the idle clock.
ORLEN_SESSION_REFRESH_MINUTES = 10
DATA_UPDATE_INTERVAL_HOURS = 8
