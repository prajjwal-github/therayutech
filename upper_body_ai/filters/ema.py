import numpy as np

class EMAFilter:
    """Exponential Moving Average (EMA) Low-Pass Filter."""
    def __init__(self, alpha=0.35):
        self.alpha = float(alpha)
        self.state = None

    def filter(self, value):
        val_arr = np.array(value, dtype=np.float32)
        if self.state is None:
            self.state = val_arr
            return val_arr
        self.state = self.alpha * val_arr + (1.0 - self.alpha) * self.state
        return self.state

    def reset(self):
        self.state = None
