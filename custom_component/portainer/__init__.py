"""Portainer Platform Integration"""
PORTAINER = 'portainer'


def setup(hass, config):
    """Setup sensors ."""
    # Data that you want to share with your platforms
    hass.data[PORTAINER] = {}
    hass.helpers.discovery.load_platform('sensor', PORTAINER, {}, config)
    return True