import pandas as pd
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from bs4 import BeautifulSoup
import time
from datetime import datetime
import re # For regular expressions
from urllib.parse import urlparse, urljoin # For parsing and joining URLs
import os # To check if output file exists
import sys # To exit gracefully on critical errors

# --- Configuration ---
INPUT_EXCEL_FILE = 'job_sites.xlsx'   # Input Excel file name
TARGET_URL_SHEET = 'Sheet1'           # Sheet name containing target URLs
TARGET_URL_COLUMN = 'A'               # Column letter (or header name) with URLs

OUTPUT_EXCEL_FILE = 'found_jobs.xlsx' # Output file for results
OUTPUT_SHEET = 'Sheet1'               # Sheet name for results
JOB_LINK_COLUMN = 'JobLink'           # Column name for found job links (clickable URL)
DATE_COLUMN = 'DateFound'             # Column name for the date found
JOB_KEY_COLUMN = 'DescriptiveKey'     # Key used for deduplication

SLEEP_DURATION_SEC = 1                # Wait time between requests
BROWSER_TIMEOUT = 3000                # Max time for page load (in milliseconds)
# Fixed time to wait after initial load for JS rendering
FALLBACK_JS_RENDER_WAIT_SEC = 3       # Time in seconds

# --- Location Filtering Setup ---
# Keywords indicating ALLOWED locations (lowercase). Focus on US/HK.
ALLOWED_LOCATION_KEYWORDS = {
    'new york', 'nyc', 'ny', 'los angeles', 'la', 'chicago', 'san francisco', 'sf',
    'boston', 'houston', 'dallas', 'philadelphia', 'atlanta', 'washington dc', 'dc',
    'seattle', 'miami', 'denver', 'austin', 'menlo park', 'palo alto', 'charlotte',
    'greenwich', 'stamford', 'irvine', 'newport beach',
    'usa', 'us', 'united states', 'hong kong', 'hk'
}

# Keywords indicating DISALLOWED locations (lowercase). Focus on non-US/HK.
DISALLOWED_LOCATION_KEYWORDS = {
    # Europe Cities
    'london', 'paris', 'frankfurt', 'milan', 'zurich', 'geneva', 'madrid',
    'amsterdam', 'dublin', 'luxembourg', 'brussels', 'stockholm', 'warsaw', 'birmingham',
    # Europe Countries/Regions
    'uk', 'united kingdom', 'great britain', 'france', 'germany', 'italy',
    'spain', 'switzerland', 'ireland', 'benelux', 'nordics', 'emea',
    # Asia Cities (Excluding HK)
    'singapore', 'tokyo', 'seoul', 'mumbai', 'delhi', 'beijing', 'shanghai',
    'shenzhen', 'dubai', 'riyadh', 'tel aviv',
    # Asia Countries/Regions (Excluding HK)
    'japan', 'korea', 'india', 'china', 'mainland', 'singapore', 'australia', 'asean', 'mea', 'israel',
    # Americas (Excluding US)
    'toronto', 'montreal', 'vancouver', 'canada', 'mexico city', 'sao paulo', 'brazil', 'latam',
    # Disallowed URL path segments (often language/region codes)
    # Check these separately AFTER checking for allowed keywords
    '/fr-fr', '/de-de', '/it-it', '/ja-jp', '/ko-kr', '/es-es',
    # Add any other specific cities/countries/regions to exclude
}

