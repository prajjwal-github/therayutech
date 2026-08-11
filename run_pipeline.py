import os
import sys
import subprocess
import yaml

def run_step(command_str, step_name):
    print("\n" + "="*70)
    print(f"🚀 EXECUTING PIPELINE STEP: {step_name}")
    print(f"   Command: {command_str}")
    print("="*70)
    result = subprocess.run(command_str, shell=True)
    if result.returncode != 0:
        print(f"❌ Step '{step_name}' failed with exit code {result.returncode}")
        sys.exit(result.returncode)

def main():
    print("🌟 STARTING COMPLETE IMAGE-ONLY UPPER-BODY AI PIPELINE...")

    # Step 1: Generate Dataset
    run_step("python generate_dataset.py --count 1000", "STEP 1 - Synthetic Image Generation")

    # Step 2: Quality Filter, Split & Augment Dataset
    run_step("python prepare_dataset.py", "STEP 2 - Quality Control, Pseudo-labeling, Splitting & Augmentation")

    # Step 3: Train Multi-Candidate Models
    run_step("python train.py", "STEP 3 - Multi-Candidate Model Training & Export")

    # Step 4: Evaluate Model & Optimization Loop
    run_step("python evaluate.py", "STEP 4 - Unseen Test Evaluation & Optimization Loop")

    # Step 5: Test Single Image Inference
    # Find first test image to demo inference
    test_dir = "dataset/test"
    test_imgs = [f for f in os.listdir(test_dir) if f.endswith(".jpg") or f.endswith(".png")]
    if test_imgs:
        sample_img = os.path.join(test_dir, test_imgs[0])
        run_step(f"python test_image.py --image {sample_img}", "STEP 5 - Single-Image Inference Test")

    print("\n" + "🎉"*35)
    print("  COMPLETE IMAGE-ONLY UPPER-BODY AI PIPELINE EXECUTED SUCCESSFULLY!")
    print("🎉"*35 + "\n")

if __name__ == "__main__":
    main()
