from flask import Flask, send_file, render_template, request, redirect, url_for, session
import os
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from pathlib import Path
import yaml

app = Flask(__name__)
app.secret_key = os.urandom(24)

def load_config():
    """
    Load configuration from YAML file or create default if not exists.
    Returns the configuration dictionary.
    """
    BASE_DIR = '/home/stevek/project/Miro/'
    CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'server_config.yml')
    
    # Default configuration
    default_config = {
        'base_dir': '/home/stevek/project/Miro/',
        'motion_images_dir': 'motion_images',
        'motion_videos_dir': 'motion_videos',
        'users': {
            'admin': generate_password_hash('admin')
        },
        'server': {
            'host': '0.0.0.0',
            'port': 5000
        }
    }
    
    # Create config directory if it doesn't exist
    config_dir = os.path.dirname(CONFIG_PATH)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    
    # Try to load existing config, create default if not exists
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as config_file:
                config = yaml.safe_load(config_file)
                if config is None:  # File exists but is empty
                    config = default_config
        else:
            config = default_config
            with open(CONFIG_PATH, 'w') as config_file:
                yaml.dump(config, config_file, default_flow_style=False)
    except Exception as e:
        print(f"Error loading config: {e}")
        config = default_config
    
    return config

# Load configuration
config = load_config()

# Set global variables from config
BASE_DIR = config['base_dir']
MOTION_IMAGES_DIR = os.path.join(BASE_DIR, config['motion_images_dir'])
MOTION_VIDEOS_DIR = os.path.join(BASE_DIR, config['motion_videos_dir'])
USERS = config['users']

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_event_details(path):
    """Extract timestamp from directory/file name and format it."""
    try:
        timestamp_str = path.split('_')[1].split('.')[0]
        timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
        return timestamp.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return path

@app.route('/')
@login_required
def index():
    return redirect(url_for('events'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username in USERS and check_password_hash(USERS[username], password):
            session['username'] = username
            return redirect(url_for('index'))
        
        return 'Invalid credentials', 401
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/events')
@login_required
def events():
    events = []
    
    # Get video events
    for video in sorted(os.listdir(MOTION_VIDEOS_DIR), reverse=True):
        if video.endswith('.avi'):
            timestamp = get_event_details(video)
            events.append({
                'timestamp': timestamp,
                'type': 'video',
                'filename': video,
                'path': f'video/{video}'
            })
    
    # Get image sequence events
    for image_dir in sorted(os.listdir(MOTION_IMAGES_DIR), reverse=True):
        dir_path = os.path.join(MOTION_IMAGES_DIR, image_dir)
        if os.path.isdir(dir_path):
            timestamp = get_event_details(image_dir)
            frame_count = len([f for f in os.listdir(dir_path) if f.endswith('.jpg')])
            events.append({
                'timestamp': timestamp,
                'type': 'frames',
                'filename': image_dir,
                'frame_count': frame_count,
                'path': f'frames/{image_dir}'
            })
    
    return render_template('events.html', events=events)

@app.route('/frames/<path:event_dir>')
@login_required
def view_frames(event_dir):
    dir_path = os.path.join(MOTION_IMAGES_DIR, event_dir)
    if not os.path.exists(dir_path):
        return 'Event not found', 404
    
    frames = sorted([f for f in os.listdir(dir_path) if f.endswith('.jpg')])
    timestamp = get_event_details(event_dir)
    
    return render_template('frames.html',
                         event_dir=event_dir,
                         timestamp=timestamp,
                         frames=frames)

@app.route('/frame/<path:event_dir>/<path:frame>')
@login_required
def serve_frame(event_dir, frame):
    frame_path = os.path.join(MOTION_IMAGES_DIR, event_dir, frame)
    if not os.path.exists(frame_path):
        return 'Frame not found', 404
    return send_file(frame_path)

@app.route('/video/<path:video_file>')
@login_required
def serve_video(video_file):
    video_path = os.path.join(MOTION_VIDEOS_DIR, video_file)
    if not os.path.exists(video_path):
        return 'Video not found', 404
    return send_file(video_path)

if __name__ == '__main__':
    app.run(host=config['server']['host'], 
            port=config['server']['port'])
