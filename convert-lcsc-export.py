import csv
import sys

def extract_lcsc_and_quantity(input_file, output_file=None):
    out = sys.stdout if output_file is None else open(output_file, "w", newline="")

    with open(input_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            lcsc = row.get("LCSC Part Number", "").strip()
            qty = row.get("Quantity", "").strip()

            if lcsc and qty:
                out.write(f"{lcsc},{qty}\n")

    if output_file is not None:
        out.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract.py input.csv [output.csv]")
        sys.exit(1)

    input_csv = sys.argv[1]
    output_csv = sys.argv[2] if len(sys.argv) > 2 else None

    extract_lcsc_and_quantity(input_csv, output_csv)

