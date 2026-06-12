"""
heart_rate.py - Version DEBUG
"""

import time
import threading
import numpy as np
from i2c_lock import i2c_lock

try:
    from scipy.signal import find_peaks, butter, filtfilt
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("⚠️  scipy non installé, calcul BPM dégradé")

MAX30102_ADDRESS  = 0x57
REG_FIFO_WR_PTR  = 0x04
REG_OVF_COUNTER  = 0x05
REG_FIFO_RD_PTR  = 0x06
REG_FIFO_DATA    = 0x07
REG_FIFO_CONFIG  = 0x08
REG_MODE_CONFIG  = 0x09
REG_SPO2_CONFIG  = 0x0A
REG_LED1_PA      = 0x0C
REG_LED2_PA      = 0x0D
REG_PART_ID      = 0xFF

SAMPLE_RATE      = 100
FIFO_SAMPLES     = 200
BPM_BUFFER_SIZE  = 5
FINGER_THRESHOLD = 50000


class MAX30102Driver:
    def __init__(self, i2c_bus: int = 1):
        try:
            import smbus2
            self._bus = smbus2.SMBus(i2c_bus)
        except ImportError:
            raise SystemExit("❌ smbus2 non installé")

        self._addr = MAX30102_ADDRESS
        part_id = self._read_byte(REG_PART_ID)
        if part_id != 0x15:
            raise RuntimeError(f"MAX30102 non détecté (part_id=0x{part_id:02X})")
        self._init_sensor()

    def _read_byte(self, reg):
        with i2c_lock:
            return self._bus.read_byte_data(self._addr, reg)

    def _write_byte(self, reg, value):
        with i2c_lock:
            self._bus.write_byte_data(self._addr, reg, value)

    def _init_sensor(self):
        self._write_byte(REG_MODE_CONFIG, 0x40)
        time.sleep(0.1)
        time.sleep(0.2)
        self._write_byte(REG_FIFO_CONFIG, 0x4F)
        time.sleep(0.2)
        self._write_byte(REG_MODE_CONFIG, 0x02)
        time.sleep(0.2)
        self._write_byte(REG_SPO2_CONFIG, 0x27)
        time.sleep(0.2)
        self._write_byte(REG_LED1_PA, 0x24)
        time.sleep(0.2)
        self._write_byte(REG_LED2_PA, 0x24)
        time.sleep(0.2)
        self._write_byte(REG_FIFO_WR_PTR, 0x00)
        self._write_byte(REG_OVF_COUNTER, 0x00)
        self._write_byte(REG_FIFO_RD_PTR, 0x00)
        time.sleep(0.5)
        print("✅ MAX30102 initialisé")

    def get_data_count(self):
        with i2c_lock:
            wr = self._bus.read_byte_data(self._addr, REG_FIFO_WR_PTR)
            rd = self._bus.read_byte_data(self._addr, REG_FIFO_RD_PTR)
        return (wr - rd) & 0x1F

    def read_fifo(self):
        with i2c_lock:
            raw = self._bus.read_i2c_block_data(self._addr, REG_FIFO_DATA, 6)
        red = ((raw[0] & 0x03) << 16) | (raw[1] << 8) | raw[2]
        ir  = ((raw[3] & 0x03) << 16) | (raw[4] << 8) | raw[5]
        return red, ir

    def close(self):
        self._bus.close()


def _bandpass_filter(signal, fs=100, low=0.7, high=3.5):
    nyq = fs / 2.0
    b, a = butter(2, [low / nyq, high / nyq], btype='band')
    return filtfilt(b, a, signal)


def _calc_bpm(ir_data):
    if len(ir_data) < FIFO_SAMPLES:
        return 0.0, False

    signal = np.array(ir_data[-FIFO_SAMPLES:], dtype=float)
    mean_ir = np.mean(signal)

    print(f"[HR DEBUG] samples={len(ir_data)} | mean_IR={mean_ir:.0f} | doigt={'OUI' if mean_ir >= FINGER_THRESHOLD else 'NON'}")

    if mean_ir < FINGER_THRESHOLD:
        return 0.0, False

    signal = (signal - np.mean(signal)) / (np.std(signal) + 1e-9)

    if SCIPY_AVAILABLE:
        try:
            filtered = _bandpass_filter(signal, fs=SAMPLE_RATE)
            peaks, props = find_peaks(filtered, distance=27, prominence=0.3)
            print(f"[HR DEBUG] pics trouvés={len(peaks)}")
        except Exception as e:
            print(f"[HR DEBUG] Erreur filtre : {e}")
            peaks = []
    else:
        peaks = np.where(np.diff(np.sign(signal)) > 0)[0]
        print(f"[HR DEBUG] passages zéro={len(peaks)}")

    if len(peaks) < 2:
        print("[HR DEBUG] Pas assez de pics pour calculer BPM")
        return 0.0, False

    intervals     = np.diff(peaks) / SAMPLE_RATE
    mean_interval = np.mean(intervals)
    bpm           = 60.0 / mean_interval
    print(f"[HR DEBUG] intervalle moyen={mean_interval:.3f}s → BPM brut={bpm:.1f}")

    if not (40 <= bpm <= 200):
        print(f"[HR DEBUG] BPM hors plage (40-200), ignoré")
        return 0.0, False

    return bpm, True


class HeartRateMonitor:
    def __init__(self, i2c_bus: int = 1, int_pin: int = 23):
        self._i2c_bus    = i2c_bus
        self._thread     = None
        self._stop_event = threading.Event()
        self.bpm: float           = 0.0
        self.finger_present: bool = False

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="HR-Monitor")
        self._thread.start()
        print(f"💓 HeartRateMonitor démarré (I2C bus={self._i2c_bus})")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        print("💓 HeartRateMonitor arrêté.")

    def _run(self):
        try:
            driver = MAX30102Driver(i2c_bus=self._i2c_bus)
        except Exception as e:
            print(f"❌ Impossible d'initialiser le MAX30102 : {e}")
            return

        ir_data    = []
        bpm_buffer = []

        try:
            while not self._stop_event.is_set():
                try:
                    count = driver.get_data_count()
                except OSError as e:
                    print(f'[HR] Erreur get_data_count: {e}')
                    time.sleep(0.5)
                    continue
                if count == 0:
                    time.sleep(0.02)
                    continue

                while count > 0:
                    try:
                        _, ir = driver.read_fifo()
                        ir_data.append(ir)
                        count -= 1
                    except Exception as e:
                        print(f"[HR DEBUG] Erreur read_fifo : {e}")
                        break

                if len(ir_data) > FIFO_SAMPLES * 3:
                    ir_data = ir_data[-FIFO_SAMPLES:]

                if len(ir_data) >= 10:
                    self.finger_present = np.mean(ir_data[-10:]) >= FINGER_THRESHOLD

                if not self.finger_present:
                    self.bpm = 0.0
                    bpm_buffer.clear()
                    continue

                if len(ir_data) >= FIFO_SAMPLES:
                    bpm, valid = _calc_bpm(ir_data)
                    if valid:
                        bpm_buffer.append(bpm)
                        if len(bpm_buffer) > BPM_BUFFER_SIZE:
                            bpm_buffer.pop(0)
                        self.bpm = float(np.mean(bpm_buffer))
                        print(f"💓 BPM = {self.bpm:.0f}")

        finally:
            driver.close()