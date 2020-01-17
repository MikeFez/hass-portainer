from datetime import datetime, timezone, timedelta
import logging
import json
import homeassistant.helpers.config_validation as cv
import requests
import voluptuous as vol
from dateutil.relativedelta import relativedelta
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME
from homeassistant.helpers.entity import Entity

from . import PORTAINER

_LOGGER = logging.getLogger(__name__)

CONF_INSTANCES = "instances"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_INCLUDE_ENDPOINTS = "include_endpoints"
CONF_EXCLUDE_ENDPOINTS = "exclude_endpoints"

SCAN_INTERVAL = timedelta(seconds=30)
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_INSTANCES): [
            {
                vol.Required(CONF_HOST): cv.url,
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_PORT, default=''): cv.string,
                vol.Optional(CONF_INCLUDE_ENDPOINTS, default=[]): cv.ensure_list,
                vol.Optional(CONF_EXCLUDE_ENDPOINTS, default=[]): cv.ensure_list,
            }
        ]
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Volkswagen sensors."""    
    sensors = []
    for portainer_configuration in config.get(CONF_INSTANCES):
        sensors.append(PortainerSensor(host=portainer_configuration.get(CONF_HOST),
                                       port=portainer_configuration.get(CONF_PORT),
                                       username=portainer_configuration.get(CONF_USERNAME),
                                       password=portainer_configuration.get(CONF_PASSWORD),
                                       include_endpoints=portainer_configuration.get(CONF_INCLUDE_ENDPOINTS),
                                       exclude_endpoints=portainer_configuration.get(CONF_EXCLUDE_ENDPOINTS)))
    add_entities(sensors, True)
    return

class Endpoint():
    def __init__(endpoint_json):
        self.id = endpoint_json['Id']
        self.name = endpoint_json['Name']
        self.status = endpoint_json['Status']
        self.containers = []

    class Container():
        def __init__(container_json):
            self.id = container_json['Id']
            self.name = container_json['Names'][0][1:]
            self.image = container_json['Image']
            self.status = container_json['Status']
            self.state = container_json['State']
        
class PortainerSensor(Entity):
    """Implementation of an Portainer sensor"""
    def __init__(self, host, port, username, password, include_endpoints, exclude_endpoints):
        """Initialize the sensor"""
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._include_endpoints = include_endpoints
        self._exclude_endpoints = exclude_endpoints
        
        self._name = f"portainer_{host}"
        self._api_url = f"{host}{':' + port if port else ''}/api"
        self._api_token = None
        
        self.endpoints = []
        self.refresh_authentication_token()
        
    
    @property
    def name(self):
        """Return the name of the sensor"""
        return self._name

    @property
    def state(self):
        """Return the next arrival time"""
        return str(len(self.endpoints))

    @property
    def device_state_attributes(self):
        """Return the state attributes """
        logging.debug("Returing attributes")
        attributes = {endpoint.name: son.dumps([container.name for container in endpoint.containers] for endpoint in self.endpoints)}
        return attributes
        
    def refresh_authentication_token(self):
        logging.debug("Refreshing API Authentication Token")
        res = requests.post(f"{self._api_url}/auth", json={"Username": self._username, "Password": self._password})
        res.raise_for_status()
        self._api_token = "Bearer " + res.json()['jwt']
        return
        
    def get_endpoints(self):
        logging.debug("Gathering list of endpoints")
        res = requests.get(f"{self._api_url}/endpoints", headers={"Authorization": self._api_token})
        res.raise_for_status()
        logging.warning(res.json())
        endpoints = [Endpoint(endpoint_json) for endpoint_json in res.json()]
        if self._include_endpoints:
            endpoints = [endpoint for endpoint in endpoints if endpoint.name not in self._exclude_endpoints]
        if self._include_endpoints:
            endpoints = [endpoint for endpoint in endpoints if endpoint.name in self._include_endpoints]
        return endpoints
        
    def get_containers(self, endpoint):
        logging.info(f"Gathering list of containers within {endpoint['Name']}")
        res = requests.get(f"{self._api_url}/endpoints/{endpoint.id}/docker/containers/json", headers={"Authorization": self._api_token})
        res.raise_for_status()
        containers = [Endpoint.Container(container_json) for container_json in res.json()]
        return containers

    def update(self):
        """Get the latest data and update the state."""
        try:
            for endpoint in self.get_endpoints():
                endpoint.get_containers = self.get_containers()
        except Exception as e:
            logging.exception(f"Encountered Exception: {e}")
