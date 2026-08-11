import argparse
import yaml
from src.dataset_generator import SyntheticUpperBodyGenerator

def main():
    parser = argparse.ArgumentParser(description="Generate Synthetic Upper-Body Human Image Dataset")
    parser.add_argument("--count", type=int, default=1000, help="Number of synthetic images to generate")
    parser.add_argument("--output_dir", type=str, default="dataset/generated", help="Output directory")
    args = parser.parse_args()

    # Load config if exists
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
            count = config.get("dataset", {}).get("target_images", args.count)
    except Exception:
        count = args.count

    if args.count != 1000:
        count = args.count

    generator = SyntheticUpperBodyGenerator(output_dir=args.output_dir)
    generator.generate_batch(count=count)

if __name__ == "__main__":
    main()
