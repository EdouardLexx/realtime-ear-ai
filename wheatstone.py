"""
wheatstone.py
-------------
Lecture du pont de Wheatstone via ADS1115 (I2C).
Utilise un verrou I2C partagé avec heart_rate.py.
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

DEFAULT_GAIN = 4


class WheatstoneReader:
    def __init__(self, i2c_bus: int = 1, address: int = 0x48,
                 gain: int = DEFAULT_GAIN, sample_rate: float = 0.1):
        self._address     = address
        self._gain        = gain
        self._sample_rate = sample_rate
        self._stop_event  = threading.Event()
        self._thread      = None

        self.voltage_diff: float = 0.0
        self.voltage_var:  float = 0.0
        self.raw_diff:     int   = 0
        self.ready:        bool  = False

        if not ADS_AVAILABLE:
            print("⚠️  adafruit-ads1x15 non installé — ADS1115 simulé")

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="Wheatstone-Reader"
        )
        self._thread.start()
        print(f"⚖️  WheatstoneReader démarré (addr=0x{self._address:02X}, gain={self._gain})")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        print("⚖️  WheatstoneReader arrêté.")

    def _run(self):
        if not ADS_AVAILABLE:
            while not self._stop_event.is_set():
                self.voltage_diff = 0.012
                self.voltage_var  = 1.65
                self.raw_diff     = 150
                self.ready        = True
                self._stop_event.wait(timeout=self._sample_rate)
            return

        try:
            with i2c_lock:
                i2c = busio.I2C(board.SCL, board.SDA)
                ads = ADS.ADS1115(i2c, address=self._address, gain=self._gain)
                chan_diff = AnalogIn(ads, 0, 1)
                chan_var  = AnalogIn(ads, 2)

            print("✅ ADS1115 détecté")
            self.ready = True

            while not self._stop_event.is_set():
                try:
                    with i2c_lock:
                        self.voltage_diff = chan_diff.voltage
                        self.raw_diff     = chan_diff.value
                        self.voltage_var  = chan_var.voltage
                except Exception as e:
                    print(f"[ADS1115] Erreur lecture : {e}")

                self._stop_event.wait(timeout=self._sample_rate)

        except Exception as e:
            print(f"❌ ADS1115 non initialisé : {e}")