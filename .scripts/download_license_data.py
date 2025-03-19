# /// script
# dependencies = [
#     "requests",
# ]
# ///
import time
import json
from pathlib import Path

import requests

URL = "https://raw.githubusercontent.com/spdx/license-list-data/refs/heads/main/json/licenses.json"


def download_file(url: str) -> dict:
    """Download file at url"""
    response = requests.get(url, timeout=10)
    response.raise_for_status()  # Raise an error for HTTP issues
    return response.json()


def fetch_data(url: str, retry: int = 0) -> dict:
    """Fetch the license JSON from the given URL with retries."""
    try:
        return download_file(url)
    except requests.exceptions.RequestException as e:
        if retry > 3:
            exit(1, f"Failed to fetch data from {url}: {e}")
        retry += 1
        backoff = 2**retry
        time.sleep(backoff)
        return fetch_data(url, retry)


def main() -> None:
    file = Path(__file__).parent / "license-data.json"
    data = fetch_data(URL)
    print(f"Downloaded {len(data)} licenses")
    with file.open("w", encoding="utf-8") as f:
        json.dump(data, f)
    if file.exists():
        print(f"License data downloaded to {file.as_posix()}")
    else:
        exit(1, f"Failed to write license data to {file}")


if __name__ == "__main__":
    main()
