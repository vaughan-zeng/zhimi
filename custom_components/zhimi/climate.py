"""
Support for Zhimi Air Condition ma1
"""
import enum
import logging
import asyncio
from functools import partial
from datetime import timedelta
import voluptuous as vol
from typing import Optional
import click

from miio import Device, DeviceException
from miio.click_common import command, format_output, EnumType

from .airconditioning import AirCondition, LcdBrightness, FanSpeed, SwingMode

# from homeassistant.core import callback
from homeassistant.components.climate import ClimateEntity, PLATFORM_SCHEMA
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    # ATTR_SWING_MODE,
    # ATTR_FAN_MODE,
    DOMAIN,
    HVAC_MODES,
    HVAC_MODE_OFF,
    # HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    PRESET_COMFORT,
    PRESET_SLEEP,
    PRESET_NONE,
    SUPPORT_SWING_MODE,
    SUPPORT_FAN_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_PRESET_MODE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    # ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_HOST,
    CONF_TOKEN,
    CONF_BRIGHTNESS,
    # CONF_TIMEOUT,
    TEMP_CELSIUS,
)

from homeassistant.exceptions import PlatformNotReady
# from homeassistant.helpers.event import async_track_state_change
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import config_validation as cv, entity_platform, service
# from homeassistant.util.dt import utcnow

_LOGGER = logging.getLogger(__name__)

SUCCESS = ['ok']


DEFAULT_NAME = 'Zhimi Air Condition'
DATA_KEY = 'climate.zhimi'
TARGET_TEMPERATURE_STEP = 0.1

CONF_MIN_TEMP = 'min_temp'
CONF_MAX_TEMP = 'max_temp'
CONF_ANGLE = 'angle'
CONF_TIMER = 'timer'

ATTR_AIR_CONDITION_MODEL = "ac_model"
ATTR_SWING_ANGLE = "swing_angle"
# ATTR_LCD_AUTO = "lcd_auto"
# ATTR_LCD_LEVEL = "lcd_level"
ATTR_LCD_SETTING = "lcd_setting"
ATTR_VOLUME = "volume"
# ATTR_SLEEP = "sleep"
# ATTR_COMFORT = "comfort"
ATTR_IDLE_TIMER = "idle_timer"
ATTR_OPEN_TIMER = "open_timer"
# CONF_COMMAND = "command"

SCAN_INTERVAL = timedelta(seconds=60)

SUPPORT_FLAGS = (SUPPORT_TARGET_TEMPERATURE |
                 SUPPORT_FAN_MODE |
                 SUPPORT_SWING_MODE |
                 SUPPORT_PRESET_MODE)
SUPPORT_PRESET = [PRESET_COMFORT, PRESET_SLEEP, PRESET_NONE]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_MIN_TEMP, default=16): vol.Coerce(int),
    vol.Optional(CONF_MAX_TEMP, default=30): vol.Coerce(int),
})

SERVICE_TURN_ON_AC_VOLUME = "turn_on_ac_volume"
SERVICE_TURN_OFF_AC_VOLUME = "turn_off_ac_volume"
SERVICE_SET_AC_LCD_LEVEL = "set_ac_lcd_level"
SERVICE_SET_AC_SWING_ANGLE = "set_ac_swing_angle"
SERVICE_SET_AC_IDLE_TIMER = "set_ac_idle_timer"
SERVICE_SET_AC_OPEN_TIMER = "set_ac_open_timer"

SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTITY_ID): cv.entity_ids})
SERVICE_SCHEMA_LCD_level = SERVICE_SCHEMA.extend(
    {vol.Required(CONF_BRIGHTNESS, default=3): vol.All(int, vol.Range(min=0, max=6))})
SERVICE_SCHEMA_SWING_ANGLE = SERVICE_SCHEMA.extend(
    {vol.Required(CONF_ANGLE, default=25): vol.All(int, vol.Range(min=0, max=60))})
