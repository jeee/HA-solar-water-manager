from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        PumpAdvisedSensor(coordinator, entry),
        GeneratorRunningSensor(coordinator, entry),
    ])


class Base(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Solar Water Manager",
            "manufacturer": "Custom",
            "model": "Advisory controller",
        }


class PumpAdvisedSensor(Base):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "pump_advised", "Pump advised")

    @property
    def is_on(self):
        return self.coordinator.data.get("recommendation") == "PUMP"

    @property
    def extra_state_attributes(self):
        return {"reason": self.coordinator.data.get("reason")}


class GeneratorRunningSensor(Base):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "generator_running", "Generator running")

    @property
    def is_on(self):
        return bool(self.coordinator.data.get("generator_running"))
