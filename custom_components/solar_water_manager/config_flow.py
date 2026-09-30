from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN, DEFAULTS


def _entity(domain=None):
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=domain)
        if domain else selector.EntitySelectorConfig()
    )


def _number(minimum, maximum, step, unit=None):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _schema(values: dict[str, Any]):
    d = {**DEFAULTS, **values}
    return vol.Schema({
        vol.Required("water_entity", default=d["water_entity"]): _entity("sensor"),
        vol.Required("battery_soc_entity", default=d["battery_soc_entity"]): _entity("sensor"),
        vol.Required("battery_power_entity", default=d["battery_power_entity"]): _entity("sensor"),
        vol.Required("battery_state_entity", default=d["battery_state_entity"]): _entity("sensor"),
        vol.Optional("battery_discharge_energy_entity", default=d["battery_discharge_energy_entity"]): _entity("sensor"),
        vol.Required("pv_power_entity", default=d["pv_power_entity"]): _entity("sensor"),
        vol.Optional("pv_energy_entity", default=d["pv_energy_entity"]): _entity("sensor"),
        vol.Required("forecast_remaining_entity", default=d["forecast_remaining_entity"]): _entity("sensor"),
        vol.Required("forecast_tomorrow_entity", default=d["forecast_tomorrow_entity"]): _entity("sensor"),
        vol.Required("weather_primary_entity", default=d["weather_primary_entity"]): _entity("weather"),
        vol.Optional("weather_secondary_entity", default=d["weather_secondary_entity"]): _entity("weather"),
        vol.Required("generator_state_entity", default=d["generator_state_entity"]): _entity("sensor"),
        vol.Required("ac_source_entity", default=d["ac_source_entity"]): _entity("sensor"),
        vol.Required("full_depth_cm", default=d["full_depth_cm"]): _number(20, 1000, 1, "cm"),
        vol.Required("full_tolerance_cm", default=d["full_tolerance_cm"]): _number(0, 50, 1, "cm"),
        vol.Required("low_depth_cm", default=d["low_depth_cm"]): _number(0, 1000, 1, "cm"),
        vol.Required("critical_depth_cm", default=d["critical_depth_cm"]): _number(0, 1000, 1, "cm"),
        vol.Required("minimum_depth_cm", default=d["minimum_depth_cm"]): _number(0, 1000, 1, "cm"),
        vol.Required("battery_reserve_margin_pct", default=d["battery_reserve_margin_pct"]): _number(0, 50, 1, "%"),
        vol.Required("minimum_battery_soc_pct", default=d["minimum_battery_soc_pct"]): _number(0, 100, 1, "%"),
        vol.Required("generator_guard_soc_pct", default=d["generator_guard_soc_pct"]): _number(0, 100, 1, "%"),
        vol.Required("minimum_good_pv_w", default=d["minimum_good_pv_w"]): _number(0, 10000, 100, "W"),
        vol.Required("high_battery_soc_pct", default=d["high_battery_soc_pct"]): _number(0, 100, 1, "%"),
        vol.Required("water_history_days", default=d["water_history_days"]): _number(2, 30, 1, "days"),
        vol.Required("overnight_history_days", default=d["overnight_history_days"]): _number(1, 30, 1, "days"),
        vol.Required("forecast_horizon_days", default=d["forecast_horizon_days"]): _number(2, 10, 1, "days"),
        vol.Required("generator_policy", default=d["generator_policy"]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": "never", "label": "Never while generator is supplying AC"},
                    {"value": "emergency_only", "label": "Emergency water only"},
                    {"value": "if_already_running", "label": "Allow if generator is already running"},
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required("monitor_only", default=d["monitor_only"]): selector.BooleanSelector(),
    })


class SolarWaterManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Solar Water Manager", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarWaterManagerOptionsFlow(config_entry)


class SolarWaterManagerOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(current))
