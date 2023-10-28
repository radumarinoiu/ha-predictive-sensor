import datetime
import logging
from typing import List

from homeassistant.components.recorder import get_instance, history
from homeassistant.components.recorder.models import LazyState
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, EVENT_HOMEASSISTANT_START, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import callback, CoreState, HomeAssistant, State
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from custom_components.ha_predictive_sensor import PLATFORMS, DOMAIN
from custom_components.ha_predictive_sensor.const import CONF_SENSOR


_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: None = None,
):
    """Set up the smart dual thermostat platform."""

    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)

    name = config[CONF_NAME]
    sensor_entity_id = config[CONF_SENSOR]
    unit = hass.config.units.temperature_unit
    unique_id = config.get(CONF_UNIQUE_ID)

    async_add_entities(
        [
            PredictiveSensor(
                name,
                sensor_entity_id,
                unique_id,
                unit,
            )
        ]
    )


class PredictiveSensor(SensorEntity, RestoreEntity):
    def __init__(self, name, sensor_entity, unique_id, unit):
        self._name = name
        self._unique_id = unique_id
        self._unit = unit
        self.temperature_entity_id = sensor_entity

        self.max_history_entries = 10
        self._sensor_temperature_history = list()
        self._predicted_temp = 0.0
        # self.device_class = "temperature"

    @property
    def native_value(self):
        """Return the sensor temperature."""
        return self._predicted_temp

    def _recalculate_prediction(self):
        """This currently does average, but it should do prediction in the future"""
        # This function would do predictions based on a vector value representing Temperature change per second
        # temp[-1] + sum([(temp[index+1]-temp[index])/time_diff[index] for index in range(len(temp)-1)])/(len(temp)-1) * 60 * 60 (1 hour into the future)
        if self._sensor_temperature_history:
            self._predicted_temp = sum(self._sensor_temperature_history)/len(self._sensor_temperature_history)

    async def _update_sensor_history(self):
        end = datetime.datetime.now()
        start = end - datetime.timedelta(hours=2)
        start, end = dt_util.as_utc(start), dt_util.as_utc(end)
        _sensor_temperature_histories = await get_instance(self.hass).async_add_executor_job(
            history.state_changes_during_period,
            self.hass,
            start,
            end,
            self.temperature_entity_id,
        )
        new_history = [elem.state for elem in _sensor_temperature_histories.get(self.temperature_entity_id, list())]
        if new_history:
            _LOGGER.info(f"New Historical data: {new_history}")
            self._sensor_temperature_history = new_history
        else:
            _LOGGER.warning(f"Failed fetching sensor history: {new_history}")

    @callback
    def _async_update_temp(self, state):
        """Update thermostat with latest state from sensor."""
        try:
            # self._sensor_temperature_history.append(float(state.state))
            self._recalculate_prediction()
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s", ex)

    async def _async_sensor_changed(self, event):
        """Handle temperature changes"""
        new_state: State = event.data.get("new_state")
        _LOGGER.info(f"Sensor change: {event.data} -> {new_state}")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        if new_state.entity_id != self.temperature_entity_id:
            return

        await self._update_sensor_history()
        await self._async_update_temp(new_state)


    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Add listener
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self.temperature_entity_id], self._async_sensor_changed
            )
        )

        @callback
        def _async_startup(*_):
            sensor_state = self.hass.states.get(self.temperature_entity_id)
            if sensor_state and sensor_state.state not in (
                    STATE_UNAVAILABLE,
                    STATE_UNKNOWN,
            ):
                self._async_update_temp(sensor_state)
                self.async_write_ha_state()

        if self.hass.state == CoreState.running:
            _async_startup()
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique id of this thermostat."""
        return self._unique_id

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit
