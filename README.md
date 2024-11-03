# Motion Detection System Guide

This system consists of two main components:
1. A motion detection script that captures video/images using a Raspberry Pi camera
2. A Flask web application for viewing the captured content

## Setup Requirements

- Raspberry Pi with Camera Module V2
- Python 3.x
- Required Python packages:
  - opencv-cv2
  - picamera2
  - flask
  - pyyaml
  - numpy

## Directory Structure

```
project/
├── config/
│   ├── motion_config.yml
│   └── server_config.yml
├── motion_images/
├── motion_videos/
├── motion_detection.py
├── web_server.py
├── logs/
└── templates/
    ├── login.html
    ├── events.html
    └── frames.html
```

## Motion Detection Script Configuration

The motion detection script uses `motion_config.yml` with these default settings:

```yaml
camera:
  resolution:
    width: 640
    height: 360
  fps: 20
motion_detection:
  min_area: 2000
  min_frames_for_video: 10
```

## Web Server Configuration

The Flask server uses `server_config.yml` with these default settings:

```yaml
base_dir: '/home/stevek/project/Miro/'
motion_images_dir: 'motion_images'
motion_videos_dir: 'motion_videos'
users:
  admin: <hashed-password>
server:
  host: '0.0.0.0'
  port: 5000
```

## Running the System

### 1. Start Motion Detection

```bash
python motion_detection.py
```

The script will:
- Initialize the camera
- Create necessary directories
- Start monitoring for motion
- Save detected motion as either:
  - Video files (if longer than minimum frames)
  - Individual frame images (if shorter than minimum frames)
- Log all activities to `logs/motion_detection_YYYYMMDD_HHMMSS.log`

To stop the motion detection, press 'q' in the preview window.

### 2. Start Web Server

```bash
python web_server.py
```

The server will:
- Start on the configured host and port
- Serve the motion detection footage through a web interface
- Require authentication for access

## Accessing the Web Interface

1. Open a web browser and navigate to `http://<raspberry-pi-ip>:5000`
2. Login with the default credentials:
   - Username: `admin`
   - Password: `admin`

### Web Interface Features

- **Events Page**: Lists all captured motion events sorted by date/time
  - Video recordings
  - Image sequences
- **Frame Viewer**: Browse through image sequences frame by frame
- **Logout**: End your session

## Security Notes

- Change the default admin password in `server_config.yml`
- The web interface requires authentication for all pages
- Sessions expire when the browser is closed

## Troubleshooting

1. **No Events Showing**:
   - Verify directory permissions
   - Check the motion detection logs

2. **Camera Issues**:
   - Ensure the camera module is properly connected
   - Check if camera is enabled in Raspberry Pi configuration
   - Verify picamera2 installation

3. **Web Access Issues**:
   - Confirm the server is running
   - Check firewall settings
   - Verify the configured port is open

## Camera Tuning

The motion detection can be adjusted by modifying these parameters:
- `min_area`: Minimum pixel area to trigger motion detection
- `min_frames_for_video`: Minimum frames needed to save as video
- Resolution and FPS in the configuration file

## Future Improvements
- Database integration for event management
- Push notifications for motion events
- Motion zone configuration (openCV)
- Event filtering and search at web interface
- Add a message when no events are available
- Add direct playback of recorded video clips
- Add previews (thumbnails) to web server
- Write proper docs using a template

