#!/usr/bin/env python3
"""Calculate the average of values in a data file.

Expected file format:
    value
    12.3
    45.6
    78.9
    ...
"""

import sys


def calculate_average(filepath: str) -> float:
    with open(filepath, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        raise ValueError("File is empty")

    # Skip the header line ("value")
    values = [float(line) for line in lines[1:]]

    if not values:
        raise ValueError("No numeric values found after header")

    return sum(values) / len(values)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_data_file>")
        sys.exit(1)

    filepath = sys.argv[1]

    try:
        avg = calculate_average(filepath)
    except FileNotFoundError:
        print(f"Error: file not found: {filepath}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Average: {avg}")


if __name__ == "__main__":
    main()