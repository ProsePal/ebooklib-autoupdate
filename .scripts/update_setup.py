# /// script
# dependencies = [
#     "requests",
#     "tomlkit",
# ]
# ///

import ast
import re
import sys
import textwrap
from collections.abc import Generator

import requests
import tomlkit
from tomlkit.items import Array, Table


def fetch_license_data(url: str) -> dict:
    """Fetch the license JSON from the given URL."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()  # Raise an error for HTTP issues
    return response.json()


def find_license_id(
    license_name: str, license_data: dict
) -> Generator[str, None, None]:
    """Find the license ID for the given license name."""
    licenses = license_data.get("licenses", [])
    normalized_name = license_name.lower().strip()

    yield from (
        license["licenseId"]
        for license in licenses
        if license["name"].lower().startswith(normalized_name)
    )


def convert_license(license: str) -> str:
    spdx_url = "https://raw.githubusercontent.com/spdx/license-list-data/refs/heads/main/json/licenses.json"
    license_data = fetch_license_data(spdx_url)
    if spdx_id := next(find_license_id(license, license_data)):
        return "{text = %s}" % spdx_id
    else:
        raise ValueError(f"License ID not found for '{license}'")


def read_lines(file_path: str) -> Generator[str, None, None]:
    """Returns a list of lines stripped of whitespace"""
    with open(file_path, "r", encoding="utf-8") as file:
        yield from (line for line in map(str.strip, file) if line)


def parse_authors(authors_file: str) -> dict[str, str]:
    """Parse the authors file and return a dictionary of names and emails."""
    authors = {}

    for line in read_lines(authors_file):
        if line.startswith("Listed"):
            continue
        name, email = line.split(" <") if "<" in line else (line, "")
        authors[name] = email.strip(">")

    return authors


def strip_string(string: str, chars: str = "\"',[]") -> str:
    """Strip quotes, brackets, and commas from a string."""
    return string.strip(chars)


def convert_long_description(long_description: str) -> str:
    return long_description.lstrip("read(").rstrip(")").strip("'\"")


def parse_setup(
    setup_keywords: dict[str, str | list[str]],
) -> dict[str, str | list[str]]:
    """Parse the setup.py file and return a dictionary of sections."""
    setup_sections: list[str] = [
        "version",
        "author",
        "author_email",
        "url",
        "license",
        "description",
        "long_description",
        "keywords",
        "classifiers",
        "install_requires",
    ]

    sections = {keyword: setup_keywords[keyword] for keyword in setup_sections}

    sections |= {
        "readme": sections.pop("long_description"),
        "license": convert_license(sections["license"]),
        "maintainer": sections.pop("author"),
        "maintainer_email": sections.pop("author_email"),
    }

    return sections


def create_inline_array(input_dict: dict[str, str]) -> Array:
    """Creates a tomlkit array on inline tables for authors/maintainers"""
    array = tomlkit.array()
    for name, email in input_dict.items():
        inline_table = tomlkit.inline_table()
        inline_table.update(
            {"name": name, "email": email} if email else {"name": name}
        )
        array.append(inline_table)

    return array


def update_classifiers(classifiers: list[str]) -> Array:
    """Creates a tomlkit array of project classifiers"""
    array = tomlkit.array()
    array.extend(classifiers)
    return array


def update_dependencies(
    requirements: list[str], proj_dependencies: list[str]
) -> Array:
    """
    Creates a tomlkit array of project dependencies from existing dependencies
    and requirements
    """
    array = tomlkit.array()
    dependencies: dict[str, str] = {
        re.split(r"[<>=!~]", dependency)[0].strip(): dependency
        for dependency in proj_dependencies
    }

    array.extend(dependencies[package] for package in requirements)
    return array


def update_maintainers(sections: dict[str, str | list[str]]) -> Array:
    """Creates an array of project maintainers"""
    maintainers = {
        "Ashlynn Antrobus": "ashlynn@prosepal.io",
        sections["maintainer"]: sections["maintainer_email"],
    }
    return create_inline_array(maintainers)


def update_py_version(classifiers: list[str]) -> str:
    """Build the `requires_python` string"""
    requires_python = min(
        (
            classifier.strip("Programming Language :: Python :: ")
            for classifier in classifiers
            if "Programming Language" in classifier
        ),
        key=lambda version: int(version.split(".")[1]),
    )

    return f">={requires_python}"


def update_urls(proj_urls: Table, home_url: str) -> Table:
    """Create a urls table from new homepage url and other existing urls"""
    urls = tomlkit.table()
    urls.add("Homepage", home_url)
    for page, url in proj_urls.value.body:
        if page != "Homepage":
            urls.add(page, url)
    return urls


def update_table_item(
    item: str, project: Table, sections: dict, authors: dict
) -> Table:
    """Returns the updated value for a project table item."""
    handlers = {
        "authors": lambda: create_inline_array(authors),
        "classifiers": lambda: update_classifiers(sections["classifiers"]),
        "dependencies": lambda: update_dependencies(
            sections["install_requires"], project["dependencies"]
        ),
        "maintainers": lambda: update_maintainers(sections),
        "requires-python": lambda: update_py_version(sections["classifiers"]),
        "urls": lambda: update_urls(project["urls"], sections["url"]),
    }
    value = handlers.get(item, lambda: sections.get(item))()
    if item in {"classifiers", "dependencies", "authors", "maintainers"}:
        value.multiline(True)
    return value


def sort_project_table(
    toml: tomlkit.TOMLDocument,
    sections: dict[str, str | list],
    authors: dict[str, str],
) -> tomlkit.TOMLDocument:
    order = [
        "name",
        "version",
        "description",
        "readme",
        "requires-python",
        "license",
        "keywords",
        "classifiers",
        "maintainers",
        "authors",
        "nl",  # A blank line
        "dependencies",
        "urls",
    ]

    table = tomlkit.table()

    for item in order:
        if item == "nl":
            table.add(tomlkit.nl())
            continue
        value = (
            update_table_item(item, toml["project"], sections, authors)
            or toml["project"][item]
        )
        table.raw_append(item, value)

    toml["project"] = table

    return toml


def update_pyproject(
    toml_file: str,
    sections: dict[str, str | list[str]],
    authors: dict[str, str],
) -> None:
    """Updates pyproject.toml with new values."""
    with open(toml_file, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)

    updated_doc = sort_project_table(doc, sections, authors)
    toml_text = re.sub("\n\n\n", "\n\n", tomlkit.dumps(updated_doc))

    with open(toml_file, "w", encoding="utf-8") as f:
        f.write(toml_text)


def update_config(
    config: dict[str, str | list[str]], supported_versions: list[str]
) -> dict[str, str | list[str]]:
    """
    Update the setup configuration dictionary with new values.
    """
    description = config["description"]
    config["description"] = description.replace("and kindle ", "").replace(
        "and Kindle ", ""
    )

    config["keywords"] = ["ebook", "epub"]

    classifiers = config["classifiers"]
    new_classifiers = []
    python_section_added = False

    for classifier in classifiers:
        if "License" in classifier:
            continue
        if "Programming Language :: Python :: " not in classifier:
            new_classifiers.append(classifier)
            continue
        if python_section_added:
            continue
        python_section_added = True
        new_classifiers.extend(
            f"Programming Language :: Python :: {version}"
            for version in supported_versions
        )

    config["classifiers"] = new_classifiers
    return config


def get_value(node: ast.AST) -> str | list[str]:
    """Helper function to convert AST nodes to Python values"""
    nodes = {
        ast.Constant: lambda n: n.value,
        ast.List: lambda n: [get_value(elt) for elt in n.elts],
        ast.Call: lambda n: get_value(n.args[0]),
    }
    return nodes[type(node)](node)


def is_setup_call(node: ast.AST) -> bool:
    """
    Check if the node is a call to the `setup` function.
    """
    return (
        hasattr(node, "value")
        and hasattr(node.value, "func")
        and hasattr(node.value.func, "id")
        and node.value.func.id == "setup"
    )


def extract_setup_keywords(ast_tree: ast.AST) -> dict[str, str | list[str]]:
    """
    Extract keyword arguments and their values from the setup() call in an AST
    """
    for node in ast.walk(ast_tree):
        if is_setup_call(node):
            return {
                keyword.arg: get_value(keyword.value)
                for keyword in node.value.keywords
            }
    raise ValueError("setup() call not found")


def update_keywords(setup_file: str) -> dict[str, str | list[str]]:
    with open(setup_file, "r") as f:
        tree = ast.parse(f.read())

    supported_versions = ["3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "3.12"]

    keywords = extract_setup_keywords(tree)
    return update_config(keywords, supported_versions)


def replace_setup(setup_file: str) -> None:
    legacy_setup = textwrap.dedent("""\
        from setuptools import setup

        setup()
    """).strip("\n")

    with open(setup_file, "w") as f:
        f.write(legacy_setup)


def main(author_file: str, setup_file: str, pyproject_file: str) -> None:
    authors = parse_authors(author_file)
    keywords = update_keywords(setup_file)
    sections = parse_setup(keywords)
    update_pyproject(pyproject_file, sections, authors)
    replace_setup(setup_file)


if __name__ == "__main__":
    _, setup_file, author_file, pyproject_file = sys.argv
    main(author_file, setup_file, pyproject_file)
