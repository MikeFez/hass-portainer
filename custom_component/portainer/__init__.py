"""Portainer Platform Integration"""
from datetime import timedelta
import logging
from typing import Sequence, TypeVar, Union
import json
import homeassistant.helpers.config_validation as cv
import requests
import voluptuous as vol
from homeassistant.helpers.entity import Entity

DOMAIN = 'portainer'

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_FILTER = "filter"
CONF_FILTER_ENDPOINT = "endpoint"
CONF_FILTER_ENDPOINT_ENABLED = "enabled"
CONF_FILTER_INCLUDE_CONTAINERS = "include_containers"
CONF_FILTER_EXCLUDE_CONTAINERS = "exclude_containers"

T = TypeVar("T")  # pylint: disable=invalid-name

# This version of ensure_list interprets an empty dict as no value
def ensure_list(value: Union[T, Sequence[T]]) -> Sequence[T]:
    """Wrap value in list if it is not one."""
    if value is None or (isinstance(value, dict) and not value):
        return []
    return value if isinstance(value, list) else [value]


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): cv.url,
                        vol.Required(CONF_USERNAME): cv.string,
                        vol.Required(CONF_PASSWORD): cv.string,
                        vol.Optional(CONF_PORT, default=''): cv.string,
                        vol.Optional(CONF_FILTER, default=[]): vol.All(
                            ensure_list,
                            [
                                vol.Schema(
                                    {
                                        vol.Required(CONF_FILTER_ENDPOINT): cv.string,
                                        vol.Optional(CONF_FILTER_ENDPOINT_ENABLED, default=True): cv.boolean,
                                        vol.Optional(CONF_FILTER_INCLUDE_CONTAINERS, default=[]): cv.ensure_list,
                                        vol.Optional(CONF_FILTER_EXCLUDE_CONTAINERS, default=[]): cv.ensure_list,
                                    }
                                )
                            ],
                        )
                    }
                )
            ],
        )
    },
    extra=vol.ALLOW_EXTRA,
)

class PortainerHost():
    """Implementation of an Portainer sensor"""
    def __init__(self, host, port, username, password, endpoint_filter):
        """Initialize the sensor"""
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._endpoint_filter = endpoint_filter
        
        self._name = f"portainer_{host}"
        self._api_url = f"{host}{':' + port if port else ''}/api"
        self._api_token = None
        
        self.endpoints = []
        
        self.refresh_authentication_token()
        self.refresh_endpoints()
        
    def refresh_authentication_token(self):
        logging.debug("Refreshing API Authentication Token")
        res = requests.post(f"{self._api_url}/auth", json={"Username": self._username, "Password": self._password})
        res.raise_for_status()
        self._api_token = "Bearer " + res.json()['jwt']
        return
        
    def refresh_endpoints(self):
        logging.debug("Gathering list of endpoints")
        res = requests.get(f"{self._api_url}/endpoints", headers={"Authorization": self._api_token})
        res.raise_for_status()
             
        endpoints = []
        for endpoint_json in res.json():
            endpoint = Endpoint(self, endpoint_json)
            endpoint_filter = self._endpoint_filter.get(endpoint._name, None)
            if endpoint_filter and not endpoint_filter[CONF_FILTER_ENDPOINT_ENABLED]:
                continue
            else:
                endpoint._container_filter = endpoint_filter
                endpoint.refresh_containers()
                endpoints.append(endpoint)
        self.endpoints = endpoints
        return

class Endpoint(Entity):
    """Implementation of an Portainer sensor"""
    def __init__(self, PortainerHost, endpoint_json):
        self._portainer_host = PortainerHost
        self._id = endpoint_json['Id']
        self._name = endpoint_json['Name']
        self._status = endpoint_json['Status']
        self._container_filter = self._portainer_host._endpoint_filter.get(self._name, None)
        self._containers = []

    class Container():
        def __init__(self, container_json):
            self._id = container_json['Id']
            self._name = container_json['Names'][0][1:]
            self._image = container_json['Image']
            self._status = container_json['Status']
            self._state = container_json['State']
    
    @property
    def name(self):
        """Return the name of the sensor"""
        return f"portainer_{self._name}"

    @property
    def state(self):
        """Return the next arrival time"""
        return "Online"

    @property
    def device_state_attributes(self):
        """Return the state attributes """
        logging.debug("Returing attributes")
        attributes = {}
        for container in self._containers:
            attributes[container._name] = container._state
        return attributes
        
    def refresh_containers(self):
        logging.info(f"Gathering list of containers within {self._name}")
        res = requests.get(f"{self._portainer_host._api_url}/endpoints/{self._id}/docker/containers/json", headers={"Authorization": self._portainer_host._api_token})
        res.raise_for_status()
        containers = []
        for container_json in res.json():
            container = Endpoint.Container(container_json)
            if self._container_filter:
                if container._name in self._container_filter[CONF_FILTER_EXCLUDE_CONTAINERS]:
                    continue
                if self._container_filter[CONF_FILTER_INCLUDE_CONTAINERS] and container._name not in self._container_filter[CONF_FILTER_INCLUDE_CONTAINERS]:
                    continue
            containers.append(container)  
        self._containers = containers
        return

    def update(self):
        """Get the latest data and update the state."""
        try:
            self.refresh_containers()
        except Exception as e:
            logging.exception(f"Encountered Exception: {e}")        

def setup(hass, config):
    """Setup hosts"""
    # Data that you want to share with your platforms
    hosts = []
    for portainer_configuration in config.get(DOMAIN):
        organized_endpoint_filter = {}
        for endpoint_filter in portainer_configuration.get(CONF_FILTER):
            organized_endpoint_filter[endpoint_filter.get(CONF_FILTER_ENDPOINT)] = endpoint_filter
        host = PortainerHost(host=portainer_configuration.get(CONF_HOST),
                               port=portainer_configuration.get(CONF_PORT),
                               username=portainer_configuration.get(CONF_USERNAME),
                               password=portainer_configuration.get(CONF_PASSWORD),
                               endpoint_filter=organized_endpoint_filter)
        hosts.append(host)
        
    hass.data[DOMAIN] = {"hosts": hosts} 
    hass.helpers.discovery.load_platform('sensor', DOMAIN, {}, config)
    return True