# --- Helper Function for Location Check (Revised Logic) ---
def should_filter_by_location(url, link_text):
    """
    Determines if a job link should be filtered out based on location.
    Priority:
    1. If an ALLOWED location keyword is found -> DON'T filter (return False).
    2. If NO allowed keyword found, check for DISALLOWED keywords -> Filter (return True) if found.
    3. If NEITHER allowed nor disallowed found -> DON'T filter (return False).
    """
    text_to_check = url.lower()
    if link_text:
        # Simple cleaning for link text before checking
        cleaned_link_text = re.sub(r'[,\(\)/]', ' ', link_text.lower())
        text_to_check += " " + cleaned_link_text

    # 1. Check for ALLOWED keywords first using careful matching
    for keyword in ALLOWED_LOCATION_KEYWORDS:
        # Use word boundaries (\b) or check surrounded by non-alphanumeric/start/end
        # This helps prevent matching 'ca' inside 'canada' or 'sf' inside 'staff'
        pattern = r'(?:\W|^)' + re.escape(keyword) + r'(?:\W|$)'
        if re.search(pattern, text_to_check):
            # print(f"DEBUG: Allowed keyword '{keyword}' found. Keeping link.") # Uncomment for debug
            return False # Keep the link (Do not filter)

    # 2. If no allowed keywords found, THEN check for DISALLOWED keywords
    for keyword in DISALLOWED_LOCATION_KEYWORDS:
        # Check for path segments explicitly first
        if keyword.startswith('/') and keyword in url.lower():
             # print(f"DEBUG: Disallowed path segment '{keyword}' found. Filtering link.") # Uncomment for debug
             return True # Filter

        # Check for keywords using word boundaries/context
        pattern = r'(?:\W|^)' + re.escape(keyword) + r'(?:\W|$)'
        if re.search(pattern, text_to_check):
            # print(f"DEBUG: Disallowed keyword '{keyword}' found. Filtering link.") # Uncomment for debug
            return True # Filter

    # 3. If neither allowed nor disallowed keywords were found
    # print(f"DEBUG: No determining location keywords found. Keeping link by default.") # Uncomment for debug
    return False # Keep the link (Do not filter - default allow)


