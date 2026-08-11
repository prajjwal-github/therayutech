import os
import json
import random
import shutil
import cv2
import yaml
from src.annotation_generator import AnnotationGenerator
from src.quality_filter import ImageQualityFilter
from src.augmentation import DatasetAugmenter

def main():
    print("[STEP 2] PREPARING, QUALITY-FILTERING, SPLITTING & AUGMENTING DATASET...")

    # Load Config
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    gen_dir = config["dataset"]["generated_dir"]
    train_dir = config["dataset"]["train_dir"]
    val_dir = config["dataset"]["val_dir"]
    test_dir = config["dataset"]["test_dir"]
    rejected_dir = config["dataset"]["rejected_dir"]

    for d in [train_dir, val_dir, test_dir, rejected_dir]:
        os.makedirs(d, exist_ok=True)
        os.makedirs(os.path.join(d, "annotations"), exist_ok=True)

    annotator = AnnotationGenerator()
    quality_filter = ImageQualityFilter(
        min_confidence=config["quality_control"]["min_pose_confidence"],
        phash_threshold=config["quality_control"]["phash_similarity_threshold"],
        rejected_dir=rejected_dir
    )
    augmenter = DatasetAugmenter(augmentation_factor=config["training"]["augmentation_factor"])

    # 1. Gather generated synthetic and real human image files
    valid_exts = {".jpg", ".jpeg", ".png"}
    image_files = []
    
    # Add generated images
    for f in os.listdir(gen_dir):
        if os.path.splitext(f)[1].lower() in valid_exts:
            image_files.append(os.path.join(gen_dir, f))

    # Add real human photos if present
    real_dir = os.path.join("dataset", "raw_real_humans")
    if os.path.exists(real_dir):
        for f in os.listdir(real_dir):
            if os.path.splitext(f)[1].lower() in valid_exts:
                image_files.append(os.path.join(real_dir, f))

    print(f"[INFO] Inspecting {len(image_files)} total images (Real Humans + Synthetic) for quality & anatomy...")

    clean_samples = []
    rejected_count = 0

    for idx, img_path in enumerate(image_files):
        # Generate annotation
        anno, success = annotator.annotate_image(img_path)
        if not success or not anno:
            quality_filter._reject_image(img_path, cv2.imread(img_path), "FAILED_POSE_DETECTION")
            rejected_count += 1
            continue

        passed, reason = quality_filter.filter_image(img_path, anno["landmarks_raw"])
        if passed:
            clean_samples.append((img_path, anno))
        else:
            rejected_count += 1

        if (idx + 1) % 200 == 0 or (idx + 1) == len(image_files):
            print(f"  - Processed {idx+1}/{len(image_files)} images...")

    print(f"[SUCCESS] Quality Filter Complete: {len(clean_samples)} Clean Passed | {rejected_count} Rejected!")

    # 2. Shuffle & Split Clean Base Dataset (70% Train, 15% Val, 15% Test)
    random.seed(config["training"]["random_seed"])
    random.shuffle(clean_samples)

    total_clean = len(clean_samples)
    n_train = int(total_clean * config["training"]["train_split"])
    n_val = int(total_clean * config["training"]["val_split"])

    train_base = clean_samples[:n_train]
    val_base = clean_samples[n_train:n_train+n_val]
    test_base = clean_samples[n_train+n_val:]

    def save_split_data(split_name, samples, target_dir, is_train=False):
        saved_annos = []
        for img_path, anno in samples:
            filename = os.path.basename(img_path)
            dest_img = os.path.join(target_dir, filename)
            shutil.copy2(img_path, dest_img)

            anno["image_path"] = dest_img
            json_filename = f"{os.path.splitext(filename)[0]}.json"
            dest_anno = os.path.join(target_dir, "annotations", json_filename)
            with open(dest_anno, "w") as f:
                json.dump(anno, f, indent=2)
            saved_annos.append(anno)

            # Augment ONLY Training Set
            if is_train:
                aug_samples = augmenter.augment_train_sample(dest_img, anno)
                for aug_img, aug_anno in aug_samples:
                    aug_filename = aug_anno["filename"]
                    aug_dest_img = os.path.join(target_dir, aug_filename)
                    cv2.imwrite(aug_dest_img, aug_img)

                    aug_anno["image_path"] = aug_dest_img
                    aug_json_filename = f"{os.path.splitext(aug_filename)[0]}.json"
                    aug_dest_anno = os.path.join(target_dir, "annotations", aug_json_filename)
                    with open(aug_dest_anno, "w") as f:
                        json.dump(aug_anno, f, indent=2)
                    saved_annos.append(aug_anno)

        print(f"  - Saved {split_name} split: {len(saved_annos)} total images (Base + Augmentations)")
        return saved_annos

    print("\n[INFO] Saving Train, Validation, and Test Dataset Splits...")
    train_annos = save_split_data("TRAIN", train_base, train_dir, is_train=True)
    val_annos = save_split_data("VALIDATION", val_base, val_dir, is_train=False)
    test_annos = save_split_data("TEST", test_base, test_dir, is_train=False)

    # 3. Create Dataset Report
    report = {
        "total_generated_images": len(image_files),
        "total_rejected_images": rejected_count,
        "total_clean_base_images": total_clean,
        "splits": {
            "train_base": len(train_base),
            "train_total_augmented": len(train_annos),
            "validation_images": len(val_annos),
            "test_images": len(test_annos)
        },
        "rejection_summary": quality_filter.get_summary()
    }

    report_path = os.path.join("dataset", "dataset_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n[SUCCESS] Dataset preparation complete! Summary report saved to '{report_path}'!")

if __name__ == "__main__":
    main()
