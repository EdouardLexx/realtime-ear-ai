import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class Config:
    # Journalisation
    log_level:         str

    # Conducteur
    id_conducteur:     int

    # Base de données
    db_host:           str
    db_port:           int
    db_user:           str
    db_password:       str
    db_name:           str

    # Détection yeux
    camera_index:      int
    max_ear:           float
    closed_threshold:  float
    alert_duration:    float
    print_interval:    float

    # Enregistrement
    send_interval:     float

    # Son
    sound_enabled:     bool
    sound_file:        str

    # Capteur cardiaque
    hr_enabled:        bool
    hr_i2c_bus:        int
    hr_int_pin:        int
    hr_alert_low:      int
    hr_alert_high:     int

    # Vibreur
    vib_enabled:       bool
    vib_gpio_pin:      int
    vib_pwm_freq:      int
    vib_duty:          int
    vib_pattern_on:    float
    vib_pattern_off:   float
    vib_pattern_reps:  int
    vib_trigger_dur:   float

    # Pont de Wheatstone
    ws_enabled:        bool
    ws_i2c_address:    int
    ws_gain:           int
    ws_sample_rate:    float

    # Angle volant
    st_enabled:        bool
    st_i2c_address:    int
    st_gain:           int
    st_channel:        int
    st_sample_rate:    float
    st_v_min:          float
    st_v_max:          float
    st_angle_min:      float
    st_angle_max:      float


def load_config(path: str = "config.xml") -> Config:
    if not os.path.isabs(path) and not os.path.exists(path):
        path = os.path.join(os.path.dirname(__file__), path)

    tree = ET.parse(path)
    root = tree.getroot()

    def get(tag: str) -> str:
        node = root.find(tag)
        if node is None or node.text is None:
            raise ValueError(f"Balise manquante dans config.xml : <{tag}>")
        return node.text.strip()

    def getbool(tag: str) -> bool:
        return get(tag).lower() == "true"

    def get_default(tag: str, default: str) -> str:
        node = root.find(tag)
        if node is None or node.text is None:
            return default
        return node.text.strip()

    return Config(
        # Journalisation
        log_level        = get_default("logging/level", "INFO"),

        # Conducteur
        id_conducteur    = int(get("conducteur/id")),

        # BDD
        db_host          = get("database/host"),
        db_port          = int(get("database/port")),
        db_user          = get("database/user"),
        db_password      = get("database/password"),
        db_name          = get("database/name"),

        # Détection yeux
        camera_index     = int(get_default("detection/camera_index", "0")),
        max_ear          = float(get("detection/max_ear")),
        closed_threshold = float(get("detection/closed_threshold")),
        alert_duration   = float(get("detection/alert_duration")),
        print_interval   = float(get("detection/print_interval")),

        # Enregistrement
        send_interval    = float(get("recording/send_interval")),

        # Son
        sound_enabled    = getbool("sound/enabled"),
        sound_file       = get("sound/file"),

        # Capteur cardiaque
        hr_enabled       = getbool("heart_rate/enabled"),
        hr_i2c_bus       = int(get("heart_rate/i2c_bus")),
        hr_int_pin       = int(get("heart_rate/int_pin")),
        hr_alert_low     = int(get("heart_rate/alert_bpm_low")),
        hr_alert_high    = int(get("heart_rate/alert_bpm_high")),

        # Vibreur
        vib_enabled      = getbool("vibrator/enabled"),
        vib_gpio_pin     = int(get("vibrator/gpio_pin")),
        vib_pwm_freq     = int(get("vibrator/pwm_frequency")),
        vib_duty         = int(get("vibrator/duty_cycle")),
        vib_pattern_on   = float(get("vibrator/pattern_on")),
        vib_pattern_off  = float(get("vibrator/pattern_off")),
        vib_pattern_reps = int(get("vibrator/pattern_reps")),
        vib_trigger_dur  = float(get("vibrator/trigger_duration")),

        # Wheatstone
        ws_enabled       = getbool("wheatstone/enabled"),
        ws_i2c_address   = int(get("wheatstone/i2c_address"), 16),
        ws_gain          = int(get("wheatstone/gain")),
        ws_sample_rate   = float(get("wheatstone/sample_rate")),

        # Angle volant
        st_enabled       = getbool("steering/enabled"),
        st_i2c_address   = int(get("steering/i2c_address"), 16),
        st_gain          = int(get("steering/gain")),
        st_channel       = int(get("steering/channel")),
        st_sample_rate   = float(get("steering/sample_rate")),
        st_v_min         = float(get("steering/v_min")),
        st_v_max         = float(get("steering/v_max")),
        st_angle_min     = float(get("steering/angle_min")),
        st_angle_max     = float(get("steering/angle_max")),
    )
