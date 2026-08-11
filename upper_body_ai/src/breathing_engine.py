class BreathingEngine:
    """
    Synchronized Yoga Breathing Guidance Engine.
    Manages Inhale, Hold, Exhale phase timing and instructions.
    """

    def __init__(self, inhale_sec=4, hold_sec=4, exhale_sec=4):
        self.inhale_sec = inhale_sec
        self.hold_sec = hold_sec
        self.exhale_sec = exhale_sec
        self.cycle_time = 0.0

    def update(self, dt=0.033):
        self.cycle_time += dt
        total_cycle = float(self.inhale_sec + self.hold_sec + self.exhale_sec)
        t = self.cycle_time % total_cycle

        if t < self.inhale_sec:
            phase = "INHALE"
            instruction = f"Inhale deeply ({self.inhale_sec - int(t)}s)"
            pct = t / self.inhale_sec
        elif t < (self.inhale_sec + self.hold_sec):
            phase = "HOLD"
            instruction = f"Hold breath ({self.inhale_sec + self.hold_sec - int(t)}s)"
            pct = (t - self.inhale_sec) / self.hold_sec
        else:
            phase = "EXHALE"
            instruction = f"Exhale slowly ({total_cycle - int(t)}s)"
            pct = (t - self.inhale_sec - self.hold_sec) / self.exhale_sec

        return {
            "phase": phase,
            "instruction": instruction,
            "progress_pct": round(pct * 100.0, 1)
        }
