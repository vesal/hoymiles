from homeassistant.core import HomeAssistant

from .http import MacipUpdateView, MacipView


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    view = MacipView(hass)
    hass.http.register_view(view)
    hass.http.register_view(MacipUpdateView(view))
    return True
