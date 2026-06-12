"""
vibrator.py
-----------
Commande du vibreur via transistor PN2222A sur GPIO du Raspberry Pi.
Utilise lgpio.

Le pilotage est en TOUT-OU-RIEN (ON/OFF) : le vibreur est soit alimente,
soit eteint. Il n'y a pas de reglage d'intensite (pas de PWM).
"""

import threading

from app_logger import get_logger

log = get_logger(__name__)

try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False


class Vibrator:
    """
    Controle le vibreur en TOUT-OU-RIEN (ON/OFF).

    Modes disponibles :
      - pulse(duration)        : vibration unique pendant `duration` secondes
      - pattern(on, off, reps) : schema on/off repete `reps` fois
      - stop()                 : arret immediat
    """

    def __init__(self, gpio_pin: int = 12):
        self._pin           = gpio_pin
        self._handle        = None
        self._active_thread = None
        self._stop_event    = threading.Event()

        if not LGPIO_AVAILABLE:
            log.warning("lgpio non disponible — vibreur simule (logs uniquement)")
            return

        try:
            self._handle = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(self._handle, self._pin)
            lgpio.gpio_write(self._handle, self._pin, 0)
            log.info("Vibreur initialise sur GPIO%d", self._pin)
        except Exception as e:
            log.warning("Vibreur non initialise : %s", e)
            self._handle = None

    # ── API publique ─────────────────────────────────────────────────────────

    def pulse(self, duration: float = 1.0):
        """Vibre pendant `duration` secondes."""
        self._launch(self._do_pulse, duration)

    def pattern(self, on: float = 0.3, off: float = 0.2, reps: int = 5):
        """Schema repete : vibre `on`s, pause `off`s, x `reps`."""
        self._launch(self._do_pattern, on, off, reps)

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
            log.debug("[SIMULATION] vibreur %s", "ON" if on else "OFF")

    def _do_pulse(self, duration: float):
        self._set_on(True)
        self._stop_event.wait(timeout=duration)
        self._set_on(False)

    def _do_pattern(self, on: float, off: float, reps: int):
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