import enum
import logging
from typing import Optional
from collections import defaultdict
import click

from miio.click_common import command, format_output, EnumType
from miio import Device, DeviceException

_LOGGER = logging.getLogger(__name__)

ZHIMI_AC_MA1 = 'zhimi.aircondition.ma1'
MODELS_SUPPORTED = [ZHIMI_AC_MA1]

class AirConditionException(DeviceException):
    pass


class FanSpeed(enum.Enum):
    low = 0
    low_medium = 1
    medium = 2
    medium_high = 3
    high = 4
    auto = 5


class SwingMode(enum.Enum):
    off = 0
    end_at_20 = 20
    end_at_40 = 40
    end_at_60 = 60


class LcdBrightness(enum.Enum):
    off = 0
    level1 = 1
    level2 = 2
    level3 = 3
    level4 = 4
    level5 = 5
    auto = 6


class AirConditionStatus:
    """Container for status reports of the Zhimi Air Condition."""

    def __init__(self, data):
        """
        Device model: zhimi.aircondition.ma1
        {'mode': 'cooling',             => "automode","cooling","heat","wind","arefaction"
         'lcd_auto': 'off',
         'lcd_level': 1,                => 0 ~ 5 mean off, level 1 ~ level 5
         'volume': 'off',
         'idle_timer': 0,               => 0 ~ 28800 sec. power off delay
         'open_timer': 0,
         'power': 'on',
         'temp_dec': 244,               => current temperature * 10
         'st_temp_dec': 320,            => target temperature * 10
         'speed_level': 5,              => 0 ~ 5 mean level 1 ~ level 5, auto
         'vertical_swing': 'on',
         'vertical_end': 60,            => 20, 40, 60
         'vertical_rt': 19,             => 0 ~ 60
         'silent': 'off',               => sleep mode
         'comfort': 'off',              => cooling 24, speed_level auto
         'ptc': 'off',
         'ptc_rt': 'off',
         'ot_run_temp': 7,
         'ep_temp': 27,
         'es_temp': 13,
         'he_temp': 39,
         'compressor_frq': 0,
         'motor_speed': 1000,
         'humidity': null,
         'ele_quantity': null,
         'ex_humidity': null,
         'ot_humidity': null,
         'remote_mac': null,
         'htsensor_mac': null,
         'ht_sensor': null,}
        """

        self.data = data
        _LOGGER.debug("BBB self.data: (%s)", self.data)

    @property
    def power(self) -> bool:
        """Current power state."""
        return self.data['power']

    @property
    def mode(self) -> str:
        """Current operation mode."""
        try:
            return self.data['mode']
        except TypeError:
            return None

    @property
    def target_temp(self) -> float:
        """Target temperature."""
        return self.data['st_temp_dec'] / 10

    @property
    def temperature(self) -> float:
        """Current temperature."""
        return self.data['temp_dec'] / 10

    @property
    def swing_setting(self) -> int:
        """Vertical swing setting."""
        if self.data['vertical_swing'] == 'off':
            return 0
        else:
            return self.data['vertical_end']

    @property
    def swing_angle(self) -> int:
        """swing vertical angle."""
        return self.data['swing_angle']

    @property
    def fan_speed(self) -> int:
        """Fan speed."""
        return self.data['speed_level']

    @property
    def lcd_setting(self) -> int:
        """LCD level."""
        if self.data['lcd_auto'] == 'on':
            return 6
        else:
            return self.data['lcd_level']

    @property
    def volume(self) -> bool:
        """Volume."""
        return self.data['volume']

    @property
    def sleep(self) -> bool:
        """silent."""
        return self.data['silent']

    @property
    def comfort(self) -> bool:
        """Comfort."""
        return self.data['comfort']

    @property
    def idle_timer(self) -> int:
        """idle timer."""
        return self.data['idle_timer']

    @property
    def open_timer(self) -> int:
        """open timer."""
        return self.data['open_timer']


    def __repr__(self) -> str:
        s = "<AirConditionStatus " \
            "power=%s, " \
            "mode=%s, " \
            "target_temp=%s, " \
            "temperature=%s, " \
            "swing_setting=%s, " \
            "swing_angle=%s, " \
            "fan_speed=%s, " \
            "lcd_setting=%s, " \
            "volume=%s, " \
            "sleep=%s, " \
            "comfort=%s, " \
            "idle_timer=%s, " \
            "open_timer=%s>" % \
            (self.power,
             self.mode,
             self.target_temp,
             self.temperature,
             self.swing_setting,
             self.swing_angle,
             self.fan_speed,
             self.lcd_setting,
             self.volume,
             self.sleep,
             self.comfort,
             self.idle_timer,
             self.open_timer)
        return s

    def __json__(self):
        return self.data


