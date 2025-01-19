import cv2
import numpy as np
import datetime
import os
import time
import logging
import yaml
from picamera2 import Picamera2, Preview
from buzzer import setup_gpio, activate_siren, deactivate_siren


def load_or_create_config():
    config_dir = 'config'
    config_path = os.path.join(config_dir, 'motion_config.yml')

    # Default configuration
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
            'duration': 30  # Duration in seconds for alarm to sound
        }
    }

    # Create config directory if it doesn't exist
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    # If config file doesn't exist, create it with default values
    if not os.path.exists(config_path):
        logger = logging.getLogger('motion_detection')
        logger.info("No configuration file found. Creating default configuration.")
        with open(config_path, 'w') as config_file:
            yaml.dump(default_config, config_file, default_flow_style=False)
        return default_config

    # Load existing config
    try:
        with open(config_path, 'r') as config_file:
            config = yaml.safe_load(config_file)
            logger = logging.getLogger('motion_detection')
            logger.info("Configuration loaded successfully")
            return config
    except Exception as e:
        logger = logging.getLogger('motion_detection')
        logger.error(f"Error loading config: {str(e)}. Using defaults.")
        return default_config


def setup_logging():
    if not os.path.exists('logs'):
        os.makedirs('logs')

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f'logs/motion_detection_{timestamp}.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('motion_detection')


def setup_camera(config):
    # Set up the Raspberry Pi Camera V2 using Picamera2
    picam2 = Picamera2()
    width = config['camera']['resolution']['width']
    height = config['camera']['resolution']['height']
    config = picam2.create_preview_configuration(main={"size": (width, height)})
    picam2.configure(config)
    picam2.start()
    return picam2


def detect_motion(previous_frame, current_frame, min_area):
    # Detect motion by comparing consecutive frames
    gray_prev = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
    gray_current = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    gray_prev = cv2.GaussianBlur(gray_prev, (21, 21), 0)
    gray_current = cv2.GaussianBlur(gray_current, (21, 21), 0)
    frame_delta = cv2.absdiff(gray_prev, gray_current)
    thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        if cv2.contourArea(contour) > min_area:
            return True
    return False


def save_images(frames, start_time):
    timestamp = start_time.strftime("%Y%m%d_%H%M%S")
    image_dir = f"motion_images/{timestamp}"

    if not os.path.exists('motion_images'):
        os.makedirs('motion_images')
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    logger = logging.getLogger('motion_detection')
    logger.info(f"Saving {len(frames)} frames as individual images in {image_dir}")

    for i, frame in enumerate(frames):
        image_path = f"{image_dir}/frame_{i:03d}.jpg"
        cv2.imwrite(image_path, frame)

    logger.info(f"Saved {len(frames)} images in {image_dir}")


def save_video(frames, config):
    fps = config['camera']['fps']
    min_frames = config['motion_detection']['min_frames_for_video']

    if len(frames) < min_frames:
        logger = logging.getLogger('motion_detection')
        logger.info(
            f"Video clip too short ({len(frames)} frames < {min_frames} frames), saving as individual images instead")
        save_images(frames, datetime.datetime.now())
        return

    if not os.path.exists('motion_videos'):
        os.makedirs('motion_videos')

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"motion_videos/motion_{timestamp}.avi"
    height, width, _ = frames[0].shape
    out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*'XVID'), fps, (width, height))

    logger = logging.getLogger('motion_detection')
    logger.info(f"Saving video with {len(frames)} frames at {fps} FPS")

    for frame in frames:
        out.write(frame)
    out.release()
    logger.info(f"Motion video saved: {filename}")


def main(cooldown=5, threshold=3, video_duration=5):
    logger = setup_logging()
    logger.info("Starting motion detection system")

    # Load configuration
    config = load_or_create_config()
    logger.info("Configuration loaded with values:")
    logger.info(f"Resolution: {config['camera']['resolution']['width']}x{config['camera']['resolution']['height']}")
    logger.info(f"FPS: {config['camera']['fps']}")
    logger.info(f"Min area for motion detection: {config['motion_detection']['min_area']}")
    logger.info(f"Min frames for video: {config['motion_detection']['min_frames_for_video']}")
    logger.info(f"Alarm enabled: {config['alarm']['enabled']}")

    camera = setup_camera(config)
    logger.info("Camera initialized successfully")

    # Initialize GPIO for buzzer and LED
    if config['alarm']['enabled']:
        setup_gpio()
        logger.info("Alarm system initialized")

    previous_frame = cv2.cvtColor(camera.capture_array(), cv2.COLOR_RGB2BGR)
    last_motion_time = time.time()
    motion_count = 0
    video_frames = []
    recording = False
    recording_start_time = None
    alarm_start_time = None

    try:
        while True:
            current_frame = cv2.cvtColor(camera.capture_array(), cv2.COLOR_RGB2BGR)

            if detect_motion(previous_frame, current_frame, config['motion_detection']['min_area']):
                motion_count += 1
                video_frames.append(current_frame)
                last_motion_time = time.time()

                if not recording and motion_count >= threshold:
                    recording = True
                    recording_start_time = datetime.datetime.now()
                    video_frames = [current_frame]
                    logger.info("Motion detected - Starting video recording")

                    # Activate alarm if enabled
                    if config['alarm']['enabled'] and alarm_start_time is None:
                        logger.info("Activating alarm system")
                        activate_siren()
                        alarm_start_time = time.time()

            elif recording and (time.time() - last_motion_time) >= 2:
                logger.info("Motion stopped - Ending recording")
                save_video(video_frames, config)
                video_frames = []
                recording = False
                motion_count = 0
                recording_start_time = None

            # Check if alarm should be deactivated
            if alarm_start_time and (time.time() - alarm_start_time) >= config['alarm']['duration']:
                logger.info("Deactivating alarm system")
                deactivate_siren()
                alarm_start_time = None

            previous_frame = current_frame
            cv2.imshow("Motion Detection", current_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                logger.info("User initiated shutdown")
                break

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}", exc_info=True)

    finally:
        if config['alarm']['enabled']:
            deactivate_siren()
        camera.stop()
        cv2.destroyAllWindows()
        logger.info("Motion detection system shutdown complete")


if __name__ == "__main__":
    main()