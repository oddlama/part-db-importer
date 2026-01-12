# part-db-importer

Batch import LCSC parts into Part-DB using browser automation. Part-DB already
has LCSC integration, but no API for bulk imports - this script automates the
web UI to import parts from a CSV file.

## Features

- Category matching with automatic category creation
- Browser-based authentication (you might not be redirected after logging in, just continue normally then)
- Continues on errors (and saves screenshots)
- Note: Existence check currently disabled - will attempt to import all parts in CSV

## Quick Start

Create a CSV file with LCSC part numbers and quantities:

```csv
C2962094,5
C567600,1
C2987730,20
```

Run the importer:

```bash
nix run github:oddlama/part-db-importer -- --base-url "https://part-db.example.com" example.csv
```

A browser window opens to the Part-DB login page. Login with admin credentials,
press Enter in the terminal, and the script starts importing.

CSV format: `lcsc_id,amount` (no headers):

```csv
C2962094,5
C567600,1
C2987730,20
```

## Output

Logs are saved to `logs/import_YYYYMMDD_HHMMSS.log`. Error screenshots are saved to `logs/error_screenshots/`.

Example:

```
[2026-01-12 15:30:45] Opening login page in browser...
============================================================
Please login in the browser window that just opened.
============================================================
Press Enter after you have successfully logged in...
[2026-01-12 15:31:11] Authentication successful!
[2026-01-12 15:31:11] Found 3 parts to import
Importing parts: 100%|████████| 3/3 [00:45<00:00] imported: 2 skipped: 1 failed: 0
============================================================
Import completed successfully!
============================================================
Imported: 2/3 parts
Skipped: 1/3 parts (already exist)
Failed: 0/3 parts
```

## Development

A nix devshell is available with all necessary dependencies:

```bash
nix develop
python importer.py example.csv --log-level DEBUG
```
## Contributing

Contributions are welcome! If you have suggestions or want to improve the script, feel free to open an issue or submit a pull request.

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE) or <https://www.apache.org/licenses/LICENSE-2.0>)
- MIT license ([LICENSE-MIT](LICENSE-MIT) or <https://opensource.org/licenses/MIT>)

at your option.

Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in this project by you, as defined in the Apache-2.0 license,
shall be dual licensed as above, without any additional terms or conditions.
