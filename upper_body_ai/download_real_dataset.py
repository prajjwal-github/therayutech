import argparse
from src.real_human_dataset_fetcher import RealHumanDatasetFetcher

def main():
    parser = argparse.ArgumentParser(description="Fetch & Pseudo-Label Real Human Full-Body Photo Dataset")
    parser.add_argument("--count", type=int, default=70, help="Number of real human photos to fetch")
    args = parser.parse_args()

    fetcher = RealHumanDatasetFetcher(raw_output_dir="dataset/raw_real_humans")
    fetcher.fetch_and_annotate(target_count=args.count)
    fetcher.close()

if __name__ == "__main__":
    main()
