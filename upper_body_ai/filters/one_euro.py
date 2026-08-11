import math
import time
import numpy as np

def smoothing_factor(t_e, cutoff):
    """Calculates alpha smoothing factor for low-pass filter."""
    r = 2 * math.pi * cutoff * t_e
    return r / (r + 1.0)

def exponential_smoothing(a, x, x_prev):
    """Applies exponential low-pass filter."""
    return a * x + (1.0 - a) * x_prev

class LowPassFilter:
    """1D Low-Pass Filter used inside One Euro Filter."""
    def __init__(self, alpha=1.0):
        self.alpha = alpha
        self.x_prev = None

    def filter(self, x, alpha=None):
        if alpha is not None:
            self.alpha = alpha
        if self.x_prev is None:
            self.x_prev = x
            return x
        x_hat = exponential_smoothing(self.alpha, x, self.x_prev)
        self.x_prev = x_hat
        return x_hat

    def reset(self):
        self.x_prev = None

class OneEuroFilter:
    """
    One Euro Adaptive Low-Pass Filter.
    Adaptive cutoff frequency fc = min_cutoff + beta * |dx/dt|.
    Eliminates keypoint jitter during stationary postures while preserving zero lag during fast motion.
    """

    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)

        self.x_filter = LowPassFilter()
        self.dx_filter = LowPassFilter()
        self.last_time = None

    def filter(self, x, timestamp=None):
        if timestamp is None:
            timestamp = time.time()

        if self.last_time is None:
            self.last_time = timestamp
            return self.x_filter.filter(x)

        dt = timestamp - self.last_time
        self.last_time = timestamp

        if dt <= 1e-6:
            dt = 1e-4

        # Compute derivative (speed)
        x_prev = self.x_filter.x_prev if self.x_filter.x_prev is not None else x
        dx = (x - x_prev) / dt

        # Filter derivative
        a_d = smoothing_factor(dt, self.d_cutoff)
        dx_hat = self.dx_filter.filter(dx, a_d)

        # Adapt cutoff frequency based on speed
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)

        # Filter signal
        a = smoothing_factor(dt, cutoff)
        return self.x_filter.filter(x, a)

    def reset(self):
        self.x_filter.reset()
        self.dx_filter.reset()
        self.last_time = None

class OneEuroFilter3D:
    """Multi-dimensional (X, Y, Z) One Euro Filter."""
    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        self.fx = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self.fy = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self.fz = OneEuroFilter(min_cutoff, beta, d_cutoff)

    def filter(self, point3d, timestamp=None):
        x_val = self.fx.filter(point3d[0], timestamp)
        y_val = self.fy.filter(point3d[1], timestamp)
        z_val = self.fz.filter(point3d[2], timestamp) if len(point3d) > 2 else 0.0
        return np.array([x_val, y_val, z_val], dtype=np.float32)

    def reset(self):
        self.fx.reset()
        self.fy.reset()
        self.fz.reset()
