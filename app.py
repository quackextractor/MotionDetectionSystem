#!/usr/bin/env python3
import threading
import time
import os
import logging
import signal
from datetime import datetime
from functools import wraps

import yaml
import cv2
import numpy as np
from flask import (
    Flask, Response, render_template, render_template_string,
    request, redirect, url_for, session, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from picamera2 import Picamera2
import RPi.GPIO as GPIO

from buzzer import setup_gpio, activate_siren, deactivate_siren

from datetime import datetime

def parse_timestamp(name: str) -> str:
    """
    Try to parse `name` as either YYYYMMDD_HHMMSS or YYYYMMDD.
    If that fails, return the raw `name`.
    """
    for fmt, out_fmt in (
        ("%Y%m%d_%H%M%S", "%Y-%m-%d %H:%M:%S"),
        ("%Y%m%d",       "%Y-%m-%d")):
        try:
            return datetime.strptime(name, fmt).strftime(out_fmt)
        except ValueError:
            continue
    return name


# -----------------------------------------------------------------------------
# HTML templates embedded in this one script
# -----------------------------------------------------------------------------
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Login - Phototrap Media Server</title>
    <style>
        /* same styles as before */
    </style>
</head>
<body>
    <div class="login-form">
        <h2>Phototrap Media Server</h2>
        <form method="POST">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
"""

EVENTS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Motion Events</title>
    <style>
        /* same styles as before */
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Motion Events</h1>
            <div>
                <a href="{{ url_for('video_feed') }}" class="view-link" target="_blank">Live Feed</a>
                <a href="{{ url_for('logout') }}" class="logout">Logout</a>
            </div>
        </div>
        <div class="events">
            {% for event in events %}
                <div class="event-card">
                    <h3>{{ event.timestamp }}</h3>
                    <span class="event-type {{ event.type }}">
                        {% if event.type == 'video' %}
                            Video Recording
                        {% else %}
                            {{ event.frame_count }} Frames
                        {% endif %}
                    </span>
                    <div>
                        {% if event.type == 'video' %}
                            <a href="{{ url_for('serve_video', video_file=event.filename) }}"
                               class="view-link" target="_blank">View Video</a>
                        {% else %}
                            <a href="{{ url_for('view_frames', event_dir=event.filename) }}"
                               class="view-link">View Frames</a>
                        {% endif %}
                    </div>
                </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

FRAMES_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Frame Sequence</title>
    <style>
        /* same styles as before */
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <a href="{{ url_for('events') }}" class="back-link">← Back to Events</a>
                <h1>Event: {{ timestamp }}</h1>
            </div>
            <a href="{{ url_for('logout') }}" class="logout">Logout</a>
        </div>
        <div class="frames">
            {% for frame in frames %}
                <div class="frame">
                    <a href="{{ url_for('serve_frame', event_dir=event_dir, frame=frame) }}" target="_blank">
                        <img src="{{ url_for('serve_frame', event_dir=event_dir, frame=frame) }}" alt="{{ frame }}">
                    </a>
                    <div class="frame-number">{{ frame }}</div>
                </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# Configuration loaders
# -----------------------------------------------------------------------------
def load_server_config():
    BASE_DIR = os.path.expanduser('~/project/Miro/')
    CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'server_config.yml')
    default = {
        'base_dir': BASE_DIR,
        'motion_images_dir': 'motion_images',
        'motion_videos_dir': 'motion_videos',
        'users': {'admin': generate_password_hash('admin')},
        'server': {'host': '0.0.0.0', 'port': 8087}
    }
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            yaml.dump(default, f)
        return default
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or default
    except Exception:
        cfg = default
    return cfg

def load_motion_config():
    CONFIG_DIR = 'config'
    CONFIG_PATH = os.path.join(CONFIG_DIR, 'motion_config.yml')
    default = {
        'camera': {'resolution': {'width': 640, 'height': 360}, 'fps': 20},
        'motion_detection': {'min_area': 2000, 'min_frames_for_video': 10},
        'alarm': {'enabled': True, 'duration': 30}
    }
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            yaml.dump(default, f)
        return default
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or default
    except Exception:
        cfg = default
    return cfg
    
   # Ensure alarm duration is valid, default to 5 seconds if not loaded or invalid
    if 'alarm' not in cfg or 'duration' not in cfg['alarm'] or not isinstance(cfg['alarm']['duration'], int):
        cfg['alarm']['duration'] = 5  # Default to 5 seconds if not correctly loaded
    
    return cfg

# -----------------------------------------------------------------------------
# Globals for frame sharing and shutdown signaling
# -----------------------------------------------------------------------------
latest_frame = None
frame_lock    = threading.Lock()
stop_event    = threading.Event()

# -----------------------------------------------------------------------------
# GPIO-based night-light
# -----------------------------------------------------------------------------
NIGHT_LIGHT_PIN = 7
def setup_night_light():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(NIGHT_LIGHT_PIN, GPIO.OUT)

def activate_night_light():
    GPIO.output(NIGHT_LIGHT_PIN, GPIO.HIGH)

def deactivate_night_light():
    GPIO.output(NIGHT_LIGHT_PIN, GPIO.LOW)

# -----------------------------------------------------------------------------
# Motion detection & saving helpers
# -----------------------------------------------------------------------------
def detect_motion(prev, curr, min_area):
    grayA = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    grayB = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
    grayA = cv2.GaussianBlur(grayA, (21,21), 0)
    grayB = cv2.GaussianBlur(grayB, (21,21), 0)
    delta = cv2.absdiff(grayA, grayB)
    thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)
    cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return any(cv2.contourArea(c) > min_area for c in cnts)

def save_images(frames, base_dir, start_time):
    ts = start_time.strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(base_dir, ts)
    os.makedirs(outdir, exist_ok=True)
    for i, f in enumerate(frames):
        cv2.imwrite(os.path.join(outdir, f"frame_{i:03d}.jpg"), f)

def save_video(frames, cfg, base_dir):
    fps       = cfg['camera']['fps']
    min_frames = cfg['motion_detection']['min_frames_for_video']
    if len(frames) < min_frames:
        save_images(frames, base_dir, datetime.now())
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outpath = os.path.join(base_dir, f"motion_{ts}.avi")
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(outpath, cv2.VideoWriter_fourcc(*'XVID'), fps, (w,h))
    for f in frames:
        writer.write(f)
    writer.release()

# -----------------------------------------------------------------------------
# Background motion-detection thread
# -----------------------------------------------------------------------------
def motion_loop(server_cfg, motion_cfg):
    logger = logging.getLogger('motion-thread')
    picam2 = Picamera2()
    w = motion_cfg['camera']['resolution']['width']
    h = motion_cfg['camera']['resolution']['height']
    cam_conf = picam2.create_preview_configuration(main={'size': (w,h)})
    picam2.configure(cam_conf)
    picam2.start()

    if motion_cfg['alarm']['enabled']:
        setup_gpio()
    setup_night_light()
    activate_night_light()

    prev = cv2.cvtColor(picam2.capture_array(), cv2.COLOR_RGB2BGR)
    motion_count = 0
    recording = False
    frames_buf = []
    last_motion = time.time()
    alarm_started = None
    threshold = 3

    img_dir = os.path.join(server_cfg['base_dir'], server_cfg['motion_images_dir'])
    vid_dir = os.path.join(server_cfg['base_dir'], server_cfg['motion_videos_dir'])
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(vid_dir, exist_ok=True)

    try:
        while not stop_event.is_set():
            frame = cv2.cvtColor(picam2.capture_array(), cv2.COLOR_RGB2BGR)
            with frame_lock:
                global latest_frame
                latest_frame = frame.copy()
            if detect_motion(prev, frame, motion_cfg['motion_detection']['min_area']):
                motion_count += 1
                frames_buf.append(frame)
                last_motion = time.time()
                if not recording and motion_count >= threshold:
                    recording = True
                    frames_buf = [frame]
                    logger.info("Started recording")
                    if motion_cfg['alarm']['enabled'] and alarm_started is None:
                        activate_siren()
                        alarm_started = time.time()
            elif recording and (time.time() - last_motion) >= 2:
                logger.info("Stopping recording & saving")
                save_video(frames_buf, motion_cfg, vid_dir)
                frames_buf = []
                motion_count = 0
                recording = False
                # Explicitly deactivate siren here
                if motion_cfg['alarm']['enabled']:
                    deactivate_siren()
                alarm_started = None

            if alarm_started and (time.time() - alarm_started) >= motion_cfg['alarm']['duration']:
                deactivate_siren()
                alarm_started = None

            prev = frame
            time.sleep(1.0 / motion_cfg['camera']['fps'])

    except Exception as e:
        logger.exception("Motion thread error")
    finally:
        if motion_cfg['alarm']['enabled']:
            deactivate_siren()
        deactivate_night_light()
        picam2.stop()
        GPIO.cleanup()
        logger.info("Motion thread exiting")

# -----------------------------------------------------------------------------
# Flask web server
# -----------------------------------------------------------------------------
app = Flask(__name__)
server_cfg = load_server_config()
motion_cfg = load_motion_config()
app.secret_key = os.urandom(24)
USERS = server_cfg['users']

def login_required(f):
    @wraps(f)
    def wrapped(*a, **k):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*a, **k)
    return wrapped

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        if u in USERS and check_password_hash(USERS[u], p):
            session['username'] = u
            return redirect(url_for('events'))
        return 'Invalid credentials', 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    return redirect(url_for('events'))

@app.route('/events')
@login_required
def events():
    evs = []
    vd = os.path.join(server_cfg['base_dir'], server_cfg['motion_videos_dir'])
    for f in sorted(os.listdir(vd), reverse=True):
        if not f.lower().endswith('.avi'):
            continue
        # motion_20250422_183045.avi  →  raw_ts = "20250422_183045"
        raw_ts = f.rsplit('_', 1)[-1].rsplit('.', 1)[0]
        ts = parse_timestamp(raw_ts)
        evs.append({
            'timestamp': ts,
            'type': 'video',
            'filename': f
        })

    fd = os.path.join(server_cfg['base_dir'], server_cfg['motion_images_dir'])
    for d in sorted(os.listdir(fd), reverse=True):
        p = os.path.join(fd, d)
        if not os.path.isdir(p):
            continue
        ts = parse_timestamp(d)       # now handles both formats
        cnt = len([x for x in os.listdir(p) if x.endswith('.jpg')])
        evs.append({
            'timestamp': ts,
            'type': 'frames',
            'filename': d,
            'frame_count': cnt
        })

    return render_template('events.html', events=evs)

@app.route('/frames/<event_dir>')
@login_required
def view_frames(event_dir):
    base = os.path.join(server_cfg['base_dir'],
                        server_cfg['motion_images_dir'],
                        event_dir)
    if not os.path.isdir(base):
        return 'Not found', 404

    frs = sorted(f for f in os.listdir(base) if f.endswith('.jpg'))
    ts  = parse_timestamp(event_dir)
    return render_template('frames.html', event_dir=event_dir, frames=frs, timestamp=ts)

@app.route('/frame/<event_dir>/<frame>')
@login_required
def serve_frame(event_dir, frame):
    path = os.path.join(server_cfg['base_dir'], server_cfg['motion_images_dir'], event_dir, frame)
    return send_file(path) if os.path.exists(path) else ('Not found', 404)

@app.route('/video/<video_file>')
@login_required
def serve_video(video_file):
    path = os.path.join(server_cfg['base_dir'], server_cfg['motion_videos_dir'], video_file)
    return send_file(path) if os.path.exists(path) else ('Not found', 404)

@app.route('/video_feed')
@login_required
def video_feed():
    def gen():
        while not stop_event.is_set():
            with frame_lock:
                frm = latest_frame.copy() if latest_frame is not None else None
            if frm is None:
                continue
            ret, jpg = cv2.imencode('.jpg', frm)
            if not ret:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpg.tobytes() + b'\r\n')
            time.sleep(1.0 / motion_cfg['camera']['fps'])
    return Response(gen(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# -----------------------------------------------------------------------------
# Main entry: start thread + Flask, ensure cleanup on exit
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    motion_thread = threading.Thread(
        target=motion_loop,
        args=(server_cfg, motion_cfg),
        daemon=True
    )
    motion_thread.start()

    try:
        app.run(
            host=server_cfg['server']['host'],
            port=server_cfg['server']['port']
        )
    finally:
        stop_event.set()
        motion_thread.join()
        logging.info("Shutting down cleanly")
