import os
import json
import yaml
from src.trainer import UpperBodyModelTrainer

def load_annotations_from_dir(anno_dir):
    """Loads all JSON annotation dicts from a folder."""
    if not os.path.exists(anno_dir):
        return []
    annos = []
    for f in os.listdir(anno_dir):
        if f.endswith(".json"):
            with open(os.path.join(anno_dir, f), "r") as json_file:
                try:
                    annos.append(json.load(json_file))
                except Exception:
                    pass
    return annos

def main():
    print("[STEP 3] TRAINING MULTI-CANDIDATE UPPER-BODY MODELS...")

    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    train_anno_dir = os.path.join(config["dataset"]["train_dir"], "annotations")
    val_anno_dir = os.path.join(config["dataset"]["val_dir"], "annotations")

    train_annos = load_annotations_from_dir(train_anno_dir)
    val_annos = load_annotations_from_dir(val_anno_dir)

    print(f"[INFO] Loaded {len(train_annos)} Training annotations and {len(val_annos)} Validation annotations.")

    if len(train_annos) == 0 or len(val_annos) == 0:
        print("[ERROR] Training or Validation annotations not found. Please run 'python prepare_dataset.py' first!")
        return

    trainer = UpperBodyModelTrainer(
        models_dir=config["training"]["models_dir"],
        checkpoints_dir=config["training"]["checkpoints_dir"]
    )

    best_name, best_model, results = trainer.train_and_evaluate(train_annos, val_annos)

    print("\n" + "="*50)
    print("[SUCCESS] MODEL TRAINING COMPLETE!")
    print(f"Best Architecture: {best_name}")
    print(f"Validation F1 Score: {results[best_name]['validation_f1']:.4f}")
    print(f"Model files saved in: '{config['training']['models_dir']}'")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
