#!/usr/bin/env python3
"""LCSC Part Importer for Part-DB using browser automation."""

import argparse
import csv
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from tqdm import tqdm

# Constants
SELECTOR_HELP_TEXT = "#part_base_category_help"
SELECTOR_SAVE = "#part_base_save"
SELECTOR_OPTION = '.ts-dropdown .option[data-value]'
SELECTOR_CREATE = '.ts-dropdown .create'
SELECTOR_CATEGORY_INPUT = '#part_base_category'
# TomSelect control specifically for category (next sibling of the select element)
SELECTOR_CATEGORY_CONTROL = '#part_base_category + .ts-wrapper .ts-control'

# Stock management selectors
SELECTOR_STOCKS_TAB = 'a.nav-link[href="#part_lots"]'
SELECTOR_COMMON_TAB = 'a.nav-link[href="#common"]'
SELECTOR_ADD_STOCK = 'button[data-action="elements--collection-type#createElement"]'

TIMEOUT_MS = 30000


class LCSCImporter:
    """Main importer class for LCSC parts."""

    def __init__(self, base_url: str, csv_path: str):
        self.base_url = base_url
        self.csv_path = Path(csv_path)
        self.browser = None
        self.page = None
        self.playwright = None

        # Setup logging
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        (self.log_dir / "error_screenshots").mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"import_{timestamp}.log"

        logging.basicConfig(
            level=logging.DEBUG,
            format='[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Log file: {log_file}")

        self.success_count = 0
        self.fail_count = 0
        self.skipped_count = 0
        self.failed_parts = []  # Track which parts failed

    def authenticate(self):
        """Interactive login to Part-DB via browser."""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False)
        self.page = self.browser.new_page()

        # Open login page
        login_url = f"{self.base_url}/en/login?_target_path=%2F"
        self.logger.info("Opening login page in browser...")
        self.page.goto(login_url, wait_until="networkidle", timeout=TIMEOUT_MS)

        # Prompt user to login manually in the browser
        self.logger.info("=" * 60)
        self.logger.info("Please login in the browser window that just opened.")
        self.logger.info("=" * 60)
        input("Press Enter after you have successfully logged in...")

        # Verify authentication by checking account info page
        account_url = f"{self.base_url}/en/user/info"
        self.logger.info("Verifying authentication...")

        try:
            self.page.goto(account_url, wait_until="networkidle", timeout=TIMEOUT_MS)

            # Check if we're still on account info page (not redirected to login)
            if "/login" in self.page.url:
                self.logger.error("Authentication failed - still at login page")
                sys.exit(1)

            # Check for user info elements to confirm we're logged in
            # Look for common elements on account page
            self.page.wait_for_selector('main, .content, body', timeout=5000)

            self.logger.info("Authentication successful!")

        except PlaywrightTimeout:
            self.logger.error("Failed to verify authentication")
            sys.exit(1)

    def load_parts_csv(self) -> list:
        """Load and validate CSV file."""
        self.logger.info(f"Loading parts from {self.csv_path}")

        if not self.csv_path.exists():
            self.logger.error(f"CSV file not found: {self.csv_path}")
            sys.exit(1)

        parts = []
        with open(self.csv_path, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) != 2:
                    self.logger.warning(f"Skipping invalid row: {row}")
                    continue

                lcsc_id, amount = row[0].strip(), row[1].strip()

                # Validate LCSC ID format
                if not re.match(r'^C\d+$', lcsc_id):
                    self.logger.warning(f"Invalid LCSC ID format: {lcsc_id}")
                    continue

                try:
                    amount = int(amount)
                    parts.append((lcsc_id, amount))
                except ValueError:
                    self.logger.warning(f"Invalid amount for {lcsc_id}: {amount}")
                    continue

        self.logger.info(f"Found {len(parts)} parts to import")
        return parts

    def check_part_exists(self, lcsc_id: str) -> bool:
        """Check if part already exists in database with exact LCSC ID match."""
        self.logger.debug(f"Checking if {lcsc_id} already exists")

        # Search for the part
        search_url = (
            f"{self.base_url}/en/parts/search?"
            f"name=1&category=1&description=1&mpn=1&tags=1&"
            f"storelocation=1&comment=1&ipn=1&ordernr=1&keyword={lcsc_id}"
        )

        try:
            self.page.goto(search_url, wait_until="networkidle", timeout=TIMEOUT_MS)

            # Check if any results found - look for part links
            part_links = self.page.locator('a[href*="/en/part/"][href*="/info"]').all()

            if not part_links:
                self.logger.debug(f"No search results found for {lcsc_id}")
                return False

            # Check each result to verify exact LCSC ID match
            for link in part_links:
                href = link.get_attribute('href')
                # Extract part ID from URL like /en/part/8/info
                match = re.search(r'/en/part/(\d+)/', href)
                if not match:
                    continue

                part_id = match.group(1)
                self.logger.debug(f"Checking part ID {part_id} for exact LCSC match")

                # Navigate to suppliers page
                suppliers_url = f"{self.base_url}/en/part/{part_id}/info#suppliers"
                self.page.goto(suppliers_url, wait_until="networkidle", timeout=TIMEOUT_MS)

                # Look for exact LCSC ID in suppliers table
                # The td contains a link like: <a href="https://www.lcsc.com/product-detail/C2962094.html">C2962094</a>
                lcsc_links = self.page.locator(f'a[href*="lcsc.com"][href*="{lcsc_id}"]').all()

                for lcsc_link in lcsc_links:
                    link_text = lcsc_link.inner_text().strip()
                    # Exact match check (handles prefix issue: C1991 vs C19915)
                    if link_text == lcsc_id:
                        self.logger.info(f"Part {lcsc_id} already exists (Part ID: {part_id})")
                        return True

            self.logger.debug(f"No exact match found for {lcsc_id} (only prefix matches)")
            return False

        except Exception as e:
            self.logger.warning(f"Error checking if part exists: {e}")
            # If we can't verify, assume it doesn't exist to allow import
            return False

    def parse_lcsc_category(self, help_text: str) -> tuple:
        """Extract LCSC category from help text."""
        # Format: "Provider: Circuit Protection -> Varistors, MOVs"
        # (inner_text strips HTML tags, so no <b> tags present)
        match = re.search(r'Provider:\s*(.+)', help_text)
        if not match:
            self.logger.debug(f"Could not parse category from help text: {help_text}")
            return ("", "")

        category_text = match.group(1).strip()
        self.logger.debug(f"Parsed category text: {category_text}")
        parts = [p.strip() for p in category_text.split('->')]

        if len(parts) == 1:
            return ("", parts[0])
        else:
            return (parts[0], parts[-1])

    def process_single_part(self, lcsc_id: str, amount: int) -> str:
        """Process a single part import. Returns 'success', 'skipped', or 'failed'."""
        self.logger.debug(f"Processing {lcsc_id} with amount {amount}")

        try:
            # Check if part already exists
            if self.check_part_exists(lcsc_id):
                self.logger.info(f"Skipping {lcsc_id} - already exists in database")
                return "skipped"

            # Navigate to create page
            url = f"{self.base_url}/en/part/from_info_provider/lcsc/{lcsc_id}/create"
            self.logger.debug(f"Navigating to: {url}")
            self.page.goto(url, wait_until="networkidle", timeout=TIMEOUT_MS)

            # Check if we got redirected to login (session expired)
            if "/login" in self.page.url:
                self.logger.error(f"Session expired - redirected to login page")
                return "failed"

            # Wait for the form to be ready (wait for tabs to load)
            try:
                self.page.wait_for_selector(SELECTOR_STOCKS_TAB, timeout=10000)
            except PlaywrightTimeout:
                self.logger.error(f"Create form not found - page may not have loaded correctly")
                self.logger.debug(f"Current URL: {self.page.url}")
                return "failed"

            # Step 1: Click on Stocks tab
            self.logger.debug("Clicking on Stocks tab")
            stocks_tab = self.page.locator(SELECTOR_STOCKS_TAB)
            stocks_tab.click()
            self.page.wait_for_timeout(1000)

            # Step 2: Click Add Stock button (within the stocks section only)
            self.logger.debug("Clicking Add Stock button")
            add_stock_button = self.page.locator('#part_lots').locator(SELECTOR_ADD_STOCK).filter(has_text="Add stock")
            add_stock_button.click()
            self.page.wait_for_timeout(1000)  # Wait for stock form to appear

            # Step 3: Select "Unspecified" from storage location dropdown
            self.logger.debug("Selecting storage location")
            try:
                # Find the storage location select element (matches pattern: part_base[partLots][*][storage_location])
                storage_select = self.page.locator('select[name*="[partLots]"][name*="[storage_location]"]').last
                storage_id = storage_select.get_attribute('id')

                # Click on the TomSelect control for storage location
                storage_control = self.page.locator(f'#{storage_id} + .ts-wrapper .ts-control')
                storage_control.click()
                self.page.wait_for_timeout(2000)

                # Select "Unspecified" option
                unspecified_option = self.page.locator('.ts-dropdown .option').filter(has_text="Unspecified").first
                unspecified_option.click()
                self.page.wait_for_timeout(1000)
            except Exception as e:
                self.logger.warning(f"Could not select storage location: {e}")
                # Continue anyway - it might already be selected

            # Step 4: Enter amount into stock amount field
            self.logger.debug(f"Entering amount: {amount}")
            try:
                # Find the amount input field (matches pattern: part_base[partLots][*][amount][value])
                amount_input = self.page.locator('input[name*="[partLots]"][name*="[amount][value]"]').last
                amount_input.fill(str(amount))
            except Exception as e:
                self.logger.error(f"Failed to enter amount: {e}")
                return "failed"

            # Step 5: Click on Common tab to return to category selection
            self.logger.debug("Clicking on Common tab")
            common_tab = self.page.locator(SELECTOR_COMMON_TAB)
            common_tab.click()
            self.page.wait_for_timeout(1000)

            # Step 6: Extract LCSC category from help text
            try:
                help_text = self.page.locator(SELECTOR_HELP_TEXT).inner_text(timeout=5000)
                parent, leaf = self.parse_lcsc_category(help_text)
                lcsc_category = f"{parent} -> {leaf}" if parent else leaf
                self.logger.debug(f"Extracted category: {lcsc_category}")
            except PlaywrightTimeout:
                self.logger.warning(f"No category help text found for {lcsc_id}")
                parent, leaf, lcsc_category = "", "", ""

            # Step 7: Clear any existing category selection first
            try:
                clear_button = self.page.locator('#part_base_category + .ts-wrapper .clear-button')
                if clear_button.is_visible():
                    self.logger.debug("Clearing existing category selection")
                    clear_button.click()
                    self.page.wait_for_timeout(1000)
            except Exception:
                pass  # No clear button or already empty

            # Step 8: Click on TomSelect control to open dropdown and type category text
            if lcsc_category:
                category_control = self.page.locator(SELECTOR_CATEGORY_CONTROL)
                category_control.click()
                self.page.wait_for_timeout(500)  # Wait for dropdown to open

                # Step 9: Type the category path first (this filters the dropdown)
                self.logger.debug(f"Typing category: {lcsc_category}")
                ts_input = self.page.locator('#part_base_category + .ts-wrapper .ts-control input')
                ts_input.fill(lcsc_category)
                self.page.wait_for_timeout(1500)  # Wait for dropdown to filter/update

                # Step 10: Look for matches in the filtered results
                try:
                    # Check if there's an exact match in the filtered options
                    self.page.wait_for_selector(SELECTOR_OPTION, timeout=2000)
                    options = self.page.locator(SELECTOR_OPTION).all()

                    exact_match = None
                    for option in options:
                        text = option.inner_text().strip()
                        # Check for exact match (case-insensitive)
                        if text.lower() == lcsc_category.lower():
                            exact_match = option
                            break

                    if exact_match:
                        self.logger.info(f"Found exact match for category: {lcsc_category}")
                        exact_match.click()
                    else:
                        # No exact match, look for create option
                        try:
                            create_option = self.page.locator(SELECTOR_CREATE).first
                            self.logger.info(f"Creating new category: {lcsc_category}")
                            create_option.click()
                        except Exception as e:
                            self.logger.warning(f"Could not find create option: {e}")
                            # Press Enter as fallback
                            ts_input.press("Enter")

                except PlaywrightTimeout:
                    self.logger.warning("No dropdown options found after typing, pressing Enter")
                    ts_input.press("Enter")

            # Click save
            save_button = self.page.locator(SELECTOR_SAVE)
            save_button.click()

            # Wait for success (redirect or flash message)
            self.page.wait_for_load_state("networkidle", timeout=10000)

            self.logger.info(f"Successfully imported {lcsc_id}")
            return "success"

        except Exception as e:
            self.logger.error(f"Error processing {lcsc_id}: {e}")
            self.take_error_screenshot(lcsc_id)
            return "failed"

    def take_error_screenshot(self, lcsc_id: str):
        """Save error screenshot."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = self.log_dir / "error_screenshots" / f"error_{lcsc_id}_{timestamp}.png"
        try:
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            self.logger.info(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            self.logger.error(f"Failed to save screenshot: {e}")

    def import_parts(self, parts: list):
        """Main import loop with progress bar."""
        tqdm.write("[INFO] Starting import...")

        with tqdm(total=len(parts), desc="Importing parts", leave=True) as pbar:
            for lcsc_id, amount in parts:
                status = self.process_single_part(lcsc_id, amount)
                if status == "success":
                    self.success_count += 1
                elif status == "skipped":
                    self.skipped_count += 1
                else:
                    self.fail_count += 1
                    self.failed_parts.append(lcsc_id)
                pbar.update(1)
                pbar.set_postfix({
                    "imported": self.success_count,
                    "skipped": self.skipped_count,
                    "failed": self.fail_count
                })

    def cleanup(self):
        """Close browser and print summary."""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

        total = self.success_count + self.skipped_count + self.fail_count

        # Print completion status
        if self.fail_count > 0:
            self.logger.warning("=" * 60)
            self.logger.warning(f"Import finished with {self.fail_count} error(s)!")
            self.logger.warning("=" * 60)
        else:
            self.logger.info("=" * 60)
            self.logger.info("Import completed successfully!")
            self.logger.info("=" * 60)

        # Print summary
        self.logger.info(f"Imported: {self.success_count}/{total} parts")
        self.logger.info(f"Skipped: {self.skipped_count}/{total} parts (already exist)")
        self.logger.info(f"Failed: {self.fail_count}/{total} parts")

        # List failed parts if any
        if self.failed_parts:
            self.logger.warning("\nFailed parts:")
            for part_id in self.failed_parts:
                self.logger.warning(f"  - {part_id}")
            self.logger.warning("\nCheck error screenshots in logs/error_screenshots/ for details.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Import LCSC parts into Part-DB using browser automation"
    )
    parser.add_argument(
        "csv_path",
        help="Path to CSV file with format: lcsc_id,amount"
    )
    parser.add_argument(
        "--base-url",
        help=f"Part-DB base URL"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Update logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    try:
        importer = LCSCImporter(args.base_url, args.csv_path)
        importer.authenticate()
        parts = importer.load_parts_csv()

        if not parts:
            logging.error("No valid parts found in CSV")
            sys.exit(1)

        importer.import_parts(parts)
        importer.cleanup()

    except KeyboardInterrupt:
        logging.info("\nImport interrupted by user")
        if 'importer' in locals():
            importer.cleanup()
        sys.exit(1)
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        if 'importer' in locals():
            importer.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()