class AirCondition(Device):

    def __init__(self, ip: str = None, token: str = None, model: str = ZHIMI_AC_MA1,
                 start_id: int = 0, debug: int = 0, lazy_discover: bool = True) -> None:
        super().__init__(ip, token, start_id, debug, lazy_discover)

        if model in MODELS_SUPPORTED:
            self.model = model
        else:
            _LOGGER.error("Device model %s unsupported. Falling back to %s.", model, ZHIMI_AC_MA1)

    @command(
        default_output = format_output(
            "",
            "Power: {result.power}\n"
            "Temperature: {result.temperature} °C\n"
            "Target temperature: {result.target_temperature} °C\n"
            "Mode: {result.mode}\n")
    )
    def status(self) -> AirConditionStatus:
        """Retrieve properties."""

        properties = [
            'power',
            'mode',
            'st_temp_dec',
            'temp_dec',
            'vertical_swing',
            'vertical_end',
            'vertical_rt',
            'speed_level',
            'lcd_auto',
            'lcd_level',
            'volume',
            'silent',
            'comfort',
            'idle_timer',
            'open_timer',
        ]

        # A single request is limited to 1 properties. Therefore the
        # properties are divided into multiple requests
        _props = properties.copy()
        values = []
        while _props:
            values.extend(self.send("get_prop", _props[:1]))
            _LOGGER.debug("AAA propertie: (%s), value: (%s)", _props[:1], values)
            _props[:] = _props[1:]

        properties_count = len(properties)
        values_count = len(values)
        if properties_count != values_count:
            _LOGGER.info(
                "Count (%s) of requested properties does not match the "
                "count (%s) of received values.",
                properties_count, values_count)

        return AirConditionStatus(
            defaultdict(lambda: None, zip(properties, values)))

    @command(
        default_output = format_output("Powering the air condition on"),
    )
    def on(self):
        """Turn the air condition on."""
        return self.send("set_power", ["on"])

    @command(
        default_output = format_output("Powering the air condition off"),
    )
    def off(self):
        """Turn the air condition off."""
        return self.send("set_power", ["off"])

    @command(
        click.argument("mode", type=str),
        default_output = format_output("Setting operation mode to '{mode}'")
    )
    def set_mode(self, mode: str):
        """Set operation mode."""
        return self.send("set_mode", [mode])

    @command(
        click.argument("temperature", type=float),
        default_output = format_output(
            "Setting target temperature to {temperature} degrees")
    )
    def set_temperature(self, temperature: float):
        """Set target temperature."""
        return self.send("set_temperature", [temperature * 10])

    @command(
        click.argument("fan_speed", type=int),
        default_output = format_output(
            "Setting fan speed to {fan_speed}")
    )
    def set_fan_speed(self, fan_speed: int):
        """Set fan speed."""
        if fan_speed < 0 or fan_speed > 5:
            raise AirConditionException("Invalid wind level: %s", fan_speed)
        return self.send("set_spd_level", [fan_speed])

    @command(
        click.argument("swing", type=str),
        default_output = format_output(
            "Setting swing mode to {swing}")
    )
    def set_swing(self, swing: str):
        """Set swing on/off."""
        return self.send("set_vertical", [swing])

    @command(
        click.argument("swing_end", type=bool),
        default_output = format_output(
            "Setting vertical swing end degrees to {swing_end}")
    )
    def set_ver_range(self, swing_end: int):
        """Set vertical swing end."""
        return self.send("set_ver_range", [0, swing_end])

    @command(
        click.argument("volume", type=str),
        default_output = format_output(
            lambda volume: "Turning on volume mode"
            "Setting volume mode to {volume}")
    )
    def set_volume(self, volume: str):
        """Set volume on/off."""
        return self.send("set_volume_sw", [volume])

    @command(
        click.argument("comfort", type=str),
        default_output = format_output(
            "Setting comfort preset to {comfort}")
    )
    def set_comfort(self, comfort: str):
        """Set comfort on/off."""
        return self.send("set_comfort", [comfort])

    @command(
        click.argument("sleep", type=str),
        default_output = format_output(
            "setting sleep mode to {sleep}")
    )
    def set_sleep(self, sleep: str):
        """Set sleep on/off."""
        return self.send("set_silent", [sleep])

    @command(
        click.argument("lcd_level", type=int),
        default_output = format_output(
            "Setting lcd level to {lcd_level}")
    )
    def set_lcd_level(self, lcd_level: int):
        """Set lcd level."""
        if lcd_level == 6:
            return self.send("set_lcd_auto", ["on"])
        else:
            return self.send("set_lcd", [lcd_level])

    @command(
        click.argument("angle", type=int),
        default_output = format_output(
            "Setting swing vertical angle to {angle}")
    )
    def set_swing_angle(self, angle: int):
        """Set swing vertical angle."""
        return self.send("set_ver_pos", [angle])

    @command(
        click.argument("timer", type=int),
        default_output = format_output(
            "Setting AC idle timer to {timer} minutes.")
    )
    def set_idle_timer(self, timer: int):
        """Set AC idle timer."""
        return self.send("set_idle_timer", [timer * 60])

    @command(
        click.argument("timer", type=int),
        default_output = format_output(
            "Setting AC open timer to {timer} minutes.")
    )
    def set_open_timer(self, timer: int):
        """Set AC open timer."""
        return self.send("set_open_timer", [timer * 60])


