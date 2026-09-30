from __future__ import annotations

from datetime import timedelta
from statistics import mean
from typing import Any
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, DEFAULTS

_LOGGER = logging.getLogger(__name__)
SUNNY = {"sunny", "clear-night"}
GOOD = {"partlycloudy"}
POOR = {"cloudy", "fog", "rainy", "pouring", "snowy", "snowy-rainy", "hail", "lightning", "lightning-rainy", "exceptional"}


def _float_state(hass, entity_id, default=None):
    if not entity_id:
        return default
    st = hass.states.get(entity_id)
    if st is None or st.state in ("unknown", "unavailable", None):
        return default
    try:
        return float(st.state)
    except (TypeError, ValueError):
        return default


def _state(hass, entity_id, default="unknown"):
    if not entity_id:
        return default
    st = hass.states.get(entity_id)
    return st.state if st else default


class SolarWaterCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(hass, logger=_LOGGER, name=DOMAIN, update_interval=timedelta(minutes=5))
        self.entry = entry
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.history: dict[str, Any] = {"water": [], "overnights": [], "sunset": None}
        self._unsub_sun = None
        self._last_water_sample = 0.0

    @property
    def cfg(self):
        return {**DEFAULTS, **self.entry.data, **self.entry.options}

    async def async_start(self):
        loaded = await self.store.async_load()
        if loaded:
            self.history.update(loaded)
        self._unsub_sun = async_track_state_change_event(self.hass, ["sun.sun"], self._sun_changed)

    async def async_stop(self):
        if self._unsub_sun:
            self._unsub_sun()
            self._unsub_sun = None
        await self.store.async_save(self.history)

    @callback
    def _sun_changed(self, event):
        old = event.data.get("old_state")
        new = event.data.get("new_state")
        if not old or not new or old.state == new.state:
            return
        self.hass.async_create_task(self._handle_sun_transition(old.state, new.state))

    async def _handle_sun_transition(self, old_state, new_state):
        c = self.cfg
        soc = _float_state(self.hass, c["battery_soc_entity"])
        discharge = _float_state(self.hass, c.get("battery_discharge_energy_entity"))
        if soc is None:
            return
        if old_state == "above_horizon" and new_state == "below_horizon":
            self.history["sunset"] = {"ts": time.time(), "soc": soc, "discharge_kwh": discharge}
        elif old_state == "below_horizon" and new_state == "above_horizon":
            sunset = self.history.get("sunset")
            if sunset:
                soc_drop = max(0.0, float(sunset["soc"]) - soc)
                kwh = None
                if discharge is not None and sunset.get("discharge_kwh") is not None:
                    kwh = max(0.0, discharge - float(sunset["discharge_kwh"]))
                self.history.setdefault("overnights", []).append({
                    "ts": time.time(),
                    "soc_drop": round(soc_drop, 2),
                    "discharge_kwh": round(kwh, 3) if kwh is not None else None,
                })
                days = int(c["overnight_history_days"])
                self.history["overnights"] = self.history["overnights"][-max(days, 1):]
                self.history["sunset"] = None
                await self.store.async_save(self.history)
        await self.async_request_refresh()

    async def _weather_forecast(self, entity_id):
        if not entity_id:
            return []
        try:
            response = await self.hass.services.async_call(
                "weather", "get_forecasts", {"type": "daily"},
                target={"entity_id": entity_id}, blocking=True, return_response=True,
            )
            return (response or {}).get(entity_id, {}).get("forecast", [])
        except Exception as err:
            _LOGGER.debug("Could not fetch weather forecast for %s: %s", entity_id, err)
            return []

    def _weather_score(self, forecast):
        if not forecast:
            return None
        cond = str(forecast.get("condition", "")).lower()
        cloud = forecast.get("cloud_coverage")
        try:
            cloud_score = max(0.0, min(1.0, 1.0 - float(cloud) / 100.0)) if cloud is not None else None
        except (TypeError, ValueError):
            cloud_score = None
        condition_score = 0.85 if cond in SUNNY else 0.6 if cond in GOOD else 0.25 if cond in POOR else 0.5
        return round(condition_score if cloud_score is None else (condition_score + cloud_score) / 2, 2)

    def _water_trend(self, samples):
        if len(samples) < 2:
            return None
        oldest, newest = samples[0], samples[-1]
        days = (newest["ts"] - oldest["ts"]) / 86400.0
        if days < 0.25:
            return None
        return round((newest["cm"] - oldest["cm"]) / days, 2)

    async def _async_update_data(self):
        c = self.cfg
        now = time.time()
        water = _float_state(self.hass, c["water_entity"])
        soc = _float_state(self.hass, c["battery_soc_entity"])
        batt_power = _float_state(self.hass, c["battery_power_entity"])
        batt_state = _state(self.hass, c["battery_state_entity"])
        pv = _float_state(self.hass, c["pv_power_entity"], 0.0)
        remaining = _float_state(self.hass, c["forecast_remaining_entity"])
        tomorrow = _float_state(self.hass, c["forecast_tomorrow_entity"])
        gen_state = _state(self.hass, c["generator_state_entity"])
        ac_source = _state(self.hass, c["ac_source_entity"])

        if water is not None and now - self._last_water_sample >= 1800:
            self.history.setdefault("water", []).append({"ts": now, "cm": water})
            cutoff = now - int(c["water_history_days"]) * 86400
            self.history["water"] = [x for x in self.history["water"] if x["ts"] >= cutoff]
            self._last_water_sample = now
            await self.store.async_save(self.history)

        water_trend = self._water_trend(self.history.get("water", []))
        days_to_min = None
        if water is not None and water_trend is not None and water_trend < -0.1:
            days_to_min = max(0.0, (water - float(c["minimum_depth_cm"])) / (-water_trend))

        overs = self.history.get("overnights", [])
        avg_overnight_soc = round(mean([x["soc_drop"] for x in overs]), 1) if overs else None
        kwhs = [x["discharge_kwh"] for x in overs if x.get("discharge_kwh") is not None]
        avg_overnight_kwh = round(mean(kwhs), 2) if kwhs else None
        target_sunset_soc = min(100.0, (avg_overnight_soc if avg_overnight_soc is not None else 25.0) + float(c["battery_reserve_margin_pct"]))

        primary = await self._weather_forecast(c.get("weather_primary_entity"))
        secondary = await self._weather_forecast(c.get("weather_secondary_entity"))
        horizon = int(c["forecast_horizon_days"])
        long_range = []
        for i in range(min(horizon, max(len(primary), len(secondary)))):
            p = self._weather_score(primary[i]) if i < len(primary) else None
            s = self._weather_score(secondary[i]) if i < len(secondary) else None
            vals = [x for x in (p, s) if x is not None]
            score = round(mean(vals), 2) if vals else None
            long_range.append({
                "day": i, "score": score,
                "primary": primary[i].get("condition") if i < len(primary) else None,
                "secondary": secondary[i].get("condition") if i < len(secondary) else None,
            })

        full = water is not None and water >= float(c["full_depth_cm"]) - float(c["full_tolerance_cm"])
        low = water is not None and water <= float(c["low_depth_cm"])
        critical = water is not None and water <= float(c["critical_depth_cm"])
        minimum = water is not None and water <= float(c["minimum_depth_cm"])
        generator_running = gen_state not in ("stopped", "unknown", "unavailable") or ac_source == "generator"
        charging = batt_state == "charging"
        good_pv_now = (pv or 0) >= float(c["minimum_good_pv_w"])
        high_soc = soc is not None and soc >= float(c["high_battery_soc_pct"])
        low_soc = soc is not None and soc < max(float(c["minimum_battery_soc_pct"]), target_sunset_soc)
        strong_tomorrow = tomorrow is not None and tomorrow >= 18.0
        future_good = any(x["score"] is not None and x["score"] >= 0.65 for x in long_range[1:4])

        recommendation, reason = "WAIT", "Waiting for a better solar/energy opportunity."
        if water is None:
            recommendation, reason = "HOLD", "Water-depth sensor is unavailable."
        elif soc is None:
            recommendation, reason = "HOLD", "Battery SOC sensor is unavailable."
        elif full:
            recommendation, reason = "FULL", "Tank is at the configured full level."
        elif minimum:
            recommendation, reason = "PUMP", "Water is at or below the configured minimum."
        elif critical:
            recommendation, reason = "PUMP", "Water level is critical; water security takes priority."
        elif generator_running and c["generator_policy"] in ("never", "emergency_only"):
            recommendation, reason = "WAIT", "Generator is supplying/running and water is not critical."
        elif good_pv_now and charging:
            recommendation, reason = "PUMP", "Good PV is available now and the battery is charging."
        elif high_soc and not generator_running:
            recommendation, reason = "PUMP", "Battery SOC is high; use available stored/solar energy to fill the tank."
        elif low_soc and (strong_tomorrow or future_good) and not low:
            recommendation, reason = "WAIT", "Battery reserve is low and a better solar opportunity is forecast."
        elif low and not generator_running and soc >= float(c["generator_guard_soc_pct"]):
            recommendation, reason = "PUMP", "Water is low and battery SOC remains above the generator guard."
        elif charging and not low_soc and not generator_running:
            recommendation, reason = "PUMP", "Battery is charging and reserve is adequate; continue toward a full tank."
        else:
            recommendation, reason = "WAIT", "Tank needs water, but current energy conditions favor waiting."

        return {
            "recommendation": recommendation, "reason": reason,
            "water_cm": water, "water_trend_cm_day": water_trend,
            "days_to_minimum": round(days_to_min, 1) if days_to_min is not None else None,
            "battery_soc": soc, "battery_power_w": batt_power, "battery_state": batt_state,
            "pv_power_w": pv, "solar_remaining_kwh": remaining, "solar_tomorrow_kwh": tomorrow,
            "avg_overnight_soc_pct": avg_overnight_soc, "avg_overnight_kwh": avg_overnight_kwh,
            "target_sunset_soc_pct": round(target_sunset_soc, 1), "overnight_samples": len(overs),
            "generator_state": gen_state, "ac_source": ac_source,
            "generator_running": generator_running, "long_range": long_range,
            "monitor_only": bool(c["monitor_only"]),
        }
