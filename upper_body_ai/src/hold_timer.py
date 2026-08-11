import time

class HoldTimer:
    """
    Automatic Yoga Posture Hold Duration Timer.
    Unlocks and counts down hold duration ONLY when posture accuracy >= 75%.
    Resets timer if posture accuracy drops below threshold.
    """

    def __init__(self, target_hold_sec=15, threshold_pct=75.0):
        self.target_hold_sec = target_hold_sec
        self.threshold_pct = threshold_pct
        self.elapsed_sec = 0.0
        self.is_holding = False
        self.is_completed = False
        self.start_time = None

    def reset(self, target_hold_sec=15):
        self.target_hold_sec = target_hold_sec
        self.elapsed_sec = 0.0
        self.is_holding = False
        self.is_completed = False
        self.start_time = None

    def update(self, accuracy_pct, dt=0.033):
        if self.is_completed:
            return {
                "elapsed_sec": round(self.target_hold_sec, 1),
                "remaining_sec": 0.0,
                "is_holding": False,
                "is_completed": True
            }

        if accuracy_pct >= self.threshold_pct:
            if not self.is_holding:
                self.is_holding = True
                self.start_time = time.time()
            
            self.elapsed_sec += dt
            if self.elapsed_sec >= self.target_hold_sec:
                self.elapsed_sec = float(self.target_hold_sec)
                self.is_completed = True
                self.is_holding = False
        else:
            self.is_holding = False
            self.elapsed_sec = max(0.0, self.elapsed_sec - dt * 0.5)

        remaining = max(0.0, float(self.target_hold_sec) - self.elapsed_sec)
        return {
            "elapsed_sec": round(self.elapsed_sec, 1),
            "remaining_sec": round(remaining, 1),
            "is_holding": self.is_holding,
            "is_completed": self.is_completed
        }
