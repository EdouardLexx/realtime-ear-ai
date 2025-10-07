import cv2
import numpy as np
import mediapipe as mp
import time
import sys
import pygame  # pour le son

# ---------- Configuration ----------
left_eye_landmarks  = [362, 385, 387, 263, 373, 380]
right_eye_landmarks = [33, 160, 158, 133, 153, 144]

MAX_EAR = 0.35
CLOSED_EYE_THRESHOLD = 0.15
PRINT_INTERVAL = 0.5   # secondes entre impressions terminal
ALERT_DURATION = 2.0   # secondes avant alerte

ALERT_SOUND_PATH = "/home/edouard/Documents/Eyes_recognition/Sounds/BMW Warning Chime.mp3"

# ---------- Initialiser pygame pour le son ----------
pygame.mixer.init()

def start_alert_sound():
    """Joue le son en boucle"""
    try:
        if not pygame.mixer.music.get_busy():  # éviter de relancer si déjà en cours
            pygame.mixer.music.load(ALERT_SOUND_PATH)
            pygame.mixer.music.play(-1)  # boucle infinie
    except Exception as e:
        print(f"Erreur lecture son: {e}")

def stop_alert_sound():
    """Arrête le son"""
    pygame.mixer.music.stop()

# ---------- Fonctions utilitaires ----------
def denormalize_landmark(landmark, w, h):
    x = int(landmark.x * w)
    y = int(landmark.y * h)
    x = max(0, min(w - 1, x))
    y = max(0, min(h - 1, y))
    return (x, y)

def eye_aspect_ratio(eye_pts):
    A = np.linalg.norm(np.array(eye_pts[1]) - np.array(eye_pts[5]))
    B = np.linalg.norm(np.array(eye_pts[2]) - np.array(eye_pts[4]))
    C = np.linalg.norm(np.array(eye_pts[0]) - np.array(eye_pts[3]))
    ear = (A + B) / (2.0 * C) if C != 0 else 0.0
    return ear, A, B, C

# ---------- Ouvrir la webcam ----------
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("❌ Erreur : webcam inaccessible")
    sys.exit(1)
else:
    print("✅ Webcam détectée")

cv2.namedWindow("Détection ouverture yeux (Live) - q pour quitter", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Détection ouverture yeux (Live) - q pour quitter", 1000, 700)

mp_facemesh = mp.solutions.face_mesh
last_print = 0.0
closed_start_time = None

with mp_facemesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
) as face_mesh:
    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("Aucun frame reçu — arrêt.", file=sys.stderr)
                break


            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = face_mesh.process(rgb)
            rgb.flags.writeable = True

            left_percent = right_percent = None

            if results.multi_face_landmarks:
                face_landmarks = results.multi_face_landmarks[0]

                # récupérer points en pixels
                left_pts  = [denormalize_landmark(face_landmarks.landmark[i], w, h) for i in left_eye_landmarks]
                right_pts = [denormalize_landmark(face_landmarks.landmark[i], w, h) for i in right_eye_landmarks]

                # dessiner et numéroter
                for i, p in enumerate(left_pts, start=1):
                    cv2.circle(frame, p, 2, (0, 255, 0), -1)
                    cv2.putText(frame, str(i), (p[0]+3, p[1]-3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,255), 1)
                for i, p in enumerate(right_pts, start=1):
                    cv2.circle(frame, p, 2, (0, 255, 0), -1)
                    cv2.putText(frame, str(i), (p[0]+3, p[1]-3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,255), 1)

                # calcul EAR et pourcentages
                left_ear, _, _, _ = eye_aspect_ratio(left_pts)
                right_ear, _, _, _ = eye_aspect_ratio(right_pts)
                left_percent  = 0.0 if left_ear < CLOSED_EYE_THRESHOLD else min(left_ear / MAX_EAR * 100, 100)
                right_percent = 0.0 if right_ear < CLOSED_EYE_THRESHOLD else min(right_ear / MAX_EAR * 100, 100)

                # Gestion alerte yeux fermés > 2 secondes
                if left_percent == 0.0 and right_percent == 0.0:
                    if closed_start_time is None:
                        closed_start_time = time.time()
                    elif time.time() - closed_start_time >= ALERT_DURATION:
                        print("Alerte : yeux fermés depuis plus de 2 secondes !")
                        start_alert_sound()  # joue en boucle

                        # 🔴 Ajout affichage texte rouge sur l’écran
                        cv2.putText(
                            frame,
                            "YEUX FERMES !",
                            (int(w/6), int(h/2)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.5,
                            (0, 0, 255),
                            3
                        )
                else:
                    closed_start_time = None
                    stop_alert_sound()  # coupe le son dès que les yeux s’ouvrent

                # couleur texte
                color_left  = (0,0,255) if left_percent == 0.0 else (0,255,0)
                color_right = (0,0,255) if right_percent == 0.0 else (0,255,0)

                cv2.putText(frame, f"D: {left_percent:.1f}%", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, color_left, 2)
                cv2.putText(frame, f"G: {right_percent:.1f}%", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, color_right, 2)

            # affichage
            cv2.imshow("Détection ouverture yeux (Live) - q pour quitter", frame)

            # impressions terminal
            now = time.time()
            if now - last_print >= PRINT_INTERVAL:
                if left_percent is not None and right_percent is not None:
                    print(f"Oeil droit: EAR={left_ear:.3f}  %={left_percent:.1f} | Oeil gauche: EAR={right_ear:.3f}  %={right_percent:.1f}")
                else:
                    print("Aucun visage détecté")
                last_print = now

            # quitter
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("Interrompu par l'utilisateur.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        stop_alert_sound()
