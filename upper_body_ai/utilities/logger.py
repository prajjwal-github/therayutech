import os
import time
import cv2

class SessionLogger:
    """
    Video Session Recording & Screenshot Manager.
    Handles interactive keyboard shortcuts:
    - R -> Toggle video recording session (.mp4 saved to output/recordings/)
    - S -> Capture high-resolution screenshot (.png saved to output/screenshots/)
    """

    def __init__(self, output_dir="output", recordings_dir=None, screenshots_dir=None):
        if recordings_dir is None:
            recordings_dir = os.path.join(output_dir, "recordings")
        if screenshots_dir is None:
            screenshots_dir = os.path.join(output_dir, "screenshots")
        self.output_dir = output_dir
        self.recordings_dir = recordings_dir
        self.screenshots_dir = screenshots_dir

        os.makedirs(self.recordings_dir, exist_ok=True)
        os.makedirs(self.screenshots_dir, exist_ok=True)

        self.is_recording = False
        self.writer = None
        self.record_filename = None

    def toggle_recording(self, frame_sample, fps=30.0):
        """Toggles video recording session on/off."""
        if not self.is_recording:
            h, w = frame_sample.shape[:2]
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            self.record_filename = os.path.join(self.recordings_dir, f"physio_session_{timestamp_str}.mp4")
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.writer = cv2.VideoWriter(self.record_filename, fourcc, fps, (w, h))
            self.is_recording = True
            print(f"[REC] Started video recording session -> '{self.record_filename}'")
        else:
            self.stop_recording()

    def record_frame(self, frame_bgr):
        """Writes frame to open video recording stream."""
        if self.is_recording and self.writer is not None:
            self.writer.write(frame_bgr)

    def stop_recording(self):
        """Stops active video recording session."""
        if self.is_recording and self.writer is not None:
            self.writer.release()
            self.writer = None
            self.is_recording = False
            print(f"[REC] Saved video recording session -> '{self.record_filename}'")

    def take_screenshot(self, frame_bgr):
        """Saves high-resolution screenshot to output/screenshots/."""
        if frame_bgr is None:
            return None
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        shot_path = os.path.join(self.screenshots_dir, f"screenshot_{timestamp_str}.png")
        cv2.imwrite(shot_path, frame_bgr)
        print(f"[SCREENSHOT] Saved screenshot -> '{shot_path}'")
        return shot_path

# Alias for backwards compatibility with live_pose.py
MediaLogger = SessionLogger

