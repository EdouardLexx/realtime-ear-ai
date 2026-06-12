"""
steering_angle.py
------------------
Lecture de l'angle du volant via un potentiomètre (0-10K)
branché sur l'ADS1115 (canal A3 par défaut).
Utilise le verrou I2C partagé avec heart_rate.py / wheatstone.py.
"""

import time
import threading
from i2c_lock import i2c_lock

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    ADS_AVAILABLE = True
except ImportError:
    ADS_AVAILABLE = False

DEFAULT_GAIN = 1  # 1 = ±4.096V, adapté pour une alim 3.3V sur le potar


class SteeringAngleReader:
    """
    Lit la tension d'un potentiomètre (course 0-10K) sur l'ADS1115
    et la convertit en angle (degrés) via une calibration linéaire.

    Calibration :
        angle = angle_min + (V - v_min) * (angle_max - angle_min) / (v_max - v_min)

    v_min / v_max = tensions mesurées aux butées (ou aux positions de référence)
    angle_min / angle_max = angles correspondants (ex: -450° / +450°)
    """

    def __init__(
        self,
        i2c_bus:      int   = 1,
        address:      int   = 0x48,
        gain:         int   = DEFAULT_GAIN,
        channel:      int   = 3,
        sample_rate:  float = 0.1,
        v_min:        float = 0.0,
        v_max:        float = 3.3,
        angle_min:    float = -450.0,
        angle_max:    float = 450.0,
    ):
        self._address     = address
        self._gain        = gain
        self._channel     = channel
        self._sample_rate = sample_rate

        self._v_min     = v_min
        self._v_max     = v_max
        self._angle_min = angle_min
        self._angle_max = angle_max

        self._stop_event = threading.Event()
        self._thread     = None

        self.voltage: float = 0.0
        self.angle:   float = 0.0
        self.ready:   bool  = False

        if not ADS_AVAILABLE:
            print("⚠️  adafruit-ads1x15 non installé — SteeringAngleReader simulé")

    # ── API publique ─────────────────────────────────────────────────────────

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="SteeringAngle-Reader"
        )
        self._thread.start()
        print(f"🎯 SteeringAngleReader démarré (addr=0x{self._address:02X}, canal A{self._channel})")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        print("🎯 SteeringAngleReader arrêté.")

    def set_calibration(self, v_min: float, v_max: float, angle_min: float, angle_max: float):
        """Permet de mettre à jour la calibration à chaud."""
        self._v_min     = v_min
        self._v_max     = v_max
        self._angle_min = angle_min
        self._angle_max = angle_max

    # ── Internals ────────────────────────────────────────────────────────────

    def _voltage_to_angle(self, voltage: float) -> float:
        v_range = (self._v_max - self._v_min)
        if v_range == 0:
            return self._angle_min
        ratio = (voltage - self._v_min) / v_range
        ratio = max(0.0, min(1.0, ratio))  # clamp dans la plage calibrée
        return self._angle_min + ratio * (self._angle_max - self._angle_min)

    def _run(self):
        if not ADS_AVAILABLE:
            # Mode simulation : oscille doucement autour de 0°
            t = 0.0
            while not self._stop_event.is_set():
                self.voltage = 1.65
                self.angle   = 0.0
                self.ready   = True
                t += self._sample_rate
                self._stop_event.wait(timeout=self._sample_rate)
            return

        try:
            with i2c_lock:
                i2c  = busio.I2C(board.SCL, board.SDA)
                ads  = ADS.ADS1115(i2c, address=self._address, gain=self._gain)
                chan = AnalogIn(ads, getattr(ADS, f"P{self._channel}"))

            print("✅ ADS1115 (angle volant) détecté")
            self.ready = True

            while not self._stop_event.is_set():
                try:
                    with i2c_lock:
                        voltage = chan.voltage
                    self.voltage = voltage
                    self.angle   = self._voltage_to_angle(voltage)
                except Exception as e:
                    print(f"[ANGLE VOLANT] Erreur lecture : {e}")

                self._stop_event.wait(timeout=self._sample_rate)

        except Exception as e:
            print(f"❌ ADS1115 (angle volant) non initialisé : {e}")