# --- Descriptive Key Extraction Function ---
def get_descriptive_job_key(url):
    """
    Extracts a unique key based on the domain and the descriptive trailing part
    of the URL path (e.g., starting from /opp/ or /job/).
    Returns None if no reliable pattern is found.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Clean trailing slash from path BEFORE splitting/searching
        path = parsed.path.rstrip('/')

        # Define markers that indicate the start of the descriptive part
        start_markers = ['/opp/', '/job/'] # Add others like '/jobs/' if relevant
        found_marker = None
        marker_index = -1

        # Find the last occurrence of any known marker
        for marker in start_markers:
            current_index = path.rfind(marker)
            if current_index > marker_index: # Prioritize later markers if nested (e.g. /job/ within /careers/)
                marker_index = current_index
                found_marker = marker

        if found_marker:
            # Extract the path starting from the found marker
            descriptive_path = path[marker_index:]
            key = f"{domain}::{descriptive_path}" # Combine domain and descriptive path
            # print(f"DEBUG: Descriptive Key: {key} from {url}") # Uncomment for debug
            return key
        else:
            # If no specific marker, maybe the whole path is descriptive? Risky.
            # Consider returning None or domain + full path as fallback key
            # print(f"DEBUG: No descriptive marker found in path for {url}. Using domain + full path.") # Uncomment for debug
            # return f"{domain}::{path}" # Fallback key (less reliable for duplicates)
            return None # Safest fallback if no marker found

    except Exception as e:
        print(f"  Warning: Error extracting descriptive job key from {url}: {e}")
        return None

# --- Filtering Logic (Checks general likelihood) ---
def is_likely_job_posting(url, base_url):
    """Checks if a URL structure resembles a job posting link."""
    lower_url = url.lower()
    lower_base_url = base_url.lower()

    if not url or url.startswith(('#', 'mailto:', 'tel:', 'javascript:')): return False

    is_workday_job_pattern = 'myworkdayjobs.com' in lower_url and '/job/' in lower_url
    is_taleo_opp_pattern = '.tal.net' in lower_url and '/opp/' in lower_url

    negative_keywords = [
        '/careers', '/jobs', '/jobboard', '/search', '/opportunities',
        'candidate/jobboard', 'login', 'signin', 'register', 'event',
        'about', 'contact', 'privacy', 'terms', '.pdf', '.jpg', '.png',
        'facebook.com', 'linkedin.com', 'twitter.com', 'instagram.com',
        'googleusercontent.com'
    ]

    if lower_url == lower_base_url or lower_url == lower_base_url + '/': return False
    if lower_url.endswith('/adv/') and len(url.split('/')) < len(base_url.split('/')) + 3: return False

    for keyword in negative_keywords:
        if keyword in lower_url:
            is_exception = (
                (is_workday_job_pattern and keyword in ['/jobs', '/careers']) or
                (is_taleo_opp_pattern and keyword in ['/jobs', '/careers', '/candidate'])
            )
            if not is_exception: return False

    if is_workday_job_pattern or is_taleo_opp_pattern: return True
    if re.search(r'jobid=|job_id=|requisitionid=|postingid=|\/\d{5,}', lower_url, re.IGNORECASE): return True

    return False


# --- Main Script ---
def scrape_jobs():
    print(f"Starting job scraper at {datetime.now()}...")

    # --- Load Existing Job Keys ---
    existing_job_keys = set()
    df_existing_full = pd.DataFrame(columns=[JOB_LINK_COLUMN, DATE_COLUMN, JOB_KEY_COLUMN])

    try:
        if os.path.exists(OUTPUT_EXCEL_FILE):
            print(f"Reading existing file {OUTPUT_EXCEL_FILE} to extract keys...")
            df_existing_check = pd.read_excel(OUTPUT_EXCEL_FILE, sheet_name=OUTPUT_SHEET)
            if JOB_LINK_COLUMN in df_existing_check.columns:
                print("Generating descriptive keys from existing links...")
                keys_from_file = [get_descriptive_job_key(str(link)) for link in df_existing_check[JOB_LINK_COLUMN].dropna()]
                existing_job_keys = set(key for key in keys_from_file if key is not None)
                print(f"Loaded {len(existing_job_keys)} unique descriptive keys from existing file.")
                df_existing_full = df_existing_check.copy()
            else:
                print(f"Warning: Column '{JOB_LINK_COLUMN}' not found in {OUTPUT_EXCEL_FILE}.")
    except FileNotFoundError: print(f"Output file {OUTPUT_EXCEL_FILE} not found. Starting fresh.")
    except Exception as e:
        print(f"ERROR loading data/keys from {OUTPUT_EXCEL_FILE}: {e}. Proceeding without existing keys.")
        existing_job_keys = set()


    # --- Load Target URLs ---
    try:
        print(f"Loading target URLs from {INPUT_EXCEL_FILE}...")
        header_row = None if len(TARGET_URL_COLUMN)==1 and TARGET_URL_COLUMN.isalpha() else 0
        df_targets = pd.read_excel(INPUT_EXCEL_FILE, sheet_name=TARGET_URL_SHEET, header=header_row)
        if len(TARGET_URL_COLUMN) == 1 and TARGET_URL_COLUMN.isalpha():
             col_index = ord(TARGET_URL_COLUMN.upper()) - ord('A')
             if col_index >= len(df_targets.columns): raise KeyError(f"Column index out of bounds.")
             target_urls = df_targets.iloc[:, col_index].dropna().astype(str).tolist()
        else:
             if TARGET_URL_COLUMN not in df_targets.columns: raise KeyError(f"Header '{TARGET_URL_COLUMN}' not found.")
             target_urls = df_targets[TARGET_URL_COLUMN].dropna().astype(str).tolist()
        print(f"Loaded {len(target_urls)} target URLs.")
    except FileNotFoundError: print(f"CRITICAL ERROR: Input file '{INPUT_EXCEL_FILE}' not found."); sys.exit(1)
    except KeyError as e: print(f"CRITICAL ERROR: Problem finding column '{TARGET_URL_COLUMN}'. Details: {e}"); sys.exit(1)
    except Exception as e: print(f"CRITICAL ERROR: Could not read target URLs: {e}"); sys.exit(1)


    new_links_data = []
    processed_job_keys_this_session = set()


    # --- Initialize Playwright ---
    print("Launching browser via Playwright...")
    with sync_playwright() as p:
        browser = None
        context = None
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                 user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
            )
            print("Browser launched successfully.")
        except PlaywrightError as e: print(f"CRITICAL ERROR: Could not launch browser: {e}. Try `playwright install`"); sys.exit(1)
        except Exception as e: print(f"CRITICAL ERROR: Browser launch failed: {e}"); sys.exit(1)


        # --- Process Each Target URL ---
        for target_url in target_urls:
            if not target_url or not target_url.startswith(('http://', 'https://')):
                print(f"Skipping invalid URL: {target_url}"); continue

            print(f"\nProcessing: {target_url}")
            page = None
            new_links_this_run_details = []

            try:
                page = context.new_page()
                page.set_default_navigation_timeout(BROWSER_TIMEOUT + 10000)
                page.set_default_timeout(BROWSER_TIMEOUT)
                # page.on("pageerror", lambda err: print(f"  Page Console Error: {err}"))

                print("  Navigating to page...")
                page.goto(target_url, wait_until='domcontentloaded')
                print(f"  Initial load complete. Waiting {FALLBACK_JS_RENDER_WAIT_SEC} seconds for dynamic content...")

                # --- Use fixed wait timeout (Selector logic removed as requested) ---
                page.wait_for_timeout(FALLBACK_JS_RENDER_WAIT_SEC * 1000)

                print("  Getting final page content...")
                html_content = page.content()

                # --- Parse and Extract ---
                soup = BeautifulSoup(html_content, 'lxml')
                found_on_page = 0
                processed_on_page = 0

                for link_tag in soup.find_all('a', href=True):
                    processed_on_page += 1
                    href = link_tag.get('href')
                    if not href or href.startswith(('#', 'mailto:', 'tel:', 'javascript:')): continue

                    try:
                        absolute_url = urljoin(target_url, href)
                        original_cleaned_url = absolute_url.split('?', 1)[0].split('#', 1)[0].rstrip('/')

                        # Check if it looks like a job posting
                        if is_likely_job_posting(original_cleaned_url, target_url):
                            link_text = link_tag.get_text(strip=True)

                            # --- Location Filtering (Revised Logic) ---
                            if not should_filter_by_location(original_cleaned_url, link_text):
                                # Location is Allowed (or unknown)
                                job_key = get_descriptive_job_key(original_cleaned_url)

                                if job_key:
                                    if job_key in processed_job_keys_this_session: continue

                                    if job_key not in existing_job_keys:
                                        found_on_page += 1
                                        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                        link_data = {
                                            JOB_LINK_COLUMN: original_cleaned_url,
                                            DATE_COLUMN: current_date,
                                            JOB_KEY_COLUMN: job_key
                                        }
                                        new_links_data.append(link_data)
                                        new_links_this_run_details.append(f"  - {original_cleaned_url} (Key: {job_key})")
                                        processed_job_keys_this_session.add(job_key)
                                        existing_job_keys.add(job_key)
                                # else:
                                    # print(f"  DEBUG: Could not generate key for allowed job: {original_cleaned_url}")
                            # else:
                                # print(f"  DEBUG: Skipping due to disallowed location: {original_cleaned_url} (Text: {link_text})")

                    except Exception as link_e: print(f"  Warning: Error processing link href '{href}': {link_e}")

                print(f"  Processed {processed_on_page} links, identified {found_on_page} potential new jobs in allowed locations.")
                if found_on_page > 0:
                    print(f"  New link details for {target_url}:")
                    for detail in new_links_this_run_details: print(detail)

            except PlaywrightError as pe: print(f"  ERROR processing {target_url} (Playwright Error): {pe}")
            except Exception as e: print(f"  ERROR processing {target_url} (General Error): {e}")
            finally:
                if page:
                    try: page.close()
                    except Exception as page_close_e: print(f"  Warning: Error closing page: {page_close_e}")
                print(f"  Sleeping for {SLEEP_DURATION_SEC} seconds...")
                time.sleep(SLEEP_DURATION_SEC)

        # --- Close Browser ---
        if browser:
            try: browser.close(); print("\nBrowser closed.")
            except Exception as browser_close_e: print(f"Warning: Error closing browser: {browser_close_e}")


    # --- Save Results ---
    if new_links_data:
        print(f"\nFound {len(new_links_data)} total new job links this run. Preparing final DataFrame...")
        df_new = pd.DataFrame(new_links_data)

        # Combine with existing data loaded earlier (df_existing_full)
        try:
            if not df_existing_full.empty:
                 print("Combining new links with existing data...")
                 # Ensure the existing DataFrame has the key column for deduplication merge
                 if JOB_KEY_COLUMN not in df_existing_full.columns:
                     if JOB_LINK_COLUMN in df_existing_full.columns:
                         print(f"Generating '{JOB_KEY_COLUMN}' for existing data...")
                         df_existing_full[JOB_KEY_COLUMN] = df_existing_full[JOB_LINK_COLUMN].apply(lambda x: get_descriptive_job_key(str(x)))
                     else: df_existing_full[JOB_KEY_COLUMN] = None

                 cols_to_combine = [JOB_LINK_COLUMN, DATE_COLUMN, JOB_KEY_COLUMN]
                 for col in cols_to_combine:
                     if col not in df_existing_full.columns: df_existing_full[col] = None
                     if col not in df_new.columns: df_new[col] = None

                 # Combine safely, ensuring columns exist
                 df_combined = pd.concat([
                    df_existing_full.reindex(columns=cols_to_combine),
                    df_new.reindex(columns=cols_to_combine)
                 ], ignore_index=True)
                 print(f"Combined DataFrame rows before deduplication: {len(df_combined)}")

                 # Remove rows where the job key couldn't be extracted
                 df_combined_keyed = df_combined.dropna(subset=[JOB_KEY_COLUMN])
                 print(f"Rows with valid DescriptiveKey: {len(df_combined_keyed)}")

                 # Deduplicate based on the Descriptive Job Key
                 df_final = df_combined_keyed.drop_duplicates(subset=[JOB_KEY_COLUMN], keep='first')
                 print(f"Rows after deduplicating by '{JOB_KEY_COLUMN}': {len(df_final)}")

            else: # No existing data
                 print("No existing data found, processing only new links...")
                 # Deduplicate new links based on key
                 df_final = df_new.dropna(subset=[JOB_KEY_COLUMN]).drop_duplicates(subset=[JOB_KEY_COLUMN], keep='first')


            # Prepare final output (remove the key column)
            df_output = df_final[[JOB_LINK_COLUMN, DATE_COLUMN]].reset_index(drop=True)

            print("\nPreview of final DataFrame to be saved:")
            print(df_output.head())

            # Write to Excel WITHOUT the index column
            print(f"\nSaving {len(df_output)} unique links to {OUTPUT_EXCEL_FILE}...")
            df_output.to_excel(OUTPUT_EXCEL_FILE, sheet_name=OUTPUT_SHEET, index=False)
            print("Save successful.")

        except Exception as e:
            print(f"ERROR: Could not combine data or save results to {OUTPUT_EXCEL_FILE}: {e}")
            print("New links found this run (not saved):")
            for item in new_links_data:
                print(f"- {item.get(JOB_LINK_COLUMN, 'N/A')} (Key: {item.get(JOB_KEY_COLUMN, 'N/A')})")
    else:
        print("\nNo new job postings found in this run (or all were filtered by location/duplicates).")

    print(f"Scraper finished at {datetime.now()}.")

# --- Run the main function ---
if __name__ == "__main__":
    scrape_jobs()