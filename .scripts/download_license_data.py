# /// script
# dependencies = [
#     "requests",
# ]
# ///
import time
import json

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
    data = fetch_data(URL)
    with open("licenses.json", "w") as f:
        json.dump(data, f)


if __name__ == "__main__":
    main()
