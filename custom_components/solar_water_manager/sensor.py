from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfLength, UnitOfTime
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

SENSORS = [
    ("recommendation", "Recommendation", None, None, None),
    ("reason", "Reason", None, None, None),
    ("water_cm", "Water depth", UnitOfLength.CENTIMETERS, SensorDeviceClass.DISTANCE, SensorStateClass.MEASUREMENT),
    ("water_trend_cm_day", "Water trend", "cm/day", None, SensorStateClass.MEASUREMENT),
    ("days_to_minimum", "Estimated days to minimum", UnitOfTime.DAYS, SensorDeviceClass.DURATION, SensorStateClass.MEASUREMENT),
    ("avg_overnight_soc_pct", "Average overnight battery use", PERCENTAGE, None, SensorStateClass.MEASUREMENT),
    ("avg_overnight_kwh", "Average overnight discharge", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
    ("target_sunset_soc_pct", "Target sunset SOC", PERCENTAGE, None, SensorStateClass.MEASUREMENT),
    ("solar_remaining_kwh", "Solar remaining today", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
    ("solar_tomorrow_kwh", "Solar forecast tomorrow", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
    ("overnight_samples", "Overnight learning samples", None, None, SensorStateClass.MEASUREMENT),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SWMSensor(coordinator, entry, *x) for x in SENSORS])


class SWMSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name, unit, device_class, state_class):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Solar Water Manager",
            "manufacturer": "Custom",
            "model": "Advisory controller",
        }

    @property
    def native_value(self):
        return self.coordinator.data.get(self.key)

    @property
    def extra_state_attributes(self):
        if self.key == "recommendation":
            return {
                "reason": self.coordinator.data.get("reason"),
                "generator_running": self.coordinator.data.get("generator_running"),
                "monitor_only": self.coordinator.data.get("monitor_only"),
                "long_range_weather": self.coordinator.data.get("long_range"),
            }
        return None
