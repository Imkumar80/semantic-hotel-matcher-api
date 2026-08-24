import argparse
import sys
import os
from .core.matcher import EntityMatcher
from .core.config import MatcherConfig

def parse_args():
    parser = argparse.ArgumentParser(description="Semantic Entity Matcher CLI")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # "match" command
    match_parser = subparsers.add_parser("match", help="Match two datasets and create a canonical database")
    match_parser.add_argument("--left", required=True, help="Path to the left CSV dataset (e.g., supplier_a.csv)")
    match_parser.add_argument("--right", required=True, help="Path to the right CSV dataset (e.g., supplier_b.csv)")
    match_parser.add_argument("--config", required=True, help="Path to the YAML configuration file")
    match_parser.add_argument("--outdir", default=".", help="Directory to save the results (default: current directory)")
    
    return parser.parse_args()

def main():
    args = parse_args()
    
    if args.command == "match":
        if not os.path.exists(args.config):
            print(f"Error: Configuration file '{args.config}' not found.")
            sys.exit(1)
            
        print(f"Loading configuration from {args.config}...")
        try:
            config = MatcherConfig.from_yaml(args.config)
        except Exception as e:
            print(f"Error parsing configuration: {e}")
            sys.exit(1)
            
        print("Initializing EntityMatcher...")
        matcher = EntityMatcher(verbose=True)
        
        print(f"Starting match process...")
        print(f"Left dataset:  {args.left}")
        print(f"Right dataset: {args.right}")
        print(f"Output directory: {args.outdir}")
        
        try:
            results = matcher.match(
                left=args.left,
                right=args.right,
                config=config,
                output_dir=args.outdir
            )
            
            print("\nMatch Process Complete!")
            print(f"Canonical entities created: {results['metrics']['total_canonical']}")
            print(f"Total matches found: {results['metrics']['total_matches']}")
            print(f"Near-misses detected: {results['metrics']['total_near_misses']}")
            
        except Exception as e:
            print(f"Error during matching: {e}")
            sys.exit(1)
    else:
        # If no command is provided, print help
        parse_args(["--help"])

if __name__ == "__main__":
    main()
