from datetime import datetime, timezone, timedelta
import logging
import json
import homeassistant.helpers.config_validation as cv
import requests

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Endpoint sensors."""    
    sensors = []
    for host in hass.data[DOMAIN]['hosts']:
        for endpoint in host.endpoints:
            sensors.append(endpoint)
    add_entities(sensors, True)
    return
