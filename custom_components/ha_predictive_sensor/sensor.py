from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity


class PredictiveSensor(SensorEntity, RestoreEntity):
    pass