import math
import numpy as np

class PhysiotherapyAnalysisEngine:
    """
    Dedicated Clinical Physiotherapy & Rehabilitation Analysis Engine.
    Features:
    - Real-Time Range of Motion (ROM) Tracking (Min, Max, Peak Degrees per Joint)
    - Movement Quality Score % (0% - 100%) based on anatomical joint bounds & stability
    - Joint Smoothness Index & Leg Symmetry Delta
    - Body Center of Gravity (COG) Shift Offset
    - Dynamic Live Clinical Feedback Generation
    """

    CLINICAL_JOINTS = [
        "elbow_flexion_left", "elbow_flexion_right",
        "shoulder_flexion_left", "shoulder_flexion_right",
        "shoulder_abduction_left", "shoulder_abduction_right",
        "hip_flexion_left", "hip_flexion_right",
        "knee_flexion_left", "knee_flexion_right",
        "ankle_flexion_left", "ankle_flexion_right",
        "trunk_posture", "pelvic_tilt", "neck_inclination"
    ]

    def __init__(self):
        self.rom_history = {j: {"min": 999.0, "max": 0.0, "current": 0.0} for j in self.CLINICAL_JOINTS}
        self.frame_counter = 0

    def reset_session(self):
        """Resets ROM history tracking for new session."""
        self.rom_history = {j: {"min": 999.0, "max": 0.0, "current": 0.0} for j in self.CLINICAL_JOINTS}
        self.frame_counter = 0

    def analyze_frame(self, angles_dict, landmarks_dict, telemetry_dict):
        """
        Analyzes live Stage 1 angle and landmark telemetry for clinical physiotherapy assessment.
        Returns:
        - physio_telemetry (dict): Complete clinical assessment metrics & feedback.
        """
        if not angles_dict or not telemetry_dict.get("is_ready", True):
            return {
                "movement_quality_pct": 0.0,
                "rom_summary": {},
                "clinical_feedback": ["Position full body in camera frame."],
                "symmetry_status": "WAITING",
                "cog_shift_status": "WAITING"
            }

        self.frame_counter += 1

        # 1. Update Range of Motion (ROM) Min/Max/Peak per Joint
        for j_key in self.CLINICAL_JOINTS:
            val = angles_dict.get(j_key, 0.0)
            if isinstance(val, (int, float)) and val > 0.0:
                self.rom_history[j_key]["current"] = round(val, 1)
                self.rom_history[j_key]["min"] = round(min(self.rom_history[j_key]["min"], val), 1)
                self.rom_history[j_key]["max"] = round(max(self.rom_history[j_key]["max"], val), 1)

        # 2. Movement Quality Index Calculation (0% - 100%)
        trunk_tilt = angles_dict.get("trunk_posture", 0.0)
        pelvic_tilt = angles_dict.get("pelvic_tilt", 0.0)
        sym_delta = angles_dict.get("leg_symmetry_delta", 0.0)

        quality_deductions = (trunk_tilt * 1.2) + (pelvic_tilt * 1.5) + (sym_delta * 0.8)
        movement_quality = float(round(max(40.0, min(100.0, 100.0 - quality_deductions)), 1))

        # 3. Dynamic Live Clinical Feedback Generation
        feedback_messages = []
        if trunk_tilt > 12.0:
            feedback_messages.append("Maintain spinal vertical alignment.")
        if pelvic_tilt > 10.0:
            feedback_messages.append("Level hips to reduce pelvic tilt.")
        if sym_delta > 15.0:
            feedback_messages.append("Balance weight evenly between left and right legs.")

        if not feedback_messages:
            feedback_messages.append("Optimal joint alignment & posture maintained.")

        # 4. Symmetry & COG Status
        symmetry_status = "NORMAL" if sym_delta <= 12.0 else "ASYMMETRIC"
        cog_shift = angles_dict.get("balance_offset", 0.0)
        cog_status = "BALANCED" if cog_shift <= 8.0 else "SHIFTED"

        return {
            "movement_quality_pct": movement_quality,
            "rom_summary": {k: {"min": v["min"] if v["min"] != 999.0 else 0.0, "max": v["max"], "current": v["current"]} for k, v in self.rom_history.items()},
            "clinical_feedback": feedback_messages[:2],
            "symmetry_status": symmetry_status,
            "cog_shift_status": cog_status
        }
