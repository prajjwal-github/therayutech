import os
import json
import sqlite3
import yaml

TARGET_DIR = r"C:\Users\Prajjwal\OneDrive\Desktop\YOGA"

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

print(f"[INFO] Populating Standalone AI Yoga Trainer Project in '{TARGET_DIR}'...")

# 1. Directories
for d in ["config", "camera", "inference", "tracking", "utilities", "metrics", "src", "ml", "visualization", "output", "database", "models/final"]:
    ensure_dir(os.path.join(TARGET_DIR, d))

print("[SUCCESS] Created all project directories!")
