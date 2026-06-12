"""
vibrator.py
-----------
Commande du vibreur via transistor PN2222A sur GPIO Raspberry Pi.
Utilise lgpio (compatible Raspberry Pi 5).
"""

import threading
import time

try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False


class Vibrator:
    """
    Contrôle le vibreur en ON/OFF simulé PWM (compatible Pi 5).

    Modes disponibles :
      - pulse(duration, duty)  : vibration unique pendant `duration` secondes
      - pattern(on, off, reps) : schéma on/off répété `reps` fois
      - stop()                 : arrêt immédiat
    """

    def __init__(self, gpio_pin: int = 12, frequency: int = 100):
        self._pin        = gpio_pin
        self._freq       = frequency
        self._handle     = None
        self._lock       = threading.Lock()
        self._active_thread = None
        self._stop_event = threading.Event()

        if not LGPIO_AVAILABLE:
            print("⚠️  lgpio non disponible — vibreur simulé (logs uniquement)")
            return

        try:
            self._handle = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(self._handle, self._pin)
            lgpio.gpio_write(self._handle, self._pin, 0)
            print(f"🔧 Vibreur initialisé sur GPIO{self._pin} (lgpio)")
        except Exception as e:
            print(f"⚠️  Vibreur non initialisé : {e}")
            self._handle = None

    # ── API publique ─────────────────────────────────────────────────────────

    def pulse(self, duration: float = 1.0, duty: int = 80):
        """Vibre pendant `duration` secondes."""
        self._launch(self._do_pulse, duration, duty)

    def pattern(self, on: float = 0.3, off: float = 0.2, reps: int = 5, duty: int = 80):
        """Schéma répété : vibre `on`s, pause `off`s, × `reps`."""
        self._launch(self._do_pattern, on, off, reps, duty)

    def stop(self):
        """Arrête immédiatement toute vibration."""
        self._stop_event.set()
        self._set_on(False)

    def cleanup(self):
        self.stop()
        if self._handle is not None:
            try:
                lgpio.gpiochip_close(self._handle)
            except Exception:
                pass

    # ── Internals ────────────────────────────────────────────────────────────

    def _launch(self, fn, *args):
        self._stop_event.set()
        if self._active_thread and self._active_thread.is_alive():
            self._active_thread.join(timeout=1.0)
        self._stop_event.clear()
        self._active_thread = threading.Thread(target=fn, args=args, daemon=True)
        self._active_thread.start()

    def _set_on(self, on: bool):
        if self._handle is not None:
            try:
                lgpio.gpio_write(self._handle, self._pin, 1 if on else 0)
            except Exception:
                pass
        else:
            print(f"[VIBREUR SIM] {'ON' if on else 'OFF'}")

    def _do_pulse(self, duration: float, duty: int):
        self._set_on(True)
        self._stop_event.wait(timeout=duration)
        self._set_on(False)

    def _do_pattern(self, on: float, off: float, reps: int, duty: int):
        for _ in range(reps):
            if self._stop_event.is_set():
                break
            self._set_on(True)
            self._stop_event.wait(timeout=on)
            if self._stop_event.is_set():
                break
            self._set_on(False)
            self._stop_event.wait(timeout=off)
        self._set_on(False)