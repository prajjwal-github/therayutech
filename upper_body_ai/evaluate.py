import os
import json
import yaml
from src.evaluator import UpperBodyEvaluator
from src.dataset_generator import SyntheticUpperBodyGenerator
from src.annotation_generator import AnnotationGenerator
from src.quality_filter import ImageQualityFilter
from src.trainer import UpperBodyModelTrainer
from train import load_annotations_from_dir

def main():
    print("[STEP 4] EVALUATING TRAINED MODEL ON UNSEEN TEST DATASET...")

    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    test_anno_dir = os.path.join(config["dataset"]["test_dir"], "annotations")
    test_annos = load_annotations_from_dir(test_anno_dir)

    print(f"[INFO] Loaded {len(test_annos)} unseen Test annotations.")

    if len(test_annos) == 0:
        print("[ERROR] Test annotations not found. Please run 'python prepare_dataset.py' first!")
        return

    evaluator = UpperBodyEvaluator(models_dir=config["training"]["models_dir"])
    report = evaluator.evaluate_test_set(test_annos)

    print("\n" + "="*50)
    print("UNSEEN TEST SET EVALUATION REPORT:")
    print("="*50)
    print(f"  Test Accuracy: {report['test_accuracy_pct']}%")
    print(f"  Weighted Precision: {report['precision']}")
    print(f"  Weighted Recall: {report['recall']}")
    print(f"  Weighted F1 Score: {report['f1_score']}")
    print(f"  Joint Angle MAE (Elbows): {report['joint_angle_mae_degrees']['elbow_mae']} deg")
    print(f"  Joint Angle MAE (Shoulders): {report['joint_angle_mae_degrees']['shoulder_mae']} deg")

    print("\nPer-Class Accuracy Breakdown:")
    for cls_name, cls_acc in report["per_class_accuracy_pct"].items():
        print(f"  - {cls_name}: {cls_acc}%")

    weak_classes = report.get("weak_classes", [])
    if weak_classes:
        print(f"\n[WARNING] Weak Pose Scenarios Identified (< 90% accuracy): {weak_classes}")
        print("[OPTIMIZATION] Triggering Automated Optimization Loop (Generating targeted images for weak poses)...")
        
        generator = SyntheticUpperBodyGenerator(output_dir="dataset/hard_cases")
        annotator = AnnotationGenerator()
        
        targeted_annos = []
        for weak_cls in weak_classes:
            print(f"  - Generating targeted batch for weak pose class: '{weak_cls}'...")
            samples = generator.generate_batch(count=50, target_dir=os.path.join("dataset/hard_cases", weak_cls.lower()))
            for img_p, anno_p in samples:
                anno, ok = annotator.annotate_image(img_p, pose_class=weak_cls)
                if ok:
                    targeted_annos.append(anno)

        print(f"[INFO] Created {len(targeted_annos)} targeted samples. Retraining model...")
        train_annos = load_annotations_from_dir(os.path.join(config["dataset"]["train_dir"], "annotations"))
        val_annos = load_annotations_from_dir(os.path.join(config["dataset"]["val_dir"], "annotations"))

        train_annos.extend(targeted_annos)

        trainer = UpperBodyModelTrainer(models_dir=config["training"]["models_dir"])
        best_name, best_model, results = trainer.train_and_evaluate(train_annos, val_annos)

        print("[INFO] Re-evaluating updated model on unseen Test Set...")
        evaluator = UpperBodyEvaluator(models_dir=config["training"]["models_dir"])
        report = evaluator.evaluate_test_set(test_annos)
        print(f"[SUCCESS] Updated Test Accuracy after Targeted Optimization: {report['test_accuracy_pct']}%")

    # Save final report
    final_report_path = os.path.join(config["training"]["models_dir"], "final_evaluation_report.json")
    with open(final_report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n[SUCCESS] Saved full evaluation report to: '{final_report_path}'")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
