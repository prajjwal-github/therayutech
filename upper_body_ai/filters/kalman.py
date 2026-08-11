import cv2
import numpy as np

class KalmanFilter2D:
    """
    2D/3D Constant Velocity Kalman Filter for Landmark Motion Tracking.
    State vector: [x, y, vx, vy]^T
    Measurement vector: [x, y]^T
    """

    def __init__(self, process_noise=1e-4, measurement_noise=1e-2):
        self.kf = cv2.KalmanFilter(4, 2)
        
        # State Transition Matrix F
        self.kf.transitionMatrix = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ], dtype=np.float32)

        # Measurement Matrix H
        self.kf.measurementMatrix = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ], dtype=np.float32)

        # Process Noise Covariance Q
        self.kf.processNoiseCov = np.eye(4, dtype=np.float32) * process_noise

        # Measurement Noise Covariance R
        self.kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * measurement_noise

        # Error Covariance P
        self.kf.errorCovPost = np.eye(4, dtype=np.float32)

        self.initialized = False

    def filter(self, point2d):
        meas = np.array([[np.float32(point2d[0])], [np.float32(point2d[1])]])

        if not self.initialized:
            self.kf.statePost = np.array([[meas[0, 0]], [meas[1, 0]], [0.0], [0.0]], dtype=np.float32)
            self.initialized = True
            return np.array([point2d[0], point2d[1]], dtype=np.float32)

        # Predict
        prediction = self.kf.predict()
        # Correct
        estimated = self.kf.correct(meas)

        return np.array([estimated[0, 0], estimated[1, 0]], dtype=np.float32)

    def reset(self):
        self.initialized = False
