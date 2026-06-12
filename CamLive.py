import cv2
import numpy as np
import mediapipe as mp
import time
from typing import Callable, Optional
from app_logger import get_logger
from config_loader import Config

log = get_logger(__name__)

# Son via pygame (optionnel)
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


# ─────────────────────────────────────────────
# Gestion du son
# ─────────────────────────────────────────────

def _init_sound(cfg: Config) -> bool:
    """Initialise pygame mixer. Retourne True si prêt."""
    if not cfg.sound_enabled:
        return False
    if not PYGAME_AVAILABLE:
        log.warning("pygame non installe — son desactive. (pip install pygame)")
        return False
    try:
        pygame.mixer.init()
        return True
    except Exception as e:
        log.warning("Impossible d'initialiser le son : %s", e)
        return False


def _start_sound(cfg: Config, sound_ready: bool) -> None:
    if not sound_ready:
        return
    try:
        if not pygame.mixer.music.get_busy():
            pygame.mixer.music.load(cfg.sound_file)
            pygame.mixer.music.play(-1)  # boucle infinie
    except Exception as e:
        log.warning("Erreur lecture son : %s", e)


def _stop_sound(sound_ready: bool) -> None:
    if not sound_ready:
        return
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass


# ─────────────────────────────────────────────
# Fonctions utilitaires
# ─────────────────────────────────────────────

def _denormalize(landmark, w: int, h: int):
    x = max(0, min(w - 1, int(landmark.x * w)))
    y = max(0, min(h - 1, int(landmark.y * h)))
    return (x, y)


def _eye_aspect_ratio(eye_pts) -> float:
    A = np.linalg.norm(np.array(eye_pts[1]) - np.array(eye_pts[5]))
    B = np.linalg.norm(np.array(eye_pts[2]) - np.array(eye_pts[4]))
    C = np.linalg.norm(np.array(eye_pts[0]) - np.array(eye_pts[3]))
    return (A + B) / (2.0 * C) if C != 0 else 0.0


def _ear_to_percent(ear: float, cfg: Config) -> float:
    if ear < cfg.closed_threshold:
        return 0.0
    return min(ear / cfg.max_ear * 100, 100.0)


# ─────────────────────────────────────────────
# Landmarks
# ─────────────────────────────────────────────

LEFT_EYE_LANDMARKS  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE_LANDMARKS = [33,  160, 158, 133, 153, 144]


# ─────────────────────────────────────────────
# Boucle principale
# ─────────────────────────────────────────────

def run_detection(
    cfg:             Config,
    on_mesure:       Optional[Callable[[int, float, int], None]] = None,
    start_time_ref:  Optional[float] = None,
) -> None:
    """Lance la détection en temps réel.

    Callback on_mesure(temps_ms, ouverture_oeil_pct, alerte_visuelle)
    """
    t0          = start_time_ref if start_time_ref is not None else time.time()
    sound_ready = _init_sound(cfg)

    # ── Webcam ──
    cap = cv2.VideoCapture(cfg.camera_index)
    if not cap.isOpened():
        log.error("Webcam inaccessible (index=%d)", cfg.camera_index)
        raise SystemExit(1)
    log.info("Webcam detectee (index=%d)", cfg.camera_index)

    win_title = "Détection ouverture yeux (Live) — q pour quitter"
    cv2.namedWindow(win_title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_title, 1000, 700)

    mp_facemesh   = mp.solutions.face_mesh
    last_print    = 0.0
    closed_start  = None
    alerte_active = False

    with mp_facemesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as face_mesh:
        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    log.warning("Aucun frame recu — arret.")
                    break

                frame = cv2.flip(frame, 1)
                h, w, _ = frame.shape
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results = face_mesh.process(rgb)
                rgb.flags.writeable = True

                left_pct = right_pct = None
                alerte_visuelle = 0

                if results.multi_face_landmarks:
                    lm = results.multi_face_landmarks[0]

                    left_pts  = [_denormalize(lm.landmark[i], w, h) for i in LEFT_EYE_LANDMARKS]
                    right_pts = [_denormalize(lm.landmark[i], w, h) for i in RIGHT_EYE_LANDMARKS]

                    # ── Dessin des points ──
                    for pts in (left_pts, right_pts):
                        for idx, p in enumerate(pts, start=1):
                            cv2.circle(frame, p, 2, (0, 255, 0), -1)
                            cv2.putText(frame, str(idx), (p[0]+3, p[1]-3),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

                    # ── EAR → % ──
                    left_ear  = _eye_aspect_ratio(left_pts)
                    right_ear = _eye_aspect_ratio(right_pts)
                    left_pct  = _ear_to_percent(left_ear,  cfg)
                    right_pct = _ear_to_percent(right_ear, cfg)
                    avg_pct   = (left_pct + right_pct) / 2.0

                    # ── Gestion alerte ──
                    yeux_fermes = (left_pct == 0.0 and right_pct == 0.0)

                    if yeux_fermes:
                        if closed_start is None:
                            closed_start = time.time()
                        if time.time() - closed_start >= cfg.alert_duration:
                            alerte_visuelle = 1
                            alerte_active   = True
                            _start_sound(cfg, sound_ready)
                            cv2.putText(
                                frame, "YEUX FERMES !",
                                (int(w / 6), int(h / 2)),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3,
                            )
                    else:
                        if alerte_active:
                            log.info("Yeux rouverts — alerte levee.")
                            alerte_active = False
                            _stop_sound(sound_ready)
                        closed_start = None

                    # ── Texte overlay ──
                    c_left  = (0, 0, 255) if left_pct  == 0.0 else (0, 255, 0)
                    c_right = (0, 0, 255) if right_pct == 0.0 else (0, 255, 0)
                    cv2.putText(frame, f"D: {left_pct:.1f}%",  (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, c_left,  2)
                    cv2.putText(frame, f"G: {right_pct:.1f}%", (10, 70),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, c_right, 2)

                    # ── Callback BDD ──
                    if on_mesure is not None:
                        temps_ms = int((time.time() - t0) * 1000)
                        on_mesure(temps_ms, avg_pct, alerte_visuelle)

                # ── Affichage ──
                cv2.imshow(win_title, frame)

                # ── Log terminal ──
                now = time.time()
                if now - last_print >= cfg.print_interval:
                    if left_pct is not None:
                        log.debug(
                            "Oeil droit: EAR=%.3f %%=%.1f | Oeil gauche: EAR=%.3f %%=%.1f | Alerte=%d",
                            left_ear, left_pct, right_ear, right_pct, alerte_visuelle
                        )
                    else:
                        log.debug("Aucun visage detecte")
                    last_print = now

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        except KeyboardInterrupt:
            log.info("Interrompu par l'utilisateur.")
        finally:
            _stop_sound(sound_ready)
            cap.release()
            cv2.destroyAllWindows()
