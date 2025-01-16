import re
import sys

import requests
import toml


def create_author_line(sections: dict) -> str:
    name = sections["author"]
    email = sections["email"]

    return "{ " + f"name = {name}, email = {email} " + "}"


def convert_long_description(long_description: str) -> str:
    return long_description.lstrip("read(").rstrip(")").strip("'\"")


def fetch_license_data(url: str) -> dict:
    """Fetch the license JSON from the given URL."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()  # Raise an error for HTTP issues
    return response.json()


def find_license_id(license_name: str, license_data: dict) -> str:
    licenses = license_data.get("licenses", [])
    normalized_name = license_name.lower().strip()

    matches = [
        license["licenseId"]
        for license in licenses
        if normalized_name in license["name"].lower()
    ]
    return matches[0] if matches else ""


def convert_license(license: str) -> str:
    spdx_url = "https://raw.githubusercontent.com/spdx/license-list-data/refs/heads/main/json/licenses.json"
    license_data = fetch_license_data(spdx_url)
    if spdx_id := find_license_id(license, license_data):
        return spdx_id
    else:
        raise ValueError(f"License ID not found for '{license}'")


def parse_setup(setup_file: str) -> dict[str, str | list[str]]:
    setup_sections = {
        "author": str,
        "author_email": str,
        "url": str,
        "license": str,
        "description": str,
        "long_description": str,
        "keywords": list,
        "classifiers": list,
        "install_requires": list,
    }

    sections: dict[str, str | list[str]] = {
        key: [] if isinstance(val, list) else ""
        for key, val in setup_sections.items()
    }

    with open(setup_file, "r") as file:
        lines = iter(line.strip() for line in file)

    key = ""
    for line in lines:
        if "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            if key in setup_sections:
                if value.startswith("["):
                    sections[key] = []
                    value = value.lstrip("[")
                else:
                    sections[key] = value.strip("\"'")

        elif isinstance(sections[key], list):
            if line == "]":
                continue
            sections[key].append(line.strip("\"'"))

    sections["author"] = create_author_line(sections)
    sections.pop("author_email")
    sections["readme"] = convert_long_description(sections["long_description"])
    sections.pop("long_description")
    sections["license"] = convert_license["convert_license"]

    return sections


def update_pyproject(toml_file: str, sections: dict[str, str | list[str]]):
    """Updates pyproject.toml with new values."""
    with open(toml_file, "r") as f:
        data = toml.load(f)

    for key, value in sections.items():
        if key == "url":
            data["project.urls"]["Homepage"] = value
        elif key == "install_requires":
            for dependency in data["project"]["dependencies"]:
                if dependency not in value:
                    data["project"]["dependencies"].remove(dependency)
        else:
            data["project"][key] = value

    with open(toml_file, "w") as f:
        toml.dump(data, f)


def update_setup(setup_file) -> str:
    supported_versions = ["3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "3.12"]

    with open(setup_file, "r") as f:
        text = f.read()

    text = text.replace("and kindle ", "")

    allowed_keywords = r"Keywords = ['ebook', 'epub']"
    keyword_pattern = r"Keywords = [(?:'\w+',\s?)*'\w+']"

    corrected_text = re.sub(keyword_pattern, allowed_keywords, text)

    programming_line_stub = '"Programming Language :: Python :: '
    programming_line = f'{programming_line_stub}[0-9.]+,"'

    old_versions = rf"^\s*{programming_line}*(?:\n\s*{programming_line})*"
    new_versions = "\n".join(
        f'         {programming_line_stub}{version},"'
        for version in supported_versions
    )
    new_version_text = re.sub(
        old_versions, new_versions, corrected_text, flags=re.MULTILINE
    )

    with open(setup_file, "w") as f:
        f.write(new_version_text)


if __name__ == "__main__":
    update_setup(sys.argv[1])
    sections = parse_setup(sys.argv[1])
    update_pyproject(sys.argv[2], sections)
