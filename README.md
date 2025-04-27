# Job Scraper

## Description

This Python script automatically scrapes job postings from a list of company career pages specified in an Excel file. It is designed to handle dynamic, JavaScript-heavy websites (like Workday and Taleo) by using the Playwright library to control a headless browser.

The script extracts individual job posting links, attempts to filter out jobs located outside the US and Hong Kong, identifies unique jobs even if their URLs have dynamic elements, and saves the unique links along with the date they were first identified to an output Excel file.

## Features

* Scrapes job postings from a list of URLs provided in an Excel file.
* Handles JavaScript-rendered content using Playwright (headless Chromium browser).
* Extracts individual job posting links (`<a>` tags).
* Filters jobs based on location keywords found in the URL or link text (attempts to keep only US/HK).
* Detects duplicate job postings across runs using a generated "Descriptive Key" (Domain + stable URL path suffix) to handle dynamic URL segments.
* Reads target URLs from a specified sheet and column in an input Excel file.
* Writes unique job links and the date first discovered to a specified sheet in an output Excel file.
* Appends new findings to the output file on subsequent runs without adding duplicates (based on the Descriptive Key).

## Prerequisites

* **Python 3.x:** Ensure you have a compatible version of Python installed ([python.org](https://www.python.org/)).
* **pip:** Python's package installer, usually included with Python.

## Setup

1.  Get the `job_scraper.py` script file.
2.  Open your terminal or command prompt and navigate to the script's directory. Run the following command to install the required Python packages:
    ```
    pip install pandas openpyxl playwright beautifulsoup4 lxml
    ```
3.  Playwright needs browser binaries to function. Run this command in your terminal:
    ```
    playwright install
    ```

## Configuration

Before running the script, you need to configure the variables at the top of `job_scraper.py`:

* **Input File:**
    * `INPUT_EXCEL_FILE`: Set to the name of your Excel file containing the list of career page URLs (e.g., `'job_sites.xlsx'`).
    * `TARGET_URL_SHEET`: The name of the sheet within the input file that contains the URLs (e.g., `'Sheet1'`).
    * `TARGET_URL_COLUMN`: The column containing the URLs. Use the column letter (e.g., `'A'`) if there's no header row, or the exact header name (e.g., `'Career Pages'`) if there is a header.
* **Output File:**
    * `OUTPUT_EXCEL_FILE`: The name of the Excel file where results will be saved (e.g., `'found_jobs.xlsx'`). The script will create this file if it doesn't exist or append to it if it does.
    * `OUTPUT_SHEET`: The name of the sheet within the output file to save results (e.g., `'Sheet1'`).
    * `JOB_LINK_COLUMN`: The desired header name for the column containing the found job URLs (e.g., `'JobLink'`).
    * `DATE_COLUMN`: The desired header name for the column containing the date the link was first found (e.g., `'DateFound'`).
    * `JOB_KEY_COLUMN`: The header name for the internal key used for deduplication (you likely don't need to change this unless it conflicts, e.g., `'DescriptiveKey'`). This column is used during processing but removed from the final output file.
* **Scraping Behavior:**
    * `SLEEP_DURATION_SEC`: Time in seconds to pause between processing each target URL. Helps avoid overwhelming servers (e.g., `1`).
    * `BROWSER_TIMEOUT`: Maximum time in milliseconds Playwright will wait for page navigation or certain actions before timing out (e.g., `3000` for 60 seconds).
    * `FALLBACK_JS_RENDER_WAIT_SEC`: **Crucial:** The fixed time in seconds the script waits *after* the initial page load (`domcontentloaded`) before grabbing the page content. This allows time for JavaScript to execute and render dynamic content. **This is the primary wait mechanism.** If jobs are missed, you may need to *increase* this value (e.g., to `10`, `15` or more), but this will slow down the script.
* **Location Filtering:**
    * `ALLOWED_LOCATION_KEYWORDS`: A Python `set` of lowercase keywords. If any of these are found in a job's URL or link text, the job is **kept** (it passes the filter). Prioritize adding specific US/HK cities and common abbreviations here.
    * `DISALLOWED_LOCATION_KEYWORDS`: A Python `set` of lowercase keywords. If *no allowed keywords* were found, the script checks this list. If any of these disallowed keywords are found, the job is **filtered out**. Populate this with cities, countries, regions, or URL path segments (like `/fr-fr`) you want to explicitly exclude.

## Usage

1.  Create the Excel file specified by `INPUT_EXCEL_FILE` (e.g., `job_sites.xlsx`). In the sheet specified by `TARGET_URL_SHEET` (e.g., `Sheet1`), list the full URLs of the career pages you want to scrape in the column specified by `TARGET_URL_COLUMN` (e.g., Column A).
2.  Open your terminal or command prompt, navigate (`cd`) to the directory where you saved `job_scraper.py`, and run the script using:
    ```
    python job_scraper.py
    ```
3.  The script will print progress messages to the console, including which URL it's processing, how many links were found/added, and any errors encountered.
4.  After the script finishes, check the Excel file specified by `OUTPUT_EXCEL_FILE` (e.g., `found_jobs.xlsx`). The sheet specified by `OUTPUT_SHEET` should contain the unique job links found in allowed locations, along with the date they were first added.

## How it Works

1.  Reads target URLs from the input Excel and loads previously found job *keys* from the output Excel (if it exists) into a Python set for duplicate checking.
2.  Initializes Playwright, launching a headless Chromium browser instance in the background.
3.  Loops through each target URL from the input list.
4.  Uses Playwright to navigate to the target URL. It waits for the initial HTML document to load (`domcontentloaded`) and then waits for a **fixed duration** (`FALLBACK_JS_RENDER_WAIT_SEC`) to allow JavaScript to execute and render dynamic content.
5.  Retrieves the final HTML content of the page after the wait.
6.  Uses BeautifulSoup to parse the HTML and find all anchor tags (`<a>`) with `href` attributes.
7.  For each link found:
    * Resolves relative URLs to absolute URLs.
    * Cleans the URL (removes query strings `?` and fragments `#`).
    * Performs an initial check (`is_likely_job_posting`) to see if the URL structure resembles a job link.
    * Performs location filtering (`should_filter_by_location`) based on keywords in the URL and link text, prioritizing allowed locations.
    * If likely a job and location is allowed, generates a "Descriptive Key" (`get_descriptive_job_key`) based on the domain and the trailing part of the URL path (e.g., from `/opp/` or `/job/` onwards).
    * Checks if this `Descriptive Key` has already been seen in previous runs (loaded from the output file) or earlier in the current run.
    * If the key is new, the *original cleaned URL* and the current date/time are stored. The new key is added to the set of seen keys.
8.  After processing all target URLs, the script reads the full existing output file (if any), combines it with the newly found links, **removes duplicates based on the `Descriptive Key` column**, selects only the `JobLink` and `DateFound` columns, and saves the final unique list back to the output Excel file, overwriting the previous version.

## Important Nuances & Limitations

* **Duplicate Detection (Descriptive Key):** The method of using the domain + descriptive path suffix (e.g., `/opp/...`, `/job/...`) as a key is designed to handle dynamic URL segments like session IDs (`xf-...`). However, it relies on:
    * The descriptive part starting consistently (e.g., always after `/opp/` or `/job/`).
    * The descriptive part itself being stable and unique for each job.
    * It might fail if the starting markers (`/opp/`, `/job/`) are not present or if dynamic elements appear *within* the descriptive suffix.
* **Location Filtering:** Filtering is based on keywords found in the link's URL or its associated text *on the listing page*.
    * It will likely **miss** the correct location if it's not mentioned in either of those places (even if the job page itself specifies it).
    * It can be inaccurate if keywords are ambiguous (e.g., city names that are also common words).
    * **You MUST review and customize** the `ALLOWED_LOCATION_KEYWORDS` and `DISALLOWED_LOCATION_KEYWORDS` sets for accuracy based on your target sites and desired locations. The current logic prioritizes keeping links if allowed keywords are found.
* **Website Changes:** Web scrapers are inherently fragile. If a website changes its HTML structure, URL patterns, or introduces new anti-scraping measures, this script **will likely break** and require updates. Regular monitoring and maintenance are necessary.
* **Error Handling:** Basic error handling is included for file operations, network requests, and parsing. However, complex errors on specific websites might not be caught gracefully. Always check the console output for error messages.
* **No Pagination:** The script only scrapes the first page of results loaded by each target URL. It does not currently handle clicking "Next" or loading subsequent pages.
* **Resource Usage:** Playwright launches a full browser process, consuming more CPU and RAM than simple HTTP requests.
* **Rate Limiting/Blocking:** Scraping too frequently or aggressively can lead to your IP address being blocked by the target websites. The `SLEEP_DURATION_SEC` helps mitigate this but is not a guarantee.

## Troubleshooting

* **Jobs Missed:** Increase `FALLBACK_JS_RENDER_WAIT_SEC`. Check if the job requires clicking pagination (not supported). Verify the job link structure matches patterns in `is_likely_job_posting`.
* **Incorrect Location Filtering:** Add/remove keywords in `ALLOWED_LOCATION_KEYWORDS` and `DISALLOWED_LOCATION_KEYWORDS`. Check debug prints inside `should_filter_by_location` if needed.
* **Duplicate Links Still Appearing:** Verify the `get_descriptive_job_key` function is correctly identifying the stable part of the URL for the affected site. Check debug prints. Ensure the `JobKey` column is being used correctly in the final `drop_duplicates`. Check for subtle differences in URLs that might affect key generation. Ensure the output file is being read correctly at the start.
* **Errors During Run:** Check the console output for specific error messages (e.g., `FileNotFoundError`, Playwright errors, parsing errors). Ensure all prerequisites (Python libraries, Playwright browsers) are installed correctly. Check network connectivity.
* **Script Stops Responding:** Potentially a Playwright issue or a page that hangs indefinitely. Try running with `headless=False` in `browser = p.chromium.launch(headless=False)` to see the browser window for clues. Increase `BROWSER_TIMEOUT`.
