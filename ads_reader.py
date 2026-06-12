"""
ads_reader.py
-------------
Lecteur unique pour l'ADS1115 (I2C, adresse 0x48 par defaut) partage entre :
  - le pont de Wheatstone  : mesure differentielle AIN0/AIN1 (+ AIN2 en single-ended)
  - l'angle du volant       : potentiometre sur AIN3 (single-ended)

Le schema electronique ne comporte qu'UN seul ADS1115 (U1). Les deux mesures
necessitent des gains differents :
  - Wheatstone : petit signal  -> gain eleve (ex 4 = +/-1.024 V)
  - Volant     : 0 a 3.3 V      -> gain faible (ex 1 = +/-4.096 V)

Pour eviter tout conflit, un seul thread lit le composant et regle le gain
AVANT chaque groupe de lectures. Le verrou I2C global (i2c_lock) est respecte.

Calibration angle :
    angle = angle_min + ratio * (angle_max - angle_min)
    ratio = clamp((V - v_min) / (v_max - v_min), 0, 1)
"""

import threading

from app_logger import get_logger
from i2c_lock import i2c_lock

log = get_logger(__name__)

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    ADS_AVAILABLE = True
except ImportError:
    ADS_AVAILABLE = False


class ADS1115Reader:
    """Lecteur unique ADS1115 : pont de Wheatstone + angle volant.

    Attributs publics (mis a jour par le thread interne) :
        ws_ready, ws_voltage_diff, ws_raw_diff, ws_voltage_var
        st_ready, st_angle, st_voltage
    """

    def __init__(
        self,
        address:        int   = 0x48,
        ws_enabled:     bool  = True,
        ws_gain:        int   = 4,
        st_enabled:     bool  = True,
        st_gain:        int   = 1,
        st_channel:     int   = 3,
        sample_rate:    float = 0.1,
        v_min:          float = 0.0,
        v_max:          float = 3.3,
        angle_min:      float = -450.0,
        angle_max:      float = 450.0,
    ):
        self._address     = address
        self._ws_enabled  = ws_enabled
        self._ws_gain     = ws_gain
        self._st_enabled  = st_enabled
        self._st_gain     = st_gain
        self._st_channel  = st_channel
        self._sample_rate = sample_rate

        self._v_min     = v_min
        self._v_max     = v_max
        self._angle_min = angle_min
        self._angle_max = angle_max

        self._stop_event = threading.Event()
        self._thread     = None

        # Wheatstone
        self.ws_ready:        bool  = False
        self.ws_voltage_diff: float = 0.0
        self.ws_raw_diff:     int   = 0
        self.ws_voltage_var:  float = 0.0

        # Angle volant
        self.st_ready:  bool  = False
        self.st_angle:  float = 0.0
        self.st_voltage: float = 0.0

        if not ADS_AVAILABLE:
            log.warning("adafruit-ads1x15 non installe — ADS1115 simule")

    # -- API publique ---------------------------------------------------------

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="ADS1115-Reader"
        )
        self._thread.start()
        log.info(
            "ADS1115Reader demarre (addr=0x%02X, wheatstone=%s gain=%d, volant=%s gain=%d canal A%d)",
            self._address,
            "ON" if self._ws_enabled else "OFF",
            self._ws_gain,
            "ON" if self._st_enabled else "OFF",
            self._st_gain,
            self._st_channel,
        )

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        log.info("ADS1115Reader arrete.")

    def set_calibration(self, v_min: float, v_max: float, angle_min: float, angle_max: float):
        """Met a jour la calibration de l'angle a chaud."""
        self._v_min     = v_min
        self._v_max     = v_max
        self._angle_min = angle_min
        self._angle_max = angle_max

    # -- Internals ------------------------------------------------------------

    def _voltage_to_angle(self, voltage: float) -> float:
        v_range = self._v_max - self._v_min
        if v_range == 0:
            return self._angle_min
        ratio = (voltage - self._v_min) / v_range
        ratio = max(0.0, min(1.0, ratio))
        return self._angle_min + ratio * (self._angle_max - self._angle_min)

    def _run(self):
        if not ADS_AVAILABLE:
            self._run_simulation()
            return

        try:
            with i2c_lock:
                i2c = busio.I2C(board.SCL, board.SDA)
                ads = ADS.ADS1115(i2c, address=self._address)
            log.info("ADS1115 detecte (addr=0x%02X)", self._address)
        except Exception as e:
            log.error("ADS1115 non initialise : %s", e)
            return

        if self._ws_enabled:
            self.ws_ready = True
        if self._st_enabled:
            self.st_ready = True

        while not self._stop_event.is_set():
            # -- Pont de Wheatstone (gain eleve) --
            if self._ws_enabled:
                try:
                    with i2c_lock:
                        ads.gain = self._ws_gain
                        chan_diff = AnalogIn(ads, 0, 1)
                        chan_var  = AnalogIn(ads, 2)
                        self.ws_voltage_diff = chan_diff.voltage
                        self.ws_raw_diff     = chan_diff.value
                        self.ws_voltage_var  = chan_var.voltage
                except Exception as e:
                    log.error("Wheatstone — erreur lecture : %s", e)

            # -- Angle volant (gain faible) --
            if self._st_enabled:
                try:
                    with i2c_lock:
                        ads.gain = self._st_gain
                        chan = AnalogIn(ads, getattr(ADS, f"P{self._st_channel}"))
                        voltage = chan.voltage
                    self.st_voltage = voltage
                    self.st_angle   = self._voltage_to_angle(voltage)
                except Exception as e:
                    log.error("Angle volant — erreur lecture : %s", e)

            self._stop_event.wait(timeout=self._sample_rate)

    def _run_simulation(self):
        """Valeurs factices quand la librairie materielle est absente."""
        if self._ws_enabled:
            self.ws_ready = True
        if self._st_enabled:
            self.st_ready = True
        while not self._stop_event.is_set():
            if self._ws_enabled:
                self.ws_voltage_diff = 0.012
                self.ws_voltage_var  = 1.65
                self.ws_raw_diff     = 150
            if self._st_enabled:
                self.st_voltage = 1.65
                self.st_angle   = 0.0
            self._stop_event.wait(timeout=self._sample_rate)
