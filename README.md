# Motion Detection System Guide

This system consists of three main components:
1. A motion detection script that captures video/images using a Raspberry Pi camera
2. An alarm system with buzzer and RGB LED indicators
3. A Flask web application for viewing the captured content

## Setup Requirements

- Raspberry Pi with Camera Module V2
- Python 3.x
- Required Python packages:
  - opencv-cv2
  - picamera2
  - flask
  - pyyaml
  - numpy
  - RPi.GPIO
- Hardware components:
  - Buzzer (connected to GPIO 3)
  - RGB LED (Red: GPIO 18, Green: GPIO 15, Blue: GPIO 14)

## Directory Structure

```
project/
├── config/
│   ├── motion_config.yml
│   └── server_config.yml
├── motion_images/
├── motion_videos/
├── motion_detection.py
├── buzzer.py
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
    default_config = {
        'camera': {
            'resolution': {
                'width': 640,
                'height': 360
            },
            'fps': 20
        },
        'motion_detection': {
            'min_area': 2000,
            'min_frames_for_video': 10
        },
        'alarm': {
            'enabled': True,
            'duration': 3
        }
    }
```

## Alarm System

The system includes an alarm feature that activates when motion is detected:
- Buzzer produces alternating police siren sound
- RGB LED alternates between red and blue
- Alarm automatically deactivates after configured duration
- Can be manually disabled in configuration

### Night Light
- Automatic activation when motion detection script starts
- Provides constant illumination during operation
- Automatically deactivates when script is stopped
- Connected to GPIO 7

## Hardware Setup

1. Connect buzzer to GPIO 3
2. Connect RGB LED:
   - Red lead to GPIO 18
   - Green lead to GPIO 15
   - Blue lead to GPIO 14
3. Connect night light diode to GPIO 7
4. Ensure proper ground connections


## Future Improvements
- Database integration for event management
- Push notifications for motion events
- Motion zone configuration (openCV)
- Event filtering and search at web interface
- Add a message when no events are available
- Add direct playback of recorded video clips
- Add previews (thumbnails) to web server
- Write proper docs using a template
- Add configurable alarm patterns and sounds
- Add remote alarm control through web interface