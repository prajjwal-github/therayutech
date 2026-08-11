import os
import math
import random
import json
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFilter

class SyntheticUpperBodyGenerator:
    """
    Procedural Synthetic Upper-Body Human Image Generator.
    Generates diverse static human upper-body images adhering to a matrix of:
    - Poses (Arms down, arms up, T-pose, elbow flexions, cross-body, physio poses)
    - Views (Front 0°, 3/4 view 30°-60°, Side view 90°)
    - Distances (Close 1.2m, Medium 2.5m, Far 4.0m)
    - Clothing (T-shirt, tank top, long sleeve, physiotherapy gear)
    - Skin tones, hair styles, lighting, and realistic room backgrounds.
    """
    
    POSE_CLASSES = [
        "ARMS_DOWN",
        "ARMS_UP",
        "LEFT_ARM_UP",
        "RIGHT_ARM_UP",
        "ARMS_SIDEWAYS",
        "PARTIAL_RAISE_LEFT",
        "PARTIAL_RAISE_RIGHT",
        "ELBOW_FLEXED_LEFT",
        "ELBOW_FLEXED_RIGHT",
        "CROSS_BODY_LEFT",
        "CROSS_BODY_RIGHT",
        "ASYMMETRIC_PHYSIO"
    ]

    SKIN_TONES = [
        (255, 224, 189), # Fair
        (240, 195, 150), # Light warm
        (210, 160, 110), # Medium tan
        (160, 105, 60),  # Olive/Brown
        (110, 65, 35),   # Dark brown
        (75, 40, 20)     # Deep dark
    ]

    CLOTHING_COLORS = [
        (40, 80, 160),  # Royal Blue
        (180, 40, 50),   # Crimson
        (40, 140, 70),   # Forest Green
        (80, 80, 80),    # Slate Gray
        (220, 220, 220), # Off-white
        (30, 30, 30),    # Charcoal
        (160, 60, 160),  # Purple
        (210, 130, 40)   # Amber
    ]

    BACKGROUND_TYPES = ["PHYSIO_ROOM", "GYM", "LIVING_ROOM", "OFFICE", "NEUTRAL_WALL"]

    def __init__(self, output_dir="dataset/generated", img_size=(800, 800)):
        self.output_dir = output_dir
        self.img_width, self.img_height = img_size
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "annotations"), exist_ok=True)

    def generate_background(self, bg_type):
        """Creates realistic background images."""
        img = np.zeros((self.img_height, self.img_width, 3), dtype=np.uint8)
        
        if bg_type == "NEUTRAL_WALL":
            base_color = random.choice([
                (230, 230, 225), (210, 215, 220), (225, 220, 210), (190, 200, 205)
            ])
            img[:] = base_color
            # Subtle gradient
            gradient = np.linspace(1.0, 0.85, self.img_height).reshape(self.img_height, 1, 1)
            img = (img * gradient).astype(np.uint8)

        elif bg_type == "PHYSIO_ROOM":
            # Wall + Floor split
            wall_color = (220, 235, 240) # Soft medical blue
            floor_color = (180, 160, 140) # Light wood/vinyl
            split_y = int(self.img_height * 0.7)
            img[:split_y] = wall_color
            img[split_y:] = floor_color
            # Baseboard line
            cv2.line(img, (0, split_y), (self.img_width, split_y), (120, 100, 80), 4)

        elif bg_type == "GYM":
            # Dark gym aesthetic
            img[:int(self.img_height * 0.75)] = (40, 45, 50)
            img[int(self.img_height * 0.75):] = (25, 25, 30)
            cv2.line(img, (0, int(self.img_height * 0.75)), (self.img_width, int(self.img_height * 0.75)), (60, 65, 70), 3)

        elif bg_type == "LIVING_ROOM":
            img[:int(self.img_height * 0.65)] = (235, 225, 215) # Warm beige
            img[int(self.img_height * 0.65):] = (140, 100, 70)  # Wood floor
            cv2.line(img, (0, int(self.img_height * 0.65)), (self.img_width, int(self.img_height * 0.65)), (90, 60, 40), 5)

        else: # OFFICE
            img[:int(self.img_height * 0.7)] = (215, 220, 225)
            img[int(self.img_height * 0.7):] = (160, 170, 180)
            cv2.line(img, (0, int(self.img_height * 0.7)), (self.img_width, int(self.img_height * 0.7)), (110, 120, 130), 4)

        # Add random subtle lighting gradient
        light_x = random.randint(0, self.img_width)
        light_y = random.randint(0, int(self.img_height * 0.5))
        Y, X = np.ogrid[:self.img_height, :self.img_width]
        dist_from_light = np.sqrt((X - light_x)**2 + (Y - light_y)**2)
        max_dist = np.sqrt(self.img_width**2 + self.img_height**2)
        light_factor = 1.15 - (dist_from_light / max_dist) * 0.35
        light_factor = np.clip(light_factor, 0.7, 1.25)[:, :, np.newaxis]
        img = np.clip(img * light_factor, 0, 255).astype(np.uint8)

        return img

    def get_pose_joint_angles(self, pose_class):
        """Returns target joint angles (degrees) for given pose class."""
        # Standard angles: shoulder_l, shoulder_r, elbow_l, elbow_r
        # 0° shoulder = down, 90° = horizontal, 180° = straight up overhead
        # 0° elbow = straight, 90° = bent at right angle, 140° = acute bend
        
        if pose_class == "ARMS_DOWN":
            s_l, s_r = random.uniform(5, 20), random.uniform(5, 20)
            e_l, e_r = random.uniform(0, 15), random.uniform(0, 15)
        elif pose_class == "ARMS_UP":
            s_l, s_r = random.uniform(160, 180), random.uniform(160, 180)
            e_l, e_r = random.uniform(0, 20), random.uniform(0, 20)
        elif pose_class == "LEFT_ARM_UP":
            s_l, s_r = random.uniform(150, 180), random.uniform(5, 25)
            e_l, e_r = random.uniform(0, 20), random.uniform(0, 20)
        elif pose_class == "RIGHT_ARM_UP":
            s_l, s_r = random.uniform(5, 25), random.uniform(150, 180)
            e_l, e_r = random.uniform(0, 20), random.uniform(0, 20)
        elif pose_class == "ARMS_SIDEWAYS": # T-Pose
            s_l, s_r = random.uniform(80, 100), random.uniform(80, 100)
            e_l, e_r = random.uniform(0, 15), random.uniform(0, 15)
        elif pose_class == "PARTIAL_RAISE_LEFT":
            s_l = random.choice([30, 45, 60, 120, 140]) + random.uniform(-10, 10)
            s_r = random.uniform(5, 25)
            e_l, e_r = random.uniform(0, 25), random.uniform(0, 20)
        elif pose_class == "PARTIAL_RAISE_RIGHT":
            s_l = random.uniform(5, 25)
            s_r = random.choice([30, 45, 60, 120, 140]) + random.uniform(-10, 10)
            e_l, e_r = random.uniform(0, 20), random.uniform(0, 25)
        elif pose_class == "ELBOW_FLEXED_LEFT":
            s_l, s_r = random.uniform(30, 90), random.uniform(5, 25)
            e_l = random.uniform(70, 130)
            e_r = random.uniform(0, 20)
        elif pose_class == "ELBOW_FLEXED_RIGHT":
            s_l, s_r = random.uniform(5, 25), random.uniform(30, 90)
            e_l = random.uniform(0, 20)
            e_r = random.uniform(70, 130)
        elif pose_class == "CROSS_BODY_LEFT":
            s_l, s_r = random.uniform(40, 80), random.uniform(5, 25)
            e_l = random.uniform(90, 140)
            e_r = random.uniform(0, 20)
        elif pose_class == "CROSS_BODY_RIGHT":
            s_l, s_r = random.uniform(5, 25), random.uniform(40, 80)
            e_l = random.uniform(0, 20)
            e_r = random.uniform(90, 140)
        else: # ASYMMETRIC_PHYSIO
            s_l = random.uniform(30, 160)
            s_r = random.uniform(10, 120)
            e_l = random.uniform(20, 110)
            e_r = random.uniform(10, 100)

        return s_l, s_r, e_l, e_r

    def render_procedural_human(self, img, pose_class, camera_distance="MEDIUM", view_angle="FRONT"):
        """
        Renders an anatomically accurate 3D/2D procedural human upper body with skin, clothing, and features.
        Returns the rendered image and dictionary of ground truth landmark 2D coordinates.
        """
        h, w = img.shape[:2]

        # Camera distance scaling
        if camera_distance == "CLOSE": # Upper torso framing
            scale = random.uniform(1.3, 1.5)
            center_y = int(h * 0.55)
        elif camera_distance == "FAR": # Full upper body + hips
            scale = random.uniform(0.7, 0.85)
            center_y = int(h * 0.45)
        else: # MEDIUM
            scale = random.uniform(0.95, 1.1)
            center_y = int(h * 0.50)

        center_x = int(w * 0.5) + random.randint(-30, 30)

        # Body dimensions (in pixels at scale=1.0)
        head_radius = int(45 * scale)
        neck_length = int(25 * scale)
        shoulder_width = int(140 * scale)
        torso_height = int(210 * scale)
        upper_arm_length = int(115 * scale)
        forearm_length = int(105 * scale)
        hip_width = int(110 * scale)

        # Yaw rotation (View angle)
        if view_angle == "SIDE_LEFT":
            yaw = -math.radians(70 + random.uniform(-10, 10))
        elif view_angle == "SIDE_RIGHT":
            yaw = math.radians(70 + random.uniform(-10, 10))
        elif view_angle == "THREE_QUARTER_LEFT":
            yaw = -math.radians(35 + random.uniform(-10, 10))
        elif view_angle == "THREE_QUARTER_RIGHT":
            yaw = math.radians(35 + random.uniform(-10, 10))
        else: # FRONT
            yaw = math.radians(random.uniform(-8, 8))

        # Skin and clothing colors
        skin_color = random.choice(self.SKIN_TONES)
        shirt_color = random.choice(self.CLOTHING_COLORS)
        pant_color = random.choice([(40, 40, 50), (30, 50, 90), (60, 60, 60)])
        hair_color = random.choice([(20, 20, 20), (50, 30, 15), (140, 90, 40), (190, 160, 80)])

        # Calculate Joint Anchors (3D)
        # Head / Neck / Spine
        head_center = np.array([center_x, center_y - torso_height * 0.5 - neck_length - head_radius, 0.0])
        neck_base = np.array([center_x, center_y - torso_height * 0.5, 0.0])
        hip_center = np.array([center_x, center_y + torso_height * 0.5, 0.0])

        # Shoulders (with yaw rotation)
        ls_3d = neck_base + np.array([-shoulder_width * 0.5 * math.cos(yaw), 0.0, shoulder_width * 0.5 * math.sin(yaw)])
        rs_3d = neck_base + np.array([shoulder_width * 0.5 * math.cos(yaw), 0.0, -shoulder_width * 0.5 * math.sin(yaw)])

        # Hips (with yaw rotation)
        lh_3d = hip_center + np.array([-hip_width * 0.5 * math.cos(yaw), 0.0, hip_width * 0.5 * math.sin(yaw)])
        rh_3d = hip_center + np.array([hip_width * 0.5 * math.cos(yaw), 0.0, -hip_width * 0.5 * math.sin(yaw)])

        # Target Arm Angles
        s_l_deg, s_r_deg, e_l_deg, e_r_deg = self.get_pose_joint_angles(pose_class)

        # Convert angles to 3D positions
        def compute_arm_joints(shoulder_3d, shoulder_deg, elbow_deg, is_left=True):
            side = -1.0 if is_left else 1.0
            s_rad = math.radians(shoulder_deg)
            e_rad = math.radians(elbow_deg)

            # Upper arm direction (rotation from down vector [0, 1, 0])
            # In front view: raising arm up rotates in XY plane
            ux = side * math.sin(s_rad) * math.cos(yaw)
            uy = math.cos(s_rad)
            uz = side * math.sin(s_rad) * math.sin(yaw)
            u_dir = np.array([ux, uy, uz])
            u_dir = u_dir / np.linalg.norm(u_dir)
            elbow_3d = shoulder_3d + u_dir * upper_arm_length

            # Forearm direction with elbow flexion
            # Forearm bends inward toward torso or upward
            fx = ux * math.cos(e_rad) - side * math.sin(e_rad) * 0.7 * math.cos(yaw)
            fy = uy * math.cos(e_rad) - math.sin(e_rad) * 0.7
            fz = uz * math.cos(e_rad) - side * math.sin(e_rad) * 0.7 * math.sin(yaw)
            f_dir = np.array([fx, fy, fz])
            f_dir = f_dir / np.linalg.norm(f_dir)
            wrist_3d = elbow_3d + f_dir * forearm_length

            return elbow_3d, wrist_3d

        le_3d, lw_3d = compute_arm_joints(ls_3d, s_l_deg, e_l_deg, is_left=True)
        re_3d, rw_3d = compute_arm_joints(rs_3d, s_r_deg, e_r_deg, is_left=False)

        # Head facial features relative to head_center
        nose_3d = head_center + np.array([15 * math.sin(yaw), 5, -head_radius * 0.8 * math.cos(yaw)])
        l_eye_3d = head_center + np.array([-18 * math.cos(yaw) + 10 * math.sin(yaw), -10, -head_radius * 0.75])
        r_eye_3d = head_center + np.array([18 * math.cos(yaw) + 10 * math.sin(yaw), -10, -head_radius * 0.75])
        l_ear_3d = head_center + np.array([-head_radius * 0.95 * math.cos(yaw), 0, 0])
        r_ear_3d = head_center + np.array([head_radius * 0.95 * math.cos(yaw), 0, 0])

        # Project 3D points to 2D image coordinates (orthographic / weak perspective)
        def project(p3d):
            return (int(p3d[0]), int(p3d[1]))

        p_head = project(head_center)
        p_neck = project(neck_base)
        p_hip_c = project(hip_center)
        p_ls = project(ls_3d)
        p_rs = project(rs_3d)
        p_lh = project(lh_3d)
        p_rh = project(rh_3d)
        p_le = project(le_3d)
        p_lw = project(lw_3d)
        p_re = project(re_3d)
        p_rw = project(rw_3d)
        p_nose = project(nose_3d)
        p_l_eye = project(l_eye_3d)
        p_r_eye = project(r_eye_3d)
        p_l_ear = project(l_ear_3d)
        p_r_ear = project(r_ear_3d)

        # --- DRAW HUMAN BODY (Back to Front depth sorting) ---

        # Convert OpenCV BGR to RGB for PIL drawing, then convert back
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        # 1. Torso & Clothing
        torso_poly = [p_ls, p_rs, p_rh, p_lh]
        draw.polygon(torso_poly, fill=shirt_color)

        # 2. Pants / Hip region
        pant_poly = [p_lh, p_rh, (p_rh[0], p_rh[1] + int(80*scale)), (p_lh[0], p_lh[1] + int(80*scale))]
        draw.polygon(pant_poly, fill=pant_color)

        # Helper to draw realistic tapered limb capsule
        def draw_limb(p1, p2, r1, r2, color):
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            length = math.hypot(dx, dy)
            if length == 0: return
            ux, uy = -dy / length, dx / length
            
            poly = [
                (int(p1[0] + ux * r1), int(p1[1] + uy * r1)),
                (int(p2[0] + ux * r2), int(p2[1] + uy * r2)),
                (int(p2[0] - ux * r2), int(p2[1] - uy * r2)),
                (int(p1[0] - ux * r1), int(p1[1] - uy * r1))
            ]
            draw.polygon(poly, fill=color)
            draw.ellipse([p1[0]-r1, p1[1]-r1, p1[0]+r1, p1[1]+r1], fill=color)
            draw.ellipse([p2[0]-r2, p2[1]-r2, p2[0]+r2, p2[1]+r2], fill=color)

        # Arm Radius
        u_arm_r = int(24 * scale)
        f_arm_r = int(19 * scale)
        hand_r = int(18 * scale)

        # Sort arms by Z depth
        arms = [
            (ls_3d[2], "LEFT", p_ls, p_le, p_lw),
            (rs_3d[2], "RIGHT", p_rs, p_re, p_rw)
        ]
        arms.sort(key=lambda item: item[0]) # draw farther arm first

        for _, side_name, p_s, p_e, p_w in arms:
            # Sleeves & Skin
            draw_limb(p_s, p_e, u_arm_r, int(u_arm_r*0.85), shirt_color)
            draw_limb(p_e, p_w, f_arm_r, int(f_arm_r*0.8), skin_color)
            # Hand
            draw.ellipse([p_w[0]-hand_r, p_w[1]-hand_r, p_w[0]+hand_r, p_w[1]+hand_r], fill=skin_color)

        # 3. Neck
        draw_limb(p_neck, p_head, int(20*scale), int(20*scale), skin_color)

        # 4. Head
        h_left, h_top = p_head[0] - head_radius, p_head[1] - head_radius
        h_right, h_bottom = p_head[0] + head_radius, p_head[1] + head_radius
        draw.ellipse([h_left, h_top, h_right, h_bottom], fill=skin_color)

        # Hair
        hair_poly = [
            (p_head[0] - head_radius - 4, p_head[1]),
            (p_head[0] - head_radius - 2, p_head[1] - head_radius - 8),
            (p_head[0] + head_radius + 2, p_head[1] - head_radius - 8),
            (p_head[0] + head_radius + 4, p_head[1])
        ]
        draw.polygon(hair_poly, fill=hair_color)

        # High-contrast Face details for detector (Eyes, Eyebrows, Nose, Mouth)
        eye_r = max(3, int(5 * scale))
        draw.ellipse([p_l_eye[0]-eye_r, p_l_eye[1]-eye_r, p_l_eye[0]+eye_r, p_l_eye[1]+eye_r], fill=(20, 20, 20))
        draw.ellipse([p_r_eye[0]-eye_r, p_r_eye[1]-eye_r, p_r_eye[0]+eye_r, p_r_eye[1]+eye_r], fill=(20, 20, 20))
        # Eyebrows
        draw.line([(p_l_eye[0]-eye_r*2, p_l_eye[1]-eye_r-3), (p_l_eye[0]+eye_r*2, p_l_eye[1]-eye_r-4)], fill=hair_color, width=3)
        draw.line([(p_r_eye[0]-eye_r*2, p_r_eye[1]-eye_r-4), (p_r_eye[0]+eye_r*2, p_r_eye[1]-eye_r-3)], fill=hair_color, width=3)
        # Nose
        draw.polygon([p_nose, (p_nose[0]-4, p_nose[1]+10), (p_nose[0]+4, p_nose[1]+10)], fill=(int(skin_color[0]*0.75), int(skin_color[1]*0.75), int(skin_color[2]*0.75)))
        # Mouth
        mouth_y = p_nose[1] + int(18 * scale)
        draw.line([(p_head[0]-int(15*scale), mouth_y), (p_head[0]+int(15*scale), mouth_y)], fill=(160, 50, 50), width=3)

        # Convert back to OpenCV BGR
        rendered_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # Apply realistic lighting shadow / mild gaussian blur to blend edges
        rendered_img = cv2.GaussianBlur(rendered_img, (3, 3), 0.5)

        # Keypoints dictionary
        landmarks = {
            "NOSE": p_nose,
            "LEFT_EYE": p_l_eye,
            "RIGHT_EYE": p_r_eye,
            "LEFT_EAR": p_l_ear,
            "RIGHT_EAR": p_r_ear,
            "LEFT_SHOULDER": p_ls,
            "RIGHT_SHOULDER": p_rs,
            "LEFT_ELBOW": p_le,
            "RIGHT_ELBOW": p_re,
            "LEFT_WRIST": p_lw,
            "RIGHT_WRIST": p_rw,
            "LEFT_HIP": p_lh,
            "RIGHT_HIP": p_rh
        }

        metadata = {
            "pose_class": pose_class,
            "camera_distance": camera_distance,
            "view_angle": view_angle,
            "angles": {
                "shoulder_left": s_l_deg,
                "shoulder_right": s_r_deg,
                "elbow_left": e_l_deg,
                "elbow_right": e_r_deg
            }
        }

        return rendered_img, landmarks, metadata

    def generate_batch(self, count=1000, target_dir=None):
        """Generates a balanced batch of synthetic upper-body images."""
        if target_dir is None:
            target_dir = self.output_dir
        
        os.makedirs(target_dir, exist_ok=True)
        anno_dir = os.path.join(target_dir, "annotations")
        os.makedirs(anno_dir, exist_ok=True)

        print(f"[INFO] Generating {count} synthetic upper-body images...")

        generated_samples = []

        distances = ["CLOSE", "MEDIUM", "FAR"]
        views = ["FRONT", "THREE_QUARTER_LEFT", "THREE_QUARTER_RIGHT", "SIDE_LEFT", "SIDE_RIGHT"]

        for i in range(count):
            pose_class = self.POSE_CLASSES[i % len(self.POSE_CLASSES)]
            dist = distances[(i // len(self.POSE_CLASSES)) % len(distances)]
            view = views[(i // (len(self.POSE_CLASSES) * len(distances))) % len(views)]
            bg_type = random.choice(self.BACKGROUND_TYPES)

            # Generate base scene background
            bg_img = self.generate_background(bg_type)

            # Render synthetic human
            rendered_img, landmarks, meta = self.render_procedural_human(
                bg_img, pose_class=pose_class, camera_distance=dist, view_angle=view
            )

            # Save Image
            filename = f"upper_body_{i+1:05d}_{pose_class.lower()}.jpg"
            img_path = os.path.join(target_dir, filename)
            cv2.imwrite(img_path, rendered_img)

            # Save Ground Truth Annotation
            anno_path = os.path.join(anno_dir, f"upper_body_{i+1:05d}_{pose_class.lower()}.json")
            annotation_data = {
                "image_filename": filename,
                "image_path": img_path,
                "image_size": [self.img_width, self.img_height],
                "pose_class": pose_class,
                "metadata": meta,
                "landmarks": {k: [int(v[0]), int(v[1])] for k, v in landmarks.items()}
            }

            with open(anno_path, "w") as f:
                json.dump(annotation_data, f, indent=2)

            generated_samples.append((img_path, anno_path))

            if (i + 1) % 200 == 0 or (i + 1) == count:
                print(f"  - Generated {i+1}/{count} images...")

        print(f"[SUCCESS] Generated {len(generated_samples)} synthetic upper-body images in '{target_dir}'!")
        return generated_samples

if __name__ == "__main__":
    generator = SyntheticUpperBodyGenerator(output_dir="dataset/generated")
    generator.generate_batch(count=50)
