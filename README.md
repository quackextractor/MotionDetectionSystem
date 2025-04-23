# Motion Detection System

This repository implements a complete motion detection and alert system using a Raspberry Pi camera. It includes:

- **Realtime motion detection** with configurable sensitivity
- **Video** and **image** capture of motion events
- **Alarm** system with buzzer and night-light
- **Flask** web interface for live feed and reviewing recorded events
- **Smart bulb** integration (TP-Link Tapo L530)
- **Automatic cleanup** script for logs and media

---

## Features

- **Motion Detection**: Continuously monitors camera feed, captures frames or video when motion is detected.
- **Alarm & Lighting**:
  - Buzzer-based siren (GPIO)
  - RGB LED indicators and night-light (GPIO)
  - Configurable duration and enable/disable options
- **Web Interface**:
  - **Login** page for secure access
  - **Live video feed** stream
  - **Events** page listing all recorded videos and image sequences
  - **Frame viewer** for browsing individual image sequences
- **Smart Bulb Control**:
  - Discover and control TP-Link Tapo L530 smart bulb
  - Turn on/off during motion events via `BulbControl.py`
- **Config Files**:
  - `motion_config.yml` for detection, camera, and alarm settings
  - `server_config.yml` for web server paths, users, and host settings
- **Cleanup**:
  - `cleanup.sh` to remove all media, logs, and configs for a fresh start

---

## Requirements

- **Hardware**:

  - Raspberry Pi (3 or above) with Camera Module V2
  - Buzzer (GPIO 3)
  - RGB LED (GPIO 18, 15, 14)
  - Night-light diode (GPIO 7)
  - TP-Link Tapo L530 smart bulb

- **Software**:

  - Python 3.7+
  - System packages:
    ```bash
    sudo apt update && sudo apt install -y python3-pip libatlas-base-dev libjasper-dev libqtgui4 python3-pyqt5 libqt4-test
    ```
  - Python dependencies:
    ```bash
    pip3 install opencv-python picamera2 flask pyyaml numpy RPi.GPIO kasa
    ```

---

## Repository Structure

```
project/
├── config/
│   ├── motion_config.yml    # Motion detection settings
│   └── server_config.yml    # Web server and user settings
├── logs/                    # Log files
├── motion_images/           # Captured frame sequences
├── motion_videos/           # Recorded motion videos
├── templates/               # Flask HTML templates
│   ├── login.html
│   ├── events.html
│   └── frames.html
├── app.py                   # Main Flask web server
├── motion_detection.py      # Core motion detection script
├── BulbControl.py           # TP-Link Tapo bulb discovery/control
├── buzzer.py                # Buzzer & GPIO helper functions
├── cleanup.sh               # Cleanup media, logs, and config
└── README.md                # Project documentation
```

---

## Configuration

### motion\_config.yml

Located in `config/motion_config.yml`. If missing, a default file is created with:

```yaml
camera:
  resolution:
    width: 640
    height: 360
  fps: 20
motion_detection:
  min_area: 2000
  min_frames_for_video: 10
  threshold: 3
alarm:
  enabled: true
  duration: 30   # seconds
```

### server\_config.yml

Located in `config/server_config.yml`. Defaults to:

```yaml
base_dir: /home/pi/project
motion_images_dir: motion_images
motion_videos_dir: motion_videos
users:
  admin: <hashed_password>
server:
  host: 0.0.0.0
  port: 8087
```

- **Users**: map usernames to password hashes (use `generate_password_hash` to add new users).

---

## Usage

1. **Start motion detection**:

   ```bash
   python3 app.py
   ```

2. **Access interface**:

   - Open `http://<raspberry-pi-ip>:8087/login` in your browser
   - Login with credentials from `server_config.yml`
   - View live feed, events, and frames

3. **Cleanup (reset all data):**

   ```bash
   python3 BulbControl.py
   ```

   Bulb will turn on/off and log status.



---

## License

Distributed under the MIT License. See `LICENSE` for details.

---

## Acknowledgments

- [Picamera2](https://www.raspberrypi.com/documentation/accessories/camera.html)
- [OpenCV Python](https://opencv.org/)
- [Flask](https://flask.palletsprojects.com/)
- [TP-Link Kasa API](https://github.com/python-kasa/python-kasa)

****
