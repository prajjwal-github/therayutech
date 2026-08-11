import numpy as np

class TrackedPerson:
    """Represents a single tracked individual across consecutive frames."""
    def __init__(self, track_id, landmarks_dict, bbox):
        self.track_id = track_id
        self.landmarks_dict = landmarks_dict
        self.bbox = bbox # [x1, y1, x2, y2]
        self.center = np.array([(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0])
        self.disappeared = 0

    def update(self, landmarks_dict, bbox):
        self.landmarks_dict = landmarks_dict
        self.bbox = bbox
        self.center = np.array([(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0])
        self.disappeared = 0

class MultiPersonTracker:
    """
    Multi-Person Persistent ID Tracker.
    Assigns stable tracking IDs (ID 1, ID 2, ...) using Bounding Box IOU and Joint Center Distance matching.
    Maintains persistent identities across occlusions and frame boundaries.
    """

    def __init__(self, max_disappeared=30, iou_threshold=0.30):
        self.next_id = 1
        self.tracked_persons = {} # track_id -> TrackedPerson
        self.max_disappeared = max_disappeared
        self.iou_threshold = iou_threshold

    @staticmethod
    def compute_bbox_from_landmarks(landmarks_dict):
        """Calculates bounding box [x1, y1, x2, y2] from landmark keypoints."""
        xs = [lm["px_x"] for lm in landmarks_dict.values()]
        ys = [lm["px_y"] for lm in landmarks_dict.values()]
        if not xs or not ys:
            return [0, 0, 100, 100]
        padding = 30
        x1 = max(0, min(xs) - padding)
        y1 = max(0, min(ys) - padding)
        x2 = max(xs) + padding
        y2 = max(ys) + padding
        return [x1, y1, x2, y2]

    @staticmethod
    def compute_iou(boxA, boxB):
        """Computes Intersection over Union (IOU) between two bounding boxes."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

        denominator = float(boxAArea + boxBArea - interArea)
        if denominator <= 0:
            return 0.0
        return interArea / denominator

    def update(self, detected_persons_landmarks):
        """
        Updates tracking IDs for a list of detected landmark dictionaries in current frame.
        Returns list of (track_id, landmarks_dict, bbox).
        """
        if not detected_persons_landmarks:
            # Increment disappearance counter
            for track_id in list(self.tracked_persons.keys()):
                self.tracked_persons[track_id].disappeared += 1
                if self.tracked_persons[track_id].disappeared > self.max_disappeared:
                    del self.tracked_persons[track_id]
            return []

        input_bboxes = [self.compute_bbox_from_landmarks(lm) for lm in detected_persons_landmarks]

        if len(self.tracked_persons) == 0:
            # Register all input detections as new tracks
            for i, lm in enumerate(detected_persons_landmarks):
                self._register(lm, input_bboxes[i])
        else:
            track_ids = list(self.tracked_persons.keys())
            existing_bboxes = [self.tracked_persons[tid].bbox for tid in track_ids]

            # Compute IOU Cost Matrix
            iou_matrix = np.zeros((len(existing_bboxes), len(input_bboxes)), dtype=np.float32)
            for e_idx, e_box in enumerate(existing_bboxes):
                for i_idx, i_box in enumerate(input_bboxes):
                    iou_matrix[e_idx, i_idx] = self.compute_iou(e_box, i_box)

            # Match detections to existing tracks
            matched_existing = set()
            matched_input = set()

            # Greedy matching based on highest IOU
            for _ in range(min(len(existing_bboxes), len(input_bboxes))):
                max_idx = np.unravel_index(np.argmax(iou_matrix), iou_matrix.shape)
                e_idx, i_idx = max_idx
                max_val = iou_matrix[e_idx, i_idx]

                if max_val >= self.iou_threshold:
                    tid = track_ids[e_idx]
                    self.tracked_persons[tid].update(detected_persons_landmarks[i_idx], input_bboxes[i_idx])
                    matched_existing.add(e_idx)
                    matched_input.add(i_idx)
                    iou_matrix[e_idx, :] = -1
                    iou_matrix[:, i_idx] = -1
                else:
                    break

            # Handle unmatched existing tracks
            for e_idx in range(len(existing_bboxes)):
                if e_idx not in matched_existing:
                    tid = track_ids[e_idx]
                    self.tracked_persons[tid].disappeared += 1
                    if self.tracked_persons[tid].disappeared > self.max_disappeared:
                        del self.tracked_persons[tid]

            # Register unmatched new detections
            for i_idx in range(len(input_bboxes)):
                if i_idx not in matched_input:
                    self._register(detected_persons_landmarks[i_idx], input_bboxes[i_idx])

        # Return active tracks
        active_tracks = []
        for tid, person in self.tracked_persons.items():
            if person.disappeared == 0:
                active_tracks.append((tid, person.landmarks_dict, person.bbox))

        return active_tracks

    def _register(self, landmarks_dict, bbox):
        person = TrackedPerson(self.next_id, landmarks_dict, bbox)
        self.tracked_persons[self.next_id] = person
        self.next_id += 1

# Alias for backwards compatibility with live_pose.py
JointTracker = MultiPersonTracker

