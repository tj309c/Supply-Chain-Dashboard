"""
Quick benchmark harness for load performance

Usage:
  python tools/benchmark_load_time.py --trials 3

This script measures `load_all_data` runtime with retail_only=True vs False and writes results to tools/benchmark_results.csv
"""
import time
import statistics
import csv
import argparse

# Import the app's load_all_data
from dashboard_simple import load_all_data


def time_trials(trials=3, retail_only=True):
    times = []
    for i in range(trials):
        start = time.perf_counter()
        # Call load_all_data with no UI progress callback (None)
        _ = load_all_data(_progress_callback=None, retail_only=retail_only)
        end = time.perf_counter()
        elapsed = end - start
        print(f"Trial {i+1}/{trials} retail_only={retail_only} -> {elapsed:.2f}s")
        times.append(elapsed)
    return times


def main():
    parser = argparse.ArgumentParser(description='Benchmark load_all_data')
    parser.add_argument('--trials', type=int, default=3, help='Number of trials to run per mode')
    parser.add_argument('--out', type=str, default='tools/benchmark_results.csv', help='Output CSV file')
    args = parser.parse_args()

    rows = []
    print('Running benchmark with trials =', args.trials)

    for retail in (True, False):
        print('\nRunning retail_only=%s' % retail)
        times = time_trials(trials=args.trials, retail_only=retail)
        avg = statistics.mean(times)
        med = statistics.median(times)
        stdev = statistics.pstdev(times) if len(times) > 1 else 0.0
        print(f"Summary retail_only={retail}: avg={avg:.2f}s med={med:.2f}s stdev={stdev:.2f}s")

        rows.append({
            'retail_only': retail,
            'trials': args.trials,
            'avg_seconds': round(avg, 3),
            'median_seconds': round(med, 3),
            'stdev_seconds': round(stdev, 3)
        })

    # write CSV
    with open(args.out, 'w', newline='') as csvfile:
        fieldnames = ['retail_only', 'trials', 'avg_seconds', 'median_seconds', 'stdev_seconds']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Benchmark saved to {args.out}")

if __name__ == '__main__':
    main()
