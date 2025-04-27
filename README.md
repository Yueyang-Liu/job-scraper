# job-scraper

**1. Prerequisites**

* Download and install Python and Visual Studio Code.
* Open your terminal or command prompt and run:
    ```
    pip install pandas openpyxl playwright beautifulsoup4 lxml
    ```
* Playwright needs browser binaries. Run this command:
    ```
    playwright install
    ```

**2. Prepare Excel Files**

* Save the sheet the target URLs as an Excel file (e.g., `job_sites.xlsx`).
* Make sure the URLs are in a specific sheet (e.g., `Sheet1`) and column (e.g., `A`). Note the exact sheet name and column letter / header name.
* Create an empty Excel file (or one with previous results) to store the output (e.g., `found_jobs.xlsx`). It should have columns for the job link and the date found (e.g., `JobLink`, `DateFound`).

**3. Run the Code**

1.  Save the code above as a Python file (e.g., `job_scraper.py`).
2.  Place the script in the **same directory** as your input Excel file (`job_sites.xlsx`).
3.  Make sure the output Excel file (`found_jobs.xlsx`) either doesn't exist yet or is in the same directory (the script will create / overwrite it).
4.  Open your terminal or command prompt, navigate (`cd`) to that directory.
5.  Run the script:
    ```
    python job_scraper.py
    ```
6.  The script will print progress messages. It will launch a headless browser (you won't see it), visit each site, wait for content, parse links, filter them, and finally save any new, unique job links found to the output Excel file.
