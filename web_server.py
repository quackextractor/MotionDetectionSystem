
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

# Night light pin
NIGHT_LIGHT_PIN = 7
shutdown_flag = threading.Event()

# --- GPIO & Light Setup ---
def setup_night_light():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(NIGHT_LIGHT_PIN, GPIO.OUT)
    logging.getLogger('motion_detection').info("Night light initialized on PIN %d", NIGHT_LIGHT_PIN)

def activate_night_light():
    GPIO.output(NIGHT_LIGHT_PIN, GPIO.HIGH)
    logging.getLogger('motion_detection').info("Night light activated")


def deactivate_night_light():
    GPIO.output(NIGHT_LIGHT_PIN, GPIO.LOW)
    logging.getLogger('motion_detection').info("Night light deactivated")

# --- Configuration ---
def load_or_create_config():
    config_dir = 'config'
    config_path = os.path.join(config_dir, 'motion_config.yml')
    default_config = {
        'camera': {'resolution': {'width': 640, 'height': 360}, 'fps': 20},
        'motion_detection': {'min_area': 2000, 'min_frames_for_video': 10, 'threshold': 3},
        'alarm': {'enabled': True, 'duration': 30}
    }
    os.makedirs(config_dir, exist_ok=True)
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            yaml.dump(default_config, f)
        return default_config
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
            # ensure threshold exists
            if 'threshold' not in cfg['motion_detection']:
                cfg['motion_detection']['threshold'] = default_config['motion_detection']['threshold']
            return cfg
    except Exception:
        return default_config

# --- Logging ---
def setup_logging():
    os.makedirs('logs', exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f'logs/motion_{ts}.log'
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.FileHandler(fname), logging.StreamHandler()])
    return logging.getLogger('motion_detection')

# --- Camera ---
def setup_camera(cfg):
    picam2 = Picamera2()
    w, h = cfg['camera']['resolution']['width'], cfg['camera']['resolution']['height']
    config = picam2.create_preview_configuration(main={"size": (w, h)})
    picam2.configure(config)
    picam2.start()
    return picam2

# --- Motion Detection ---
def detect_motion(prev, cur, min_area):
    g1 = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)
    g1 = cv2.GaussianBlur(g1, (21,21),0)
    g2 = cv2.GaussianBlur(g2, (21,21),0)
    delta = cv2.absdiff(g1, g2)
    th = cv2.threshold(delta,25,255,cv2.THRESH_BINARY)[1]
    th = cv2.dilate(th, None, iterations=2)
    cnts,_ = cv2.findContours(th,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    return any(cv2.contourArea(c)>min_area for c in cnts)

# --- Saving ---
def save_images(frames, start_time):
    ts = start_time.strftime("%Y%m%d_%H%M%S")
    base = 'motion_images'
    dir_ = os.path.join(base, ts)
    os.makedirs(dir_, exist_ok=True)
    for i, f in enumerate(frames):
        cv2.imwrite(f"{dir_}/frame_{i:03d}.jpg", f)


def save_video(frames, cfg):
    fps = cfg['camera']['fps']
    if len(frames)<cfg['motion_detection']['min_frames_for_video']:
        save_images(frames, datetime.datetime.now()); return
    os.makedirs('motion_videos', exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"motion_videos/motion_{ts}.avi"
    h,w,_ = frames[0].shape
    out = cv2.VideoWriter(fname, cv2.VideoWriter_fourcc(*'XVID'), fps, (w,h))
    for f in frames: out.write(f)
    out.release()

# --- Main Loop ---
def motion_loop():
    logger = setup_logging()
    cfg = load_or_create_config()
    camera = setup_camera(cfg)
    if cfg['alarm']['enabled']:
        setup_gpio(); logger.info("Alarm initialized")
    setup_night_light(); activate_night_light()

    prev_frame = cv2.cvtColor(camera.capture_array(), cv2.COLOR_RGB2BGR)
    frames, count, recording = [], 0, False
    last_motion, alarm_start = time.time(), None
    threshold = cfg['motion_detection']['threshold']

    while not shutdown_flag.is_set():
        frame = cv2.cvtColor(camera.capture_array(), cv2.COLOR_RGB2BGR)
        if detect_motion(prev_frame, frame, cfg['motion_detection']['min_area']):
            count += 1; frames.append(frame); last_motion = time.time()
            if not recording and count >= threshold:
                recording = True; logger.info("Start recording")
                frames = [frame]
                if cfg['alarm']['enabled'] and alarm_start is None:
                    activate_siren(); alarm_start = time.time()
        elif recording and time.time() - last_motion >= 2:
            logger.info("Stop recording"); save_video(frames, cfg)
            frames, count, recording, alarm_start = [], 0, False, None
        if alarm_start and time.time() - alarm_start >= cfg['alarm']['duration']:
            deactivate_siren(); alarm_start = None
        prev_frame = frame
        time.sleep(1/cfg['camera']['fps'])

    # Cleanup
    if cfg['alarm']['enabled']: deactivate_siren()
    deactivate_night_light(); camera.stop(); GPIO.cleanup(); logger.info("Motion loop stopped")

if __name__ == '__main__':
    try:
        motion_loop()
    except KeyboardInterrupt:
        shutdown_flag.set()