SERVICE_SCHEMA_TIMER = SERVICE_SCHEMA.extend(
    {vol.Required(CONF_TIMER, default=90): vol.All(int, vol.Range(min=0, max=480))})

SERVICE_TO_METHOD = {
    SERVICE_TURN_ON_AC_VOLUME: {"method": "async_turn_on_ac_volume"},
    SERVICE_TURN_OFF_AC_VOLUME: {"method": "async_turn_off_ac_volume"},
    SERVICE_SET_AC_LCD_LEVEL: {
        "method": "async_set_ac_lcd_level",
        "schema": SERVICE_SCHEMA_LCD_level,},
    SERVICE_SET_AC_SWING_ANGLE: {
        "method": "async_set_ac_swing_angle",
        "schema": SERVICE_SCHEMA_SWING_ANGLE,},
    SERVICE_SET_AC_IDLE_TIMER: {
        "method": "async_set_ac_idle_timer",
        "schema": SERVICE_SCHEMA_TIMER,},
    SERVICE_SET_AC_OPEN_TIMER: {
        "method": "async_set_ac_open_timer",
        "schema": SERVICE_SCHEMA_TIMER,},
}


class OperationMode(enum.Enum):
    off = HVAC_MODE_OFF
    # automode = HVAC_MODE_AUTO
    cooling = HVAC_MODE_COOL
    heat = HVAC_MODE_HEAT
    wind = HVAC_MODE_FAN_ONLY
    arefaction = HVAC_MODE_DRY


