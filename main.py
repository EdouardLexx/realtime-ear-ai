import time
import threading
import queue

from app_logger import setup_logging, get_logger
from config_loader import load_config
from db            import start_trajet, insert_mesure, end_trajet
from CamLive       import run_detection
from heart_rate    import HeartRateMonitor
from vibrator      import Vibrator
from ads_reader    import ADS1115Reader


def _etat(actif: bool, erreur: bool = False) -> str:
    if erreur:
        return "ERREUR"
    return "OK" if actif else "DESACTIVE"


def main():
    # -- Config + logging ----------------------------------------------------
    cfg = load_config("config.xml")
    setup_logging(cfg.log_level)
    log = get_logger(__name__)

    log.info("=" * 60)
    log.info("DEMARRAGE - Detection attention conducteur")
    log.info("=" * 60)
    log.info("Config        : conducteur=%d | niveau log=%s", cfg.id_conducteur, cfg.log_level)

    # -- Capteur cardiaque ---------------------------------------------------
    hr_monitor = None
    hr_error = False
    if cfg.hr_enabled:
        try:
            hr_monitor = HeartRateMonitor(
                i2c_bus = cfg.hr_i2c_bus,
                int_pin = cfg.hr_int_pin,
            )
            hr_monitor.start()
        except Exception as e:
            hr_error = True
            log.error("Capteur cardiaque desactive : %s", e)
    log.info("Cardiaque     : %s", _etat(cfg.hr_enabled and hr_monitor is not None, hr_error))

    # -- Vibreur -------------------------------------------------------------
    vibrator = None
    vib_error = False
    if cfg.vib_enabled:
        try:
            vibrator = Vibrator(gpio_pin=cfg.vib_gpio_pin)
        except Exception as e:
            vib_error = True
            log.error("Vibreur desactive : %s", e)
    log.info("Vibreur       : %s (GPIO%d)", _etat(cfg.vib_enabled and vibrator is not None, vib_error), cfg.vib_gpio_pin)

    # -- ADS1115 (Wheatstone + angle volant) ---------------------------------
    ads_reader = None
    ads_error = False
    if cfg.ws_enabled or cfg.st_enabled:
        try:
            ads_reader = ADS1115Reader(
                address     = cfg.ws_i2c_address,
                ws_enabled  = cfg.ws_enabled,
                ws_gain     = cfg.ws_gain,
                st_enabled  = cfg.st_enabled,
                st_gain     = cfg.st_gain,
                st_channel  = cfg.st_channel,
                sample_rate = cfg.ws_sample_rate,
                v_min       = cfg.st_v_min,
                v_max       = cfg.st_v_max,
                angle_min   = cfg.st_angle_min,
                angle_max   = cfg.st_angle_max,
            )
            ads_reader.start()
        except Exception as e:
            ads_error = True
            log.error("ADS1115 desactive : %s", e)
    log.info("Wheatstone    : %s", _etat(cfg.ws_enabled and ads_reader is not None, ads_error))
    log.info("Angle volant  : %s", _etat(cfg.st_enabled and ads_reader is not None, ads_error))

    # ── Trajet BDD ───────────────────────────────────────────────────────────
    trajet_id  = start_trajet(cfg)
    start_time = time.time()
    log.info("=" * 60)

    # -- Etat DB (partage avec le thread d'ecriture) -------------------------
    db_state = {"ok": True}

    # -- Thread BDD ----------------------------------------------------------
    db_queue = queue.Queue()

    def db_worker():
        while True:
            item = db_queue.get()
            if item is None:
                break
            t_ms, ouv, alerte_vis, bpm, alerte_bpm, ws_volt, angle = item
            try:
                insert_mesure(
                    cfg              = cfg,
                    id_trajet        = trajet_id,
                    temps_ms         = t_ms,
                    ouverture_oeil   = ouv,
                    alerte_visuelle  = alerte_vis,
                    rythme_cardiaque = bpm,
                    alerte_sonore    = alerte_bpm,
                    angle_volant     = angle,
                )
                db_state["ok"] = True
            except Exception as e:
                db_state["ok"] = False
                log.error("Ecriture BDD echouee : %s", e)
            finally:
                db_queue.task_done()

    worker = threading.Thread(target=db_worker, daemon=True, name="DB-Worker")
    worker.start()

    # -- Etat vibreur (evite de relancer si deja actif) ----------------------
    vibrator_running = [False]

    # -- Callback cam -> tout le reste ---------------------------------------
    last_send = [0.0]

    def on_mesure(temps_ms: int, ouverture_oeil: float, alerte_visuelle: int):
        now = time.time()

        # -- Vibreur : declenche des l'alerte yeux, independamment du throttle BDD --
        if vibrator is not None:
            if alerte_visuelle == 1:
                if not vibrator_running[0]:
                    vibrator_running[0] = True
                    log.warning("Conducteur endormi -> vibreur declenche !")
                    vibrator.pattern(
                        on   = cfg.vib_pattern_on,
                        off  = cfg.vib_pattern_off,
                        reps = cfg.vib_pattern_reps,
                    )
            else:
                if vibrator_running[0]:
                    vibrator_running[0] = False
                    vibrator.stop()

        # -- Envoi BDD throttle --------------------------------------------------
        if now - last_send[0] < cfg.send_interval:
            return
        last_send[0] = now

        # BPM
        bpm        = 0
        alerte_bpm = 0
        if hr_monitor is not None:
            bpm = int(round(hr_monitor.bpm))
            if hr_monitor.finger_present and bpm > 0:
                if bpm < cfg.hr_alert_low or bpm > cfg.hr_alert_high:
                    alerte_bpm = 1

        # Wheatstone
        ws_volt = 0.0
        if ads_reader is not None and ads_reader.ws_ready:
            ws_volt = ads_reader.ws_voltage_diff

        # Angle volant
        angle = 0.0
        if ads_reader is not None and ads_reader.st_ready:
            angle = ads_reader.st_angle

        db_queue.put((temps_ms, ouverture_oeil, alerte_visuelle, bpm, alerte_bpm, ws_volt, angle))

        # -- Ligne d'etat consolidee --------------------------------------------
        t_s       = temps_ms / 1000.0
        s_bpm     = f"{bpm}" if hr_monitor is not None else "--"
        s_angle   = f"{angle:+.1f}" if (ads_reader is not None and ads_reader.st_ready) else "--"
        s_ws      = f"{ws_volt:.4f}V" if (ads_reader is not None and ads_reader.ws_ready) else "--"
        s_vibreur = "ON" if vibrator_running[0] else "OFF"
        s_db      = "OK" if db_state["ok"] else "ERREUR"
        alertes   = []
        if alerte_visuelle:
            alertes.append("YEUX")
        if alerte_bpm:
            alertes.append("BPM")
        s_alerte = ",".join(alertes) if alertes else "-"

        log.info(
            "[t=%6.1fs] yeux=%5.1f%% | BPM=%3s | angle=%7s | WS=%9s | vibreur=%-3s | alerte=%-8s | DB=%s",
            t_s, ouverture_oeil, s_bpm, s_angle, s_ws, s_vibreur, s_alerte, s_db,
        )

    # -- Lancement camera ----------------------------------------------------
    try:
        run_detection(cfg=cfg, on_mesure=on_mesure, start_time_ref=start_time)
    finally:
        log.info("Arret en cours...")
        if vibrator is not None:
            vibrator.stop()
            vibrator.cleanup()
        if hr_monitor is not None:
            hr_monitor.stop()
        if ads_reader is not None:
            ads_reader.stop()
        db_queue.put(None)
        worker.join()
        end_trajet(cfg, trajet_id)
        log.info("Arret propre.")


if __name__ == "__main__":
    main()
