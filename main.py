import time
import threading
import queue
from config_loader import load_config
from db            import start_trajet, insert_mesure, end_trajet
from CamLive       import run_detection
from heart_rate    import HeartRateMonitor
from vibrator      import Vibrator
from wheatstone    import WheatstoneReader
from steering_angle import SteeringAngleReader


def main():
    # ── Config ──────────────────────────────────────────────────────────────
    cfg = load_config("config.xml")
    print(
        f"⚙️  Config chargée — conducteur={cfg.id_conducteur} | "
        f"son={'ON' if cfg.sound_enabled else 'OFF'} | "
        f"cardiaque={'ON' if cfg.hr_enabled else 'OFF'} | "
        f"vibreur={'ON' if cfg.vib_enabled else 'OFF'} | "
        f"wheatstone={'ON' if cfg.ws_enabled else 'OFF'}"
    )

    # ── Capteur cardiaque ────────────────────────────────────────────────────
    hr_monitor = None
    if cfg.hr_enabled:
        try:
            hr_monitor = HeartRateMonitor(
                i2c_bus = cfg.hr_i2c_bus,
                int_pin = cfg.hr_int_pin,
            )
            hr_monitor.start()
        except Exception as e:
            print(f"Capteur cardiaque désactivé : {e}")

    # ── Vibreur ──────────────────────────────────────────────────────────────
    vibrator = None
    if cfg.vib_enabled:
        try:
            vibrator = Vibrator(
                gpio_pin  = cfg.vib_gpio_pin,
                frequency = cfg.vib_pwm_freq,
            )
        except Exception as e:
            print(f"Vibreur désactivé : {e}")

    # ── Pont de Wheatstone ───────────────────────────────────────────────────
    ws_reader = None
    if cfg.ws_enabled:
        try:
            ws_reader = WheatstoneReader(
                address     = cfg.ws_i2c_address,
                gain        = cfg.ws_gain,
                sample_rate = cfg.ws_sample_rate,
            )
            ws_reader.start()
        except Exception as e:
            print(f"WheatstoneReader désactivé : {e}")

    # ── Angle volant ─────────────────────────────────────────────────────────
    steering_reader = None
    if cfg.st_enabled:
        try:
            steering_reader = SteeringAngleReader(
                i2c_bus     = 1,
                address     = cfg.st_i2c_address,
                gain        = cfg.st_gain,
                channel     = cfg.st_channel,
                sample_rate = cfg.st_sample_rate,
                v_min       = cfg.st_v_min,
                v_max       = cfg.st_v_max,
                angle_min   = cfg.st_angle_min,
                angle_max   = cfg.st_angle_max,
            )
            steering_reader.start()
        except Exception as e:
            print(f"SteeringAngleReader désactivé : {e}")

    # ── Trajet BDD ───────────────────────────────────────────────────────────
    trajet_id  = start_trajet(cfg)
    start_time = time.time()

    # ── Thread BDD ───────────────────────────────────────────────────────────
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
                s_yeux  = "ALERTE" if alerte_vis else "👁️ OK"
                s_coeur = f"{bpm} BPM{'⚠️' if alerte_bpm else ''}"
                s_ws    = f"  {ws_volt:.4f}V"
                s_angle = f"  🎯 {angle:.1f}°"
                print(f"[DB] t={t_ms}ms | œil={ouv:.1f}% | {s_yeux} | {s_coeur} | {s_ws} | {s_angle}")
            except Exception as e:
                print(f"[DB] ⚠️  Erreur : {e}")
            finally:
                db_queue.task_done()

    worker = threading.Thread(target=db_worker, daemon=True, name="DB-Worker")
    worker.start()

    # ── État vibreur (évite de relancer si déjà actif) ───────────────────────
    vibrator_running = [False]

    # ── Callback cam → tout le reste ─────────────────────────────────────────
    last_send = [0.0]

    def on_mesure(temps_ms: int, ouverture_oeil: float, alerte_visuelle: int):
        now = time.time()

        # ── Vibreur : déclenché dès l'alerte yeux, indépendamment du throttle BDD ──
        if vibrator is not None:
            if alerte_visuelle == 1:
                if not vibrator_running[0]:
                    vibrator_running[0] = True
                    print("📳 Vibreur déclenché — conducteur endormi !")
                    vibrator.pattern(
                        on   = cfg.vib_pattern_on,
                        off  = cfg.vib_pattern_off,
                        reps = cfg.vib_pattern_reps,
                        duty = cfg.vib_duty,
                    )
            else:
                if vibrator_running[0]:
                    vibrator_running[0] = False
                    vibrator.stop()

        # ── Envoi BDD throttlé ───────────────────────────────────────────────
        if now - last_send[0] < cfg.send_interval:
            return
        last_send[0] = now

        # BPM
        bpm       = 0
        alerte_bpm = 0
        if hr_monitor is not None:
            bpm = int(round(hr_monitor.bpm))
            if hr_monitor.finger_present and bpm > 0:
                if bpm < cfg.hr_alert_low or bpm > cfg.hr_alert_high:
                    alerte_bpm = 1

        # Wheatstone
        ws_volt = 0.0
        if ws_reader is not None and ws_reader.ready:
            ws_volt = ws_reader.voltage_diff

        # Angle volant
        angle = 0.0
        if steering_reader is not None and steering_reader.ready:
            angle = steering_reader.angle

        db_queue.put((temps_ms, ouverture_oeil, alerte_visuelle, bpm, alerte_bpm, ws_volt, angle))

    # ── Lancement caméra ─────────────────────────────────────────────────────
    try:
        run_detection(cfg=cfg, on_mesure=on_mesure, start_time_ref=start_time)
    finally:
        print("Arrêt en cours...")
        if vibrator is not None:
            vibrator.stop()
            vibrator.cleanup()
        if hr_monitor is not None:
            hr_monitor.stop()
        if ws_reader is not None:
            ws_reader.stop()
        if steering_reader is not None:
            steering_reader.stop()
        db_queue.put(None)
        worker.join()
        end_trajet(cfg, trajet_id)
        print("Arrêt propre.")


if __name__ == "__main__":
    main()