# pylint: disable=unused-argument
@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the air condition companion from config."""
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    host = config.get(CONF_HOST)
    token = config.get(CONF_TOKEN)
    name = config.get(CONF_NAME)
    min_temp = config.get(CONF_MIN_TEMP)
    max_temp = config.get(CONF_MAX_TEMP)

    _LOGGER.info("Initializing with host %s (token %s...)", host, token[:5])

    try:
        device = AirCondition(host, token)
        device_info = device.info()
        model = device_info.model
        unique_id = "{}-{}".format(model, device_info.mac_address)
        _LOGGER.info(
            "model: %s, firmware_ver: %s, hardware_ver: %s detected",
            model,
            device_info.firmware_version,
            device_info.hardware_version,
        )
    except DeviceException as ex:
        _LOGGER.error("Device unavailable or token incorrect: %s", ex)
        raise PlatformNotReady

    zhimi_air_condition = ZhimiAirCondition(
        hass, name, device, model, unique_id, min_temp, max_temp)
    hass.data[DATA_KEY][host] = zhimi_air_condition
    async_add_devices([zhimi_air_condition], update_before_add=True)

    async def async_service_handler(service):
        """Map services to methods on ZhimiAirConditioningCompanion."""
        method = SERVICE_TO_METHOD.get(service.service)
        params = {
            key: value for key, value in service.data.items() if key != ATTR_ENTITY_ID
        }
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        if entity_ids:
            devices = [
                device
                for device in hass.data[DATA_KEY].values()
                if device.entity_id in entity_ids
            ]
        else:
            devices = hass.data[DATA_KEY].values()

        update_tasks = []
        for device in devices:
            if not hasattr(device, method["method"]):
                continue
            await getattr(device, method["method"])(**params)
            update_tasks.append(device.async_update_ha_state(True))

        if update_tasks:
            await asyncio.wait(update_tasks, loop=hass.loop)


    platform = entity_platform.current_platform.get()

    platform.async_register_entity_service(
        SERVICE_TURN_ON_AC_VOLUME,
        {vol.Required(ATTR_ENTITY_ID): cv.entity_ids},
        "async_turn_on_ac_volume",
    )
    platform.async_register_entity_service(
        SERVICE_TURN_OFF_AC_VOLUME,
        {vol.Required(ATTR_ENTITY_ID): cv.entity_ids},
        "async_turn_off_ac_volume",
    )
    platform.async_register_entity_service(
        SERVICE_SET_AC_LCD_LEVEL,
        {vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(CONF_BRIGHTNESS, default=3): vol.All(int, vol.Range(min=0, max=6))},
        "async_set_ac_lcd_level",
    )
    platform.async_register_entity_service(
        SERVICE_SET_AC_SWING_ANGLE,
        {vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(CONF_ANGLE, default=25): vol.All(int, vol.Range(min=0, max=60))},
        "async_set_ac_swing_angle",
    )
    platform.async_register_entity_service(
        SERVICE_SET_AC_IDLE_TIMER,
        {vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(CONF_TIMER, default=90): vol.All(int, vol.Range(min=0, max=480))},
        "async_set_ac_idle_timer",
    )
    platform.async_register_entity_service(
        SERVICE_SET_AC_OPEN_TIMER,
        {vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(CONF_TIMER, default=90): vol.All(int, vol.Range(min=0, max=480))},
        "async_set_ac_open_timer",
    )


class ZhimiAirCondition(ClimateEntity):
    """Representation of a Zhimi Air Condition."""

    def __init__(self, hass, name, device, model, unique_id,
                 min_temp, max_temp):

        """Initialize the climate device."""
        self.hass = hass
        self._name = name
        self._device = device
        self._model = model
        self._unique_id = unique_id
        self._available = False
        self._state = None
        self._state_attrs = {
            ATTR_AIR_CONDITION_MODEL: self._model,
            ATTR_TEMPERATURE: None,
            ATTR_HVAC_MODE: None,
            ATTR_SWING_ANGLE: None,
            # ATTR_LCD_AUTO: None,
            # ATTR_LCD_LEVEL: None,
            ATTR_LCD_SETTING: None,
            ATTR_VOLUME: None,
            ATTR_IDLE_TIMER: None,
            ATTR_OPEN_TIMER: None,
        }
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._current_temperature = None
        self._target_temperature = None
        self._hvac_mode = None
        self._fan_speed = None
        self._swing_mode = None
        self._preset_mode = None
        self._sleep = None
        self._comfort = None

    @asyncio.coroutine
    def _try_command(self, mask_error, func, *args, **kwargs):
        """Call a command handling error messages."""
        try:
            result = yield from self.hass.async_add_job(
                partial(func, *args, **kwargs))

            _LOGGER.debug("Response received: %s", result)
            self.schedule_update_ha_state()

            return result == SUCCESS
        except DeviceException as exc:
            _LOGGER.error(mask_error, exc)
            self._available = False
            return False

    @asyncio.coroutine
    def async_turn_on(self, speed: str = None, **kwargs) -> None:
        """Turn the miio AC on."""
        result = yield from self._try_command(
            "Turning the miio AC on failed.", self._device.on)
        if result:
            self._state = True

    @asyncio.coroutine
    def async_turn_off(self, **kwargs) -> None:
        """Turn the miio AC off."""
        result = yield from self._try_command(
            "Turning the miio AC off failed.", self._device.off)
        if result:
            self._state = False

    @asyncio.coroutine
    def async_update(self):
        """Update the state of this climate device."""
        try:
            state = yield from self.hass.async_add_job(self._device.status)
            _LOGGER.debug("Got new state: %s", state)
            # Got new state: <AirConditionStatus power=on, mode=cooling, target_temp=26.9, 
            # temperature=26.7, swing=off, fan_speed=1, lcd_auto=off, lcd_level=2, volume=on, 
            # sleep=off, comfort=off>
            self._available = True
            self._state_attrs.update(
                {
                    ATTR_TEMPERATURE: state.target_temp,
                    ATTR_HVAC_MODE: state.mode if self._state else "off",
                    ATTR_SWING_ANGLE: state.swing_angle,
                    # ATTR_LCD_AUTO: state.lcd_auto,
                    # ATTR_LCD_LEVEL: state.lcd_level,
                    ATTR_LCD_SETTING: LcdBrightness(state.lcd_setting).name,
                    ATTR_VOLUME: state.volume,
                    ATTR_IDLE_TIMER: state.idle_timer,
                    ATTR_OPEN_TIMER: state.open_timer,
                }
            )

            # 确认什么情况下power为off和on?
            if state.power == "off":
                self._hvac_mode = HVAC_MODE_OFF
                self._state = False
            else:
                if state.mode == "automode":
                    self._last_on_operation = HVAC_MODE_OFF
                else:
                    self._last_on_operation = OperationMode[state.mode].value
                self._hvac_mode = self._last_on_operation
                self._state = True

            self._target_temperature = state.target_temp
            self._current_temperature = state.temperature
            self._fan_speed = FanSpeed(state.fan_speed).name
            self._swing_mode = SwingMode(state.swing_setting).name
            self._comfort = state.comfort
            self._sleep = state.sleep
            if state.comfort == 'on':
                self._preset_mode = PRESET_COMFORT
            elif state.sleep == 'on':
                self._preset_mode = PRESET_SLEEP
            else:
                self._preset_mode = PRESET_NONE
            # _LOGGER.info("AAA self._preset_mode: %s", self._preset_mode)

        except DeviceException as ex:
            self._available = False
            _LOGGER.error("Got exception while fetching the state: %s", ex)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._max_temp

    @property
    def target_temperature_step(self):
        """Return the target temperature step."""
        return TARGET_TEMPERATURE_STEP

    @property
    def should_poll(self):
        """Return the polling state."""
        return True

    @property
    def unique_id(self):
        """Return an unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def available(self):
        """Return true when state is known."""
        return self._available

    @property
    def device_state_attributes(self):
        """Return the state attributes of the device."""
        return self._state_attrs

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @asyncio.coroutine
    def async_set_temperature(self, **kwargs):
        """Set target temperature."""
        if self._hvac_mode == HVAC_MODE_OFF or self._hvac_mode == HVAC_MODE_FAN_ONLY:
            return

        if kwargs.get(ATTR_TEMPERATURE) is not None:
            self._target_temperature = kwargs.get(ATTR_TEMPERATURE)
        if kwargs.get(ATTR_HVAC_MODE) is not None:
            self._hvac_mode = kwargs.get(ATTR_HVAC_MODE)

        yield from self._try_command(
            "Setting temperature of the miio AC failed.",
            self._device.set_temperature, self._target_temperature)


    @property
    def last_on_operation(self):
        """Return the last operation when the AC is on (ie heat, cool, fan only)"""
        return self._last_on_operation

    @property
    def hvac_mode(self):
        """Return new hvac mode ie. heat, cool, fan only."""
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """Return the list of available hvac modes."""
        return [mode.value for mode in OperationMode]

    @asyncio.coroutine
    def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if hvac_mode == OperationMode.off.value:
            result = yield from self._try_command(
                "Turning the ac mode to off failed.", self._device.off)
            if result:
                self._state = False
                self._hvac_mode = HVAC_MODE_OFF
        else:
            if self._hvac_mode == HVAC_MODE_OFF:
                result = yield from self._try_command(
                    "Turning the ac mode to on failed.", self._device.on)
                if not result:
                    return
            self._hvac_mode = OperationMode(hvac_mode).name
            self._state = True
            result = yield from self._try_command(
                "Setting hvac mode of the ac failed.",
                self._device.set_mode, self._hvac_mode)
            if result:
                self.async_update()

    @property
    def preset_mode(self):
        """Return the current preset mode (comfort, sleep, none)."""
        return self._preset_mode

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        return SUPPORT_PRESET

    @asyncio.coroutine
    def async_set_preset_mode(self, preset_mode):
        """Set new preset mode."""
        if preset_mode == PRESET_NONE:
            if self._comfort != "off":
                yield from self._try_command(
                    "Turn off comfort preset of the miio AC failed.",
                    self._device.set_comfort, 'off')
            if self._sleep != "off":
                yield from self._try_command(
                    "Turn off silent preset of the miio AC failed.",
                    self._device.set_sleep, 'off')
        elif preset_mode == PRESET_COMFORT:
            if self._comfort != "on":
                yield from self._try_command(
                    "Turn on comfort preset of the miio AC failed.",
                    self._device.set_comfort, 'on')
            if self._sleep != "off":
                yield from self._try_command(
                    "Turn off silent preset of the miio AC failed.",
                    self._device.set_sleep, 'off')
        elif preset_mode == PRESET_SLEEP:
            if self._sleep != "on":
                yield from self._try_command(
                    "Turn on silent preset of the miio AC failed.",
                    self._device.set_sleep, 'on')
            if self._comfort != "off":
                yield from self._try_command(
                    "Turn off comfort preset of the miio AC failed.",
                    self._device.set_comfort, 'off')

    @property
    def swing_mode(self):
        """Return the current swing setting."""
        return self._swing_mode

    @property
    def swing_modes(self):
        """List of available swing modes."""
        return [mode.name for mode in SwingMode]

    @asyncio.coroutine
    def async_set_swing_mode(self, swing_mode):
        """Set the swing mode."""
        if self.supported_features & SUPPORT_SWING_MODE == 0:
            return

        if swing_mode == 'Off':
            yield from  self._try_command(
                "Setting swing mode of the miio AC failed.",
                self._device.set_swing, 'off')
        else:
            yield from  self._try_command(
                "Setting swing mode of the miio AC failed.",
                self._device.set_swing, 'on')
            
            swing_end = int(swing_mode[-2:])
            yield from  self._try_command(
                "Setting Vertical Swing End of the miio AC failed.",
                self._device.set_ver_range, swing_end)

    @property
    def fan_mode(self):
        """Return fan speed."""
        return self._fan_speed

    @property
    def fan_modes(self):
        """Return the list of available fan speeds."""
        return [speed.name for speed in FanSpeed]

    @asyncio.coroutine
    def async_set_fan_mode(self, fan_mode):
        """Set the fan speed."""
        # _LOGGER.info("CCC fan_speed: (%s)", fan_mode)
        if self.supported_features & SUPPORT_FAN_MODE == 0:
            return
        if self._hvac_mode == HVAC_MODE_DRY:
            return

        self._fan_speed = FanSpeed[fan_mode].name
        fan_speed_value = FanSpeed[fan_mode].value

        yield from self._try_command(
            "Setting fan speed of the miio AC failed.",
            self._device.set_fan_speed, fan_speed_value)

    @asyncio.coroutine
    def async_turn_on_ac_volume(self):
        """Setting the volume on."""
        yield from  self._try_command(
            "Setting volume on of the miio AC failed.",
            self._device.set_volume, "on")

    @asyncio.coroutine
    def async_turn_off_ac_volume(self):
        """Setting the volume to off."""
        yield from  self._try_command(
            "Setting volume off of the miio AC failed.",
            self._device.set_volume, "off")

    @asyncio.coroutine
    def async_set_ac_lcd_level(self, brightness):
        """Setting the lcd level."""
        yield from  self._try_command(
            "Setting lcd level of the miio AC failed.",
            self._device.set_lcd_level, brightness)

    @asyncio.coroutine
    def async_set_ac_swing_angle(self, angle):
        """Setting the swing vertical angle."""
        yield from  self._try_command(
            "Setting lcd level of the miio AC failed.",
            self._device.set_swing_angle, angle)

    @asyncio.coroutine
    def async_set_ac_idle_timer(self, timer):
        """Setting the AC idle timer."""
        yield from  self._try_command(
            "Setting idle timer of the miio AC failed.",
            self._device.set_idle_timer, timer)

    @asyncio.coroutine
    def async_set_ac_open_timer(self, timer):
        """Setting the AC open timer."""
        yield from  self._try_command(
            "Setting open timer of the miio AC failed.",
            self._device.set_open_timer, timer)




