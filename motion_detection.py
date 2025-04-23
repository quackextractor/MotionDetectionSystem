import cv2
import subprocess
import numpy as np
import datetime
import os
import time
import logging
import yaml
from picamera2 import Picamera2
from buzzer import setup_gpio, activate_siren, deactivate_siren
import RPi.GPIO as GPIO
import threading

# Night light pin constant
NIGHT_LIGHT_PIN = 7

# Shared frame and lock for streaming
latest_frame = None
frame_lock = threading.Lock()
motion_detection_running = True

# --- GPIO / Light Setup ---
def setup_night_light():
    """Setup GPIO pin for night light."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(NIGHT_LIGHT_PIN, GPIO.OUT)
    logging.getLogger('motion_detection').info("Night light initialized on PIN %s", NIGHT_LIGHT_PIN)


def activate_night_light():
    """Turn on the night light."""
    GPIO.output(NIGHT_LIGHT_PIN, GPIO.HIGH)
    logging.getLogger('motion_detection').info("Night light activated")


def deactivate_night_light():
    """Turn off the night light."""
    GPIO.output(NIGHT_LIGHT_PIN, GPIO.LOW)
    logging.getLogger('motion_detection').info("Night light deactivated")

# --- Configuration & Logging ---
def load_or_create_config():
    config_dir = 'config'
    config_path = os.path.join(config_dir, 'motion_config.yml')

    default_config = {
        'camera': {'resolution': {'width': 640, 'height': 360}, 'fps': 20},
        'motion_detection': {'min_area': 2000, 'min_frames_for_video': 10, 'threshold': 3, 'cooldown': 5, 'video_duration': 5},
        'alarm': {'enabled': True, 'duration': 30}
    }

    os.makedirs(config_dir, exist_ok=True)
    if not os.path.exists(config_path):
        logging.getLogger('motion_detection').info("No configuration found. Creating default.")
        with open(config_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False)
        return default_config

    try:
        with open(config_path, 'r') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        logging.getLogger('motion_detection').error(f"Error loading config: {e}")
        return default_config

    # Merge missing defaults
    for section, vals in default_config.items():
        cfg.setdefault(section, vals)
        for key, val in vals.items():
            if isinstance(val, dict):
                cfg[section].setdefault(key, val)
    return cfg


def setup_logging():
    if not os.path.exists('logs'):
        os.makedirs('logs')
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = f'logs/motion_detection_{ts}.log'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(logfile), logging.StreamHandler()]
    )
    return logging.getLogger('motion_detection')


def setup_camera(config):
    picam2 = Picamera2()
    w = config['camera']['resolution']['width']
    h = config['camera']['resolution']['height']
    cfg = picam2.create_preview_configuration(main={"size": (w, h)})
    picam2.configure(cfg)
    picam2.start()
    return picam2

# --- Motion Detection Helpers ---
def detect_motion(prev, curr, min_area):
    gray_prev = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    gray_curr = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
    gray_prev = cv2.GaussianBlur(gray_prev, (21, 21), 0)
    gray_curr = cv2.GaussianBlur(gray_curr, (21, 21), 0)
    delta = cv2.absdiff(gray_prev, gray_curr)
    thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return any(cv2.contourArea(c) > min_area for c in contours)

# --- Save Outputs ---
def save_images(frames, start_time):
    ts = start_time.strftime("%Y%m%d_%H%M%S")
    base_dir = 'motion_images'
    out_dir = os.path.join(base_dir, ts)
    os.makedirs(out_dir, exist_ok=True)
    logger = logging.getLogger('motion_detection')
    for i, f in enumerate(frames): cv2.imwrite(os.path.join(out_dir, f"frame_{i:03d}.jpg"), f)
    logger.info(f"Saved {len(frames)} images to {out_dir}")


def save_video(frames, config):
    fps = config['camera']['fps']
    min_f = config['motion_detection']['min_frames_for_video']
    if len(frames) < min_f:
        save_images(frames, datetime.datetime.now())
        return
    os.makedirs('motion_videos', exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f'motion_videos/motion_{ts}.avi'
    h, w, _ = frames[0].shape
    out = cv2.VideoWriter(fname, cv2.VideoWriter_fourcc(*'XVID'), fps, (w, h))
    for f in frames: out.write(f)
    out.release()
    logging.getLogger('motion_detection').info(f"Saved video {fname}")

# --- Main Threaded Function ---
def motion_detection_main():
    global latest_frame, motion_detection_running
    logger = setup_logging()
    logger.info("Motion detection thread started")
    config = load_or_create_config()
    camera = setup_camera(config)
    if config['alarm']['enabled']: setup_gpio()
    setup_night_light(); activate_night_light()

    prev = cv2.cvtColor(camera.capture_array(), cv2.COLOR_RGB2BGR)
    motion_count = 0; recording = False; frames_buf = []
    last_motion = time.time(); alarm_start = None

    try:
        while motion_detection_running:
            cur = cv2.cvtColor(camera.capture_array(), cv2.COLOR_RGB2BGR)
            if detect_motion(prev, cur, config['motion_detection']['min_area']):
                motion_count += 1
                frames_buf.append(cur)
                last_motion = time.time()
                if not recording and motion_count >= config['motion_detection']['threshold']:
                    recording = True; frames_buf = [cur]
                    logger.info("Motion threshold reached, recording started")
                    if config['alarm']['enabled'] and alarm_start is None:
                        activate_siren(); subprocess.Popen(["python3", "BulbControl.py"]);
                        alarm_start = time.time()
            elif recording and time.time() - last_motion >= config['motion_detection']['cooldown']:
                logger.info("Motion stopped, saving recording")
                save_video(frames_buf, config)
                frames_buf = []; recording = False; motion_count = 0; alarm_start = None
            # Alarm timeout
            if alarm_start and (time.time() - alarm_start) >= config['alarm']['duration']:
                deactivate_siren(); alarm_start = None
            prev = cur
            # Update shared frame for streaming
            with frame_lock:
                latest_frame = cur.copy()
    except Exception as e:
        logger.error(f"Error in motion thread: {e}", exc_info=True)
    finally:
        motion_detection_running = False
        if config['alarm']['enabled']: deactivate_siren()
        deactivate_night_light()
        camera.stop(); GPIO.cleanup()
        logger.info("Motion detection thread stopped")

if __name__ == '__main__':
    motion_detection_main()
