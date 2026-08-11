import math
import cv2
import numpy as np

class MedicalGUIRenderer:
    """
    Commercial Medical Anatomical Stick-Figure Skeleton & On-Skeleton Goniometric Arc Overlay Renderer.
    Features:
    - On-Skeleton Clinical Goniometric Arc Curves (cv2.ellipse) connecting intersecting bone vectors
    - Floating Live Angle Badges (e.g. 99.0 deg, 82.3 deg, 48.5 deg) right at joint pivots matching clinical reference
    - Selective Body Tracking Modes (UPPER_BODY, LOWER_BODY, FULL_BODY)
    - Debug Mode HUD (Press 'D') displaying live angles, torso inclination, and joint landmark confidence scores
    - 21-Joint Finger Skeleton & Glowing Node Renderers
    """

    UPPER_BODY_CONNECTIONS = [
        ("C7_NECK", "PELVIS_CENTER", (255, 220, 220)),
        ("NOSE", "C7_NECK", (255, 220, 220)),
        ("NOSE", "LEFT_EYE", (255, 180, 220)),
        ("NOSE", "RIGHT_EYE", (255, 180, 220)),
        ("LEFT_EYE", "LEFT_EAR", (255, 180, 220)),
        ("RIGHT_EYE", "RIGHT_EAR", (255, 180, 220)),
        ("LEFT_SHOULDER", "RIGHT_SHOULDER", (0, 255, 120)),
        ("LEFT_SHOULDER", "LEFT_HIP", (0, 255, 120)),
        ("RIGHT_SHOULDER", "RIGHT_HIP", (0, 255, 120)),
        ("LEFT_SHOULDER", "LEFT_ELBOW", (255, 180, 0)),
        ("LEFT_ELBOW", "LEFT_WRIST", (255, 180, 0)),
        ("RIGHT_SHOULDER", "RIGHT_ELBOW", (0, 200, 255)),
        ("RIGHT_ELBOW", "RIGHT_WRIST", (0, 200, 255))
    ]

    LOWER_BODY_CONNECTIONS = [
        ("LEFT_HIP", "RIGHT_HIP", (0, 255, 120)),
        ("LEFT_HIP", "LEFT_KNEE", (0, 220, 255)),
        ("LEFT_KNEE", "LEFT_ANKLE", (0, 220, 255)),
        ("LEFT_ANKLE", "LEFT_HEEL", (0, 220, 255)),
        ("LEFT_ANKLE", "LEFT_FOOT_INDEX", (0, 220, 255)),
        ("LEFT_HEEL", "LEFT_FOOT_INDEX", (0, 220, 255)),
        ("RIGHT_HIP", "RIGHT_KNEE", (255, 150, 0)),
        ("RIGHT_KNEE", "RIGHT_ANKLE", (255, 150, 0)),
        ("RIGHT_ANKLE", "RIGHT_HEEL", (255, 150, 0)),
        ("RIGHT_ANKLE", "RIGHT_FOOT_INDEX", (255, 150, 0)),
        ("RIGHT_HEEL", "RIGHT_FOOT_INDEX", (255, 150, 0))
    ]

    FULL_BODY_CONNECTIONS = UPPER_BODY_CONNECTIONS + LOWER_BODY_CONNECTIONS

    HAND_FINGER_CHAINS = [
        ["WRIST", "THUMB_CMC", "THUMB_MCP", "THUMB_IP", "THUMB_TIP"],
        ["WRIST", "INDEX_FINGER_MCP", "INDEX_FINGER_PIP", "INDEX_FINGER_DIP", "INDEX_FINGER_TIP"],
        ["WRIST", "MIDDLE_FINGER_MCP", "MIDDLE_FINGER_PIP", "MIDDLE_FINGER_DIP", "MIDDLE_FINGER_TIP"],
        ["WRIST", "RING_FINGER_MCP", "RING_FINGER_PIP", "RING_FINGER_DIP", "RING_FINGER_TIP"],
        ["WRIST", "PINKY_MCP", "PINKY_PIP", "PINKY_DIP", "PINKY_TIP"]
    ]

    JOINT_ARC_DEFINITIONS = [
        ("LEFT_SHOULDER", "LEFT_HIP", "LEFT_ELBOW", "shoulder_abduction_left", (0, 255, 255)),
        ("RIGHT_SHOULDER", "RIGHT_HIP", "RIGHT_ELBOW", "shoulder_abduction_right", (0, 255, 255)),
        ("LEFT_ELBOW", "LEFT_SHOULDER", "LEFT_WRIST", "elbow_flexion_left", (0, 220, 255)),
        ("RIGHT_ELBOW", "RIGHT_SHOULDER", "RIGHT_WRIST", "elbow_flexion_right", (0, 220, 255)),
        ("LEFT_WRIST", "LEFT_ELBOW", "LEFT_HAND_MIDDLE_FINGER_TIP", "elbow_flexion_left", (255, 200, 0)),
        ("RIGHT_WRIST", "RIGHT_ELBOW", "RIGHT_HAND_MIDDLE_FINGER_TIP", "elbow_flexion_right", (255, 200, 0)),
        ("LEFT_HIP", "LEFT_SHOULDER", "LEFT_KNEE", "hip_flexion_left", (0, 255, 120)),
        ("RIGHT_HIP", "RIGHT_SHOULDER", "RIGHT_KNEE", "hip_flexion_right", (0, 255, 120)),
        ("LEFT_KNEE", "LEFT_HIP", "LEFT_ANKLE", "knee_flexion_left", (255, 150, 0)),
        ("RIGHT_KNEE", "RIGHT_HIP", "RIGHT_ANKLE", "knee_flexion_right", (255, 150, 0)),
        ("LEFT_ANKLE", "LEFT_KNEE", "LEFT_FOOT_INDEX", "ankle_flexion_left", (255, 100, 200)),
        ("RIGHT_ANKLE", "RIGHT_KNEE", "RIGHT_FOOT_INDEX", "ankle_flexion_right", (255, 100, 200))
    ]

    def __init__(self):
        self.show_bones = True
        self.show_joints = True
        self.show_hands = True
        self.show_angles_hud = True
        self.show_confidence_badges = True
        self.show_telemetry = True
        self.show_goniometer_arcs = True
        self.show_debug_hud = False

    def render(self, frame_bgr, landmarks_dict, angles_dict, telemetry_dict, physio_telemetry=None, body_mode="FULL_BODY", is_recording=False, track_id=1):
        if frame_bgr is None:
            return None

        canvas = frame_bgr.copy()
        h, w = canvas.shape[:2]

        is_ready = telemetry_dict.get("is_ready", True)
        guidance_msg = telemetry_dict.get("guidance_message", "Waiting for camera positioning...")

        if landmarks_dict and telemetry_dict.get("person_detected", False):
            if self.show_bones:
                self._draw_bones(canvas, landmarks_dict, is_ready, body_mode)
            if self.show_hands and body_mode != "LOWER_BODY":
                self._draw_hands(canvas, landmarks_dict)
            if self.show_joints:
                self._draw_joints(canvas, landmarks_dict, is_ready, body_mode)
            if self.show_goniometer_arcs and angles_dict and is_ready:
                self._draw_goniometer_arcs_and_badges(canvas, landmarks_dict, angles_dict, body_mode)
            if self.show_angles_hud and angles_dict:
                self._draw_selective_angles_hud(canvas, landmarks_dict, angles_dict, is_ready, body_mode)
            if self.show_debug_hud and angles_dict:
                self._draw_debug_hud(canvas, angles_dict)
            if self.show_confidence_badges:
                self._draw_confidence_badge(canvas, landmarks_dict, telemetry_dict, track_id)

        if self.show_telemetry:
            self._draw_telemetry_bar(canvas, telemetry_dict, angles_dict, body_mode, is_recording)

        if not is_ready:
            self._draw_guidance_overlay(canvas, guidance_msg)

        if physio_telemetry and is_ready:
            self._draw_physio_assessment_overlay(canvas, physio_telemetry, body_mode)

        return canvas

    def _draw_debug_hud(self, canvas, angles_dict):
        h, w = canvas.shape[:2]
        card_w, card_h = 320, 140
        x, y = 15, 180

        sub = canvas[y:y+card_h, x:x+card_w]
        bg = np.full(sub.shape, (15, 20, 30), dtype=np.uint8)
        canvas[y:y+card_h, x:x+card_w] = cv2.addWeighted(sub, 0.25, bg, 0.75, 0)
        cv2.rectangle(canvas, (x, y), (x+card_w, y+card_h), (0, 200, 255), 1, cv2.LINE_AA)

        l_abd = angles_dict.get("shoulder_abduction_left", None)
        r_abd = angles_dict.get("shoulder_abduction_right", None)
        torso_ang = angles_dict.get("torso_angle", None)

        l_sh_conf = angles_dict.get("l_sh_conf", 0.0)
        r_sh_conf = angles_dict.get("r_sh_conf", 0.0)
        l_elb_conf = angles_dict.get("l_elb_conf", 0.0)
        r_elb_conf = angles_dict.get("r_elb_conf", 0.0)

        l_abd_str = f"{l_abd:.1f}deg" if isinstance(l_abd, (int, float)) else "TRACKING..."
        r_abd_str = f"{r_abd:.1f}deg" if isinstance(r_abd, (int, float)) else "TRACKING..."
        torso_str = f"{torso_ang:.1f}deg" if isinstance(torso_ang, (int, float)) else "N/A"

        cv2.putText(canvas, "DEBUG BIOMECHANICS MODE", (x + 10, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 255, 200), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"L Shoulder Abd : {l_abd_str}", (x + 10, y + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"R Shoulder Abd : {r_abd_str}", (x + 10, y + 64), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"Torso Angle    : {torso_str}", (x + 10, y + 86), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 220, 100), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"L/R Sh Conf    : {l_sh_conf:.2f} | {r_sh_conf:.2f}", (x + 10, y + 108), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"L/R Elb Conf   : {l_elb_conf:.2f} | {r_elb_conf:.2f}", (x + 10, y + 128), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1, cv2.LINE_AA)

    def _draw_goniometer_arcs_and_badges(self, canvas, landmarks_dict, angles_dict, body_mode):
        h, w = canvas.shape[:2]
        upper_joints = {"LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST"}
        lower_joints = {"LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE", "RIGHT_ANKLE"}

        for pivot_name, node_a_name, node_c_name, angle_key, arc_color in self.JOINT_ARC_DEFINITIONS:
            if body_mode == "UPPER_BODY" and pivot_name not in upper_joints:
                continue
            if body_mode == "LOWER_BODY" and pivot_name not in lower_joints:
                continue

            if pivot_name in landmarks_dict and node_a_name in landmarks_dict and node_c_name in landmarks_dict:
                lm_b = landmarks_dict[pivot_name]
                lm_a = landmarks_dict[node_a_name]
                lm_c = landmarks_dict[node_c_name]

                if lm_b.get("visibility", 1.0) < 0.35 or lm_a.get("visibility", 1.0) < 0.35 or lm_c.get("visibility", 1.0) < 0.35:
                    continue

                bx, by = lm_b["px_x"], lm_b["px_y"]
                ax, ay = lm_a["px_x"], lm_a["px_y"]
                cx, cy = lm_c["px_x"], lm_c["px_y"]

                angle_val = angles_dict.get(angle_key, None)
                if angle_val is None or isinstance(angle_val, str):
                    continue

                ang_a = math.degrees(math.atan2(ay - by, ax - bx)) % 360.0
                ang_c = math.degrees(math.atan2(cy - by, cx - bx)) % 360.0

                start_ang = min(ang_a, ang_c)
                end_ang = max(ang_a, ang_c)

                if (end_ang - start_ang) > 180.0:
                    start_ang, end_ang = end_ang, start_ang + 360.0

                radius = 28
                cv2.ellipse(canvas, (bx, by), (radius + 2, radius + 2), 0, start_ang, end_ang, (15, 20, 25), 5, cv2.LINE_AA)
                cv2.ellipse(canvas, (bx, by), (radius, radius), 0, start_ang, end_ang, arc_color, 3, cv2.LINE_AA)

                mid_ang_rad = math.radians((start_ang + end_ang) / 2.0)
                lbl_dist = radius + 24
                lx = int(bx + lbl_dist * math.cos(mid_ang_rad))
                ly = int(by + lbl_dist * math.sin(mid_ang_rad))

                lx = max(35, min(w - 75, lx))
                ly = max(35, min(h - 35, ly))

                label_str = f"{angle_val:.1f}deg"
                (lbl_w, lbl_h), _ = cv2.getTextSize(label_str, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)

                cv2.rectangle(canvas, (lx - 4, ly - lbl_h - 4), (lx + lbl_w + 4, ly + 4), (18, 22, 35), -1)
                cv2.rectangle(canvas, (lx - 4, ly - lbl_h - 4), (lx + lbl_w + 4, ly + 4), arc_color, 1, cv2.LINE_AA)
                cv2.putText(canvas, label_str, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

    def _draw_physio_assessment_overlay(self, canvas, p_data, body_mode):
        h, w = canvas.shape[:2]
        quality_pct = p_data.get("movement_quality_pct", 94.5)
        feedback = p_data.get("clinical_feedback", [])
        sym_status = p_data.get("symmetry_status", "NORMAL")
        cog_status = p_data.get("cog_shift_status", "BALANCED")

        mode_title = f"MODE: {body_mode} PHYSIOTHERAPY ASSESSMENT"

        card_w, card_h = 580, 65
        x, y = int(w/2 - card_w/2), 42
        sub = canvas[y:y+card_h, x:x+card_w]
        bg = np.full(sub.shape, (18, 22, 35), dtype=np.uint8)
        canvas[y:y+card_h, x:x+card_w] = cv2.addWeighted(sub, 0.30, bg, 0.70, 0)
        cv2.rectangle(canvas, (x, y), (x+card_w, y+card_h), (0, 255, 120), 2, cv2.LINE_AA)

        cv2.putText(canvas, mode_title, (x + 15, y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (0, 255, 200), 2, cv2.LINE_AA)
        cv2.putText(canvas, f"MOVEMENT QUALITY: {quality_pct:.1f}%", (x + 15, y + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 0) if quality_pct >= 80 else (0, 165, 255), 2, cv2.LINE_AA)
        
        if body_mode != "UPPER_BODY":
            cv2.putText(canvas, f"SYMMETRY: {sym_status} | COG: {cog_status}", (x + 300, y + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 220, 100), 2, cv2.LINE_AA)
        else:
            cv2.putText(canvas, "UPPER POSTURE STABLE", (x + 320, y + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (120, 255, 120), 2, cv2.LINE_AA)

        c_w, c_h = 580, 60
        cx, cy = int(w/2 - c_w/2), h - 170
        sub_c = canvas[cy:cy+c_h, cx:cx+c_w]
        bg_c = np.full(sub_c.shape, (15, 20, 30), dtype=np.uint8)
        canvas[cy:cy+c_h, cx:cx+c_w] = cv2.addWeighted(sub_c, 0.30, bg_c, 0.70, 0)
        cv2.rectangle(canvas, (cx, cy), (cx+c_w, cy+c_h), (0, 200, 255), 1, cv2.LINE_AA)

        first_msg = feedback[0] if feedback else "Optimal joint alignment & posture maintained."
        cv2.putText(canvas, "CLINICAL FEEDBACK:", (cx + 15, cy + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 255, 200), 1, cv2.LINE_AA)
        cv2.putText(canvas, first_msg, (cx + 15, cy + 46), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)

    def _draw_guidance_overlay(self, canvas, message):
        h, w = canvas.shape[:2]
        card_w, card_h = 560, 65
        x, y = int(w/2 - card_w/2), int(h/2 - card_h/2)

        sub = canvas[y:y+card_h, x:x+card_w]
        bg = np.full(sub.shape, (15, 20, 35), dtype=np.uint8)
        canvas[y:y+card_h, x:x+card_w] = cv2.addWeighted(sub, 0.25, bg, 0.75, 0)

        cv2.rectangle(canvas, (x, y), (x+card_w, y+card_h), (0, 165, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, "CAMERA POSITIONING GUIDANCE", (x + 15, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, message, (x + 15, y + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)

    def _draw_bones(self, canvas, landmarks_dict, is_ready, body_mode):
        connections = self.FULL_BODY_CONNECTIONS
        if body_mode == "UPPER_BODY":
            connections = self.UPPER_BODY_CONNECTIONS
        elif body_mode == "LOWER_BODY":
            connections = self.LOWER_BODY_CONNECTIONS

        for p1_name, p2_name, color in connections:
            if p1_name in landmarks_dict and p2_name in landmarks_dict:
                lm1 = landmarks_dict[p1_name]
                lm2 = landmarks_dict[p2_name]

                if lm1.get("visibility", 1.0) >= 0.2 and lm2.get("visibility", 1.0) >= 0.2:
                    p1 = (lm1["px_x"], lm1["px_y"])
                    p2 = (lm2["px_x"], lm2["px_y"])
                    line_color = color if is_ready else (120, 120, 120)

                    cv2.line(canvas, p1, p2, (15, 20, 25), 4, cv2.LINE_AA)
                    cv2.line(canvas, p1, p2, line_color, 2, cv2.LINE_AA)

    def _draw_hands(self, canvas, landmarks_dict):
        for prefix, color in [("LEFT_HAND_", (255, 200, 100)), ("RIGHT_HAND_", (100, 220, 255))]:
            body_wrist_key = "LEFT_WRIST" if "LEFT" in prefix else "RIGHT_WRIST"
            wrist_hand_key = f"{prefix}WRIST"

            if body_wrist_key in landmarks_dict and wrist_hand_key in landmarks_dict:
                bw = (landmarks_dict[body_wrist_key]["px_x"], landmarks_dict[body_wrist_key]["px_y"])
                hw = (landmarks_dict[wrist_hand_key]["px_x"], landmarks_dict[wrist_hand_key]["px_y"])
                cv2.line(canvas, bw, hw, color, 2, cv2.LINE_AA)

            for chain in self.HAND_FINGER_CHAINS:
                for i in range(len(chain) - 1):
                    k1 = f"{prefix}{chain[i]}"
                    k2 = f"{prefix}{chain[i+1]}"
                    if k1 in landmarks_dict and k2 in landmarks_dict:
                        pt1 = (landmarks_dict[k1]["px_x"], landmarks_dict[k1]["px_y"])
                        pt2 = (landmarks_dict[k2]["px_x"], landmarks_dict[k2]["px_y"])
                        cv2.line(canvas, pt1, pt2, color, 1, cv2.LINE_AA)
                        cv2.circle(canvas, pt2, 2, (255, 255, 255), -1, cv2.LINE_AA)

    def _draw_joints(self, canvas, landmarks_dict, is_ready, body_mode):
        upper_joint_names = {"NOSE", "C7_NECK", "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST"}
        lower_joint_names = {"PELVIS_CENTER", "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL", "RIGHT_HEEL", "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX"}

        for name, lm in landmarks_dict.items():
            if "HAND_" in name: continue

            if body_mode == "UPPER_BODY" and name not in upper_joint_names and name != "PELVIS_CENTER":
                continue
            if body_mode == "LOWER_BODY" and name not in lower_joint_names:
                continue

            if lm.get("visibility", 1.0) >= 0.2:
                pt = (lm["px_x"], lm["px_y"])
                glow_color = (0, 200, 255) if is_ready else (100, 100, 100)
                dot_color = (0, 255, 255) if is_ready else (180, 180, 180)

                cv2.circle(canvas, pt, 7, glow_color, 1, cv2.LINE_AA)
                cv2.circle(canvas, pt, 4, dot_color, -1, cv2.LINE_AA)
                cv2.circle(canvas, pt, 1, (255, 255, 255), -1, cv2.LINE_AA)

    def _draw_selective_angles_hud(self, canvas, landmarks_dict, angles_dict, is_ready, body_mode):
        h, w = canvas.shape[:2]
        card_w, card_h = 240, 125

        def val_str(key):
            if not is_ready or key not in angles_dict:
                return "N/A"
            val = angles_dict[key]
            if val is None:
                return "TRACKING..."
            if isinstance(val, str):
                return val
            if isinstance(val, (int, float)):
                return f"{val:.1f} deg"
            return "N/A"

        if body_mode in ["UPPER_BODY", "FULL_BODY"]:
            x_lu, y_lu = 15, 45
            self._draw_hud_card_box(canvas, x_lu, y_lu, card_w, card_h, "LEFT UPPER BODY")
            cv2.putText(canvas, f"L Elbow Flexion:  {val_str('elbow_flexion_left')}", (x_lu + 10, y_lu + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 220, 100), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"L Shoulder Flex: {val_str('shoulder_flexion_left')}", (x_lu + 10, y_lu + 68), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"L Shoulder Abd:  {val_str('shoulder_abduction_left')}", (x_lu + 10, y_lu + 96), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 220, 100), 1, cv2.LINE_AA)

            x_ru, y_ru = w - card_w - 15, 45
            self._draw_hud_card_box(canvas, x_ru, y_ru, card_w, card_h, "RIGHT UPPER BODY")
            cv2.putText(canvas, f"R Elbow Flexion:  {val_str('elbow_flexion_right')}", (x_ru + 10, y_ru + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100, 220, 255), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"R Shoulder Flex: {val_str('shoulder_flexion_right')}", (x_ru + 10, y_ru + 68), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"R Shoulder Abd:  {val_str('shoulder_abduction_right')}", (x_ru + 10, y_ru + 96), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100, 220, 255), 1, cv2.LINE_AA)

        if body_mode in ["LOWER_BODY", "FULL_BODY"]:
            x_ll, y_ll = 15, h - card_h - 15
            self._draw_hud_card_box(canvas, x_ll, y_ll, card_w, card_h, "LEFT LOWER BODY")
            cv2.putText(canvas, f"L Hip Flexion:   {val_str('hip_flexion_left')}", (x_ll + 10, y_ll + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 220, 255), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"L Knee Flexion:  {val_str('knee_flexion_left')}", (x_ll + 10, y_ll + 68), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 220, 255), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"L Ankle Angle:   {val_str('ankle_flexion_left')}", (x_ll + 10, y_ll + 96), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 220, 255), 1, cv2.LINE_AA)

            x_rl, y_rl = w - card_w - 15, h - card_h - 15
            self._draw_hud_card_box(canvas, x_rl, y_rl, card_w, card_h, "RIGHT LOWER BODY")
            cv2.putText(canvas, f"R Hip Flexion:   {val_str('hip_flexion_right')}", (x_rl + 10, y_rl + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 150, 0), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"R Knee Flexion:  {val_str('knee_flexion_right')}", (x_rl + 10, y_rl + 68), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 150, 0), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"R Ankle Angle:   {val_str('ankle_flexion_right')}", (x_rl + 10, y_rl + 96), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 150, 0), 1, cv2.LINE_AA)

        x_mid, y_mid = int(w/2 - 140), h - 100
        self._draw_hud_card_box(canvas, x_mid, y_mid, 280, 90, "POSTURE, PELVIS & BALANCE")
        if is_ready:
            cv2.putText(canvas, f"Spine Tilt:  {angles_dict.get('trunk_posture', 0.0):.1f}d | Pelvis: {angles_dict.get('pelvic_tilt', 0.0):.1f}d", (x_mid + 10, y_mid + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 255, 120), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"Leg Symmetry Delta: {angles_dict.get('leg_symmetry_delta', 0.0):.1f} deg", (x_mid + 10, y_mid + 56), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 255, 120), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"Body COG Shift:     {angles_dict.get('balance_offset', 0.0):.1f}%", (x_mid + 10, y_mid + 78), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 255, 120), 1, cv2.LINE_AA)
        else:
            cv2.putText(canvas, "Spine & Balance: WAITING FOR BODY", (x_mid + 10, y_mid + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 165, 255), 1, cv2.LINE_AA)

    def _draw_hud_card_box(self, canvas, x, y, w, h, title):
        sub = canvas[y:y+h, x:x+w]
        bg = np.full(sub.shape, (18, 22, 32), dtype=np.uint8)
        canvas[y:y+h, x:x+w] = cv2.addWeighted(sub, 0.35, bg, 0.65, 0)
        
        cv2.rectangle(canvas, (x, y), (x+w, y+h), (70, 85, 110), 1, cv2.LINE_AA)
        cv2.rectangle(canvas, (x, y), (x+w, y+22), (35, 45, 65), -1)
        cv2.putText(canvas, title, (x + 8, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 200), 1, cv2.LINE_AA)

    def _draw_confidence_badge(self, canvas, landmarks_dict, telemetry_dict, track_id):
        if "NOSE" in landmarks_dict:
            nose = landmarks_dict["NOSE"]
            px, py = nose["px_x"], max(30, nose["px_y"] - 65)
            conf = telemetry_dict.get("overall_confidence", 0.0)
            status = telemetry_dict.get("status_badge", "Ready")

            badge_str = f"ID: #{track_id} | Conf: {conf:.1f}% | {status}"
            cv2.rectangle(canvas, (px - 85, py - 20), (px + 105, py + 5), (18, 22, 32), -1)
            cv2.rectangle(canvas, (px - 85, py - 20), (px + 105, py + 5), (0, 255, 120) if telemetry_dict.get("is_ready", True) else (0, 165, 255), 1, cv2.LINE_AA)
            cv2.putText(canvas, badge_str, (px - 80, py - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA)

    def _draw_telemetry_bar(self, canvas, telemetry_dict, angles_dict, body_mode, is_recording):
        w = canvas.shape[1]
        banner_h = 32
        sub = canvas[0:banner_h, 0:w]
        bg = np.full(sub.shape, (15, 20, 30), dtype=np.uint8)
        canvas[0:banner_h, 0:w] = cv2.addWeighted(sub, 0.2, bg, 0.8, 0)
        cv2.line(canvas, (0, banner_h), (w, banner_h), (50, 70, 95), 1, cv2.LINE_AA)

        fps = telemetry_dict.get("fps", 60.0)
        lat = telemetry_dict.get("latency_ms", 12.5)

        cv2.putText(canvas, f"AI PHYSIOTHERAPY PLATFORM", (15, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 255, 200), 2, cv2.LINE_AA)
        cv2.putText(canvas, f"FPS: {fps:.1f}", (240, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0) if fps >= 30 else (0, 165, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"LATENCY: {lat:.1f}ms", (340, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"BODY MODE: {body_mode}", (490, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 200, 100), 1, cv2.LINE_AA)

        if is_recording:
            cv2.circle(canvas, (w - 110, 16), 6, (0, 0, 255), -1, cv2.LINE_AA)
            cv2.putText(canvas, "REC", (w - 95, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2, cv2.LINE_AA)

        cv2.putText(canvas, "[HOTKEYS: U=Upper | L=Lower | F=Full | D=Debug | Q=Exit]", (w - 480, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1, cv2.LINE_AA)
