import os
import time
import threading
import cv2
import numpy as np

class WebcamStream:
    """
    Asynchronous Threaded Live WebCam Frame Capture.
    Runs frame capture in a dedicated background daemon thread to achieve zero-lag execution.
    Features:
    - Automatic device fallback (Device 0 -> 1 -> Synthetic test loop)
    - FPS calculation & hardware resolution negotiation
    - Non-blocking frame queue buffer
    """

    def __init__(self, src=0, width=1280, height=720, fps=60, flip_horizontal=True, **kwargs):
        self.src = src
        self.width = width
        self.height = height
        self.target_fps = fps
        self.flip_horizontal = flip_horizontal

        self.stream = None
        self.grabbed = False
        self.frame = None
        self.stopped = False

        self.fps = 0.0
        self.frame_count = 0
        self.start_time = time.time()
        self.last_frame_time = time.time()

        self._init_camera()

    def _init_camera(self):
        """Attempts camera initialization with resolution configuration and device fallback."""
        devices_to_try = [self.src]
        if self.src != 0: devices_to_try.append(0)
        if 1 not in devices_to_try: devices_to_try.append(1)

        for dev_id in devices_to_try:
            print(f"[INFO] Attempting webcam initialization on Device ID: {dev_id}...")
            cap = cv2.VideoCapture(dev_id, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                cap.set(cv2.CAP_PROP_FPS, self.target_fps)


                ret, frame = cap.read()
                if ret and frame is not None:
                    self.stream = cap
                    self.src = dev_id
                    self.grabbed = ret
                    if self.flip_horizontal:
                        frame = cv2.flip(frame, 1)
                    self.frame = frame
                    print(f"[SUCCESS] WebCam initialized on Device {dev_id} ({frame.shape[1]}x{frame.shape[0]})!")
                    return

                cap.release()

        print("[WARNING] No physical webcam detected! Initializing synthetic fallback camera stream...")
        self.stream = None
        self.grabbed = True
        self.frame = self._generate_synthetic_frame()

    def _generate_synthetic_frame(self):
        """Generates synthetic test frame if no physical webcam is attached."""
        img = np.full((self.height, self.width, 3), (35, 30, 25), dtype=np.uint8)
        cv2.putText(img, "SYNTHETIC CAMERA FALLBACK (NO PHYSICAL WEBCAM)", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        cv2.putText(img, "Connect USB WebCam for live human motion tracking", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        return img

    def start(self):
        """Starts the background frame capture thread."""
        self.stopped = False
        self.start_time = time.time()
        self.last_frame_time = time.time()
        t = threading.Thread(target=self.update, args=(), daemon=True)
        t.start()
        return self

    def update(self):
        """Thread worker function that continuously grabs frames."""
        while not self.stopped:
            if self.stream is not None and self.stream.isOpened():
                ret, frame = self.stream.read()
                if ret and frame is not None:
                    if self.flip_horizontal:
                        frame = cv2.flip(frame, 1)
                    self.frame = frame
                    self.grabbed = ret

                    # Calculate FPS
                    self.frame_count += 1
                    now = time.time()
                    elapsed = now - self.start_time
                    if elapsed >= 1.0:
                        self.fps = round(self.frame_count / elapsed, 1)
                        self.frame_count = 0
                        self.start_time = now
                else:
                    time.sleep(0.01)
            else:
                # Update synthetic test frame
                self.frame = self._generate_synthetic_frame()
                time.sleep(0.033)

    def read(self):
        """Returns the current frame."""
        return self.grabbed, self.frame

    def stop(self):
        """Stops the thread and releases the webcam."""
        self.stopped = True
        time.sleep(0.05)
        if self.stream is not None:
            self.stream.release()
            self.stream = None
        print("[INFO] Camera stream stopped and hardware released.")
