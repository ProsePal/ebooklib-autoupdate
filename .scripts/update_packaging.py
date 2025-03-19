# /// script
# dependencies = [
#     "tomlkit",
# ]
# ///

import ast
import json
import re
import sys
from collections.abc import Callable, Generator
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, TypeAlias

import tomlkit
from tomlkit.items import Array, Table


MIN_PY3_SUPPORTED_VERSION = 9
MAX_PY3_SUPPORTED_VERSION = 12

FORK_MAINTAINER = {"name": "Ashlynn Antrobus", "email": "ashlynn@prosepal.io"}

LEGACY_SETUP = "from setuptools import setup\n\n\nsetup()\n"

Configuration: TypeAlias = str | list[str] | dict[str, Any]
PyProject: TypeAlias = dict[str, Configuration]


class Format(Enum):
    SETUP = "setup.py"
    PYPROJECT = "pyproject.toml"


@cache
def build_supported_versions_list(
    min_version: int = MIN_PY3_SUPPORTED_VERSION,
    max_version: int = MAX_PY3_SUPPORTED_VERSION,
) -> list[str]:
    """Build a list of supported Python versions."""
    assert min_version <= max_version
    return [f"3.{version}" for version in range(min_version, max_version + 1)]


def replace_setup(setup_path: Path, legacy_setup: str = LEGACY_SETUP) -> None:
    """Replace the existing setup.py file"""
    with setup_path.open("w", encoding="utf-8") as f:
        f.write(legacy_setup)


def parse_authors(authors_path: Path) -> dict[str, str]:
    """Parse the authors file and return a dictionary of names and emails."""
    authors = {}
    lines = [line.strip() for line in authors_path.read_text().splitlines()]

    for line in lines:
        if line.startswith("Listed"):
            continue
        name, email = line.split(" <") if "<" in line else (line, "")
        authors[name] = email.strip(">")

    return authors


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


def update_maintainers(
    sections: dict[str, str | list[str]],
    auto_maintainer: dict = FORK_MAINTAINER,
) -> Array:
    """Creates a tomlkit inline array of project maintainers"""
    maintainers = {
        auto_maintainer["name"]: auto_maintainer["email"],
        sections["maintainer"]: sections["maintainer_email"],
    }
    return create_inline_array(maintainers)


def min_supported_py_version() -> str:
    """Build the `requires_python` string"""
    versions = build_supported_versions_list()
    requires_python = min(versions)

    return f">={requires_python}"


def update_urls(proj_urls: Table, home_url: str) -> Table:
    """Create a urls table from new homepage url and other existing urls"""
    urls = tomlkit.table()
    urls.add("Homepage", home_url)
    if not proj_urls or proj_urls.value is None:
        return urls

    for page, url in proj_urls.value.body:
        if page != "Homepage":
            urls.add(page, url)
    return urls


def update_table_item(
    item: str, project: Table, sections: dict, authors: dict
) -> Table:
    """Returns the updated value for a project table item."""
    match item:
        case "authors":
            value = create_inline_array(authors)
        case "classifiers":
            value = update_classifiers(sections["classifiers"])
        case "dependencies":
            value = (
                update_dependencies("", sections.get("dependencies"))
                if sections.get("dependencies")
                else update_dependencies(
                    sections["install_requires"],
                    project["dependencies"],
                )
            )
        case "maintainers":
            value = update_maintainers(sections)
        case "requires-python":
            value = sections.get("requires_python", min_supported_py_version())
        case "urls":
            value = sections.get(
                "urls", update_urls(project["urls"], sections["url"])
            )
        case _:
            value = sections.get(item)
    if item in {"classifiers", "dependencies", "authors", "maintainers"}:
        value.multiline(True)
    return value


def sort_project_table(
    doc: tomlkit.TOMLDocument,
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
            update_table_item(item, doc["project"], sections, authors)
            or doc["project"][item]
        )
        table.raw_append(item, value)

    doc["project"] = table

    return doc


def update_pyproject(
    toml_path: Path,
    sections: dict[str, str | list[str]],
    authors: dict[str, str],
) -> None:
    """Updates pyproject.toml with new values."""
    with open(toml_path, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)

    updated_doc = sort_project_table(doc, sections, authors)
    toml_text = re.sub("\n{3,}", "\n\n", tomlkit.dumps(updated_doc))

    with toml_path.open("w", encoding="utf-8") as f:
        f.write(toml_text)


def find_license_id(
    license_name: str, license_data: dict
) -> Generator[str, None, None]:
    """Yield a SPDX license ID for the given license name."""
    licenses = license_data.get("licenses", [])
    normalized_name = license_name.lower().strip()

    yield from (
        license["licenseId"]
        for license in licenses
        if license["name"].lower().startswith(normalized_name)
    )


def convert_license(license: str, license_data: dict) -> str:
    """
    Convert a license name to a SPDX license ID.

    Return the first SPDX license ID found for the given license name or raise a ValueError.

    Args:
        license (str): The name of the license.
        license_data (dict): The SPDX license JSON data.

    Returns:
        str: The SPDX license ID.
    """
    try:
        spdx_id = next(find_license_id(license, license_data))
        return '{text = "%s"}' % spdx_id
    except StopIteration as e:
        raise ValueError(f"License ID not found for '{license}'") from e


def convert_long_description(long_description: str) -> str:
    """
    Return the file name from the `long_description` function call in the
    setup.py AST.
    """
    return long_description.lstrip("read(").rstrip(")").strip("'\"")


def get_value(node: ast.AST) -> str | list[str]:
    """Helper function to convert AST nodes to Python values"""
    match node:
        case ast.Constant(value=value):
            return value
        case ast.List(elts=elts):
            return [get_value(elt) for elt in elts]
        case ast.Call(args=args):
            return get_value(args[0])
    raise ValueError(f"Unhandled AST node type: {type(node)}")


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


def parse_ast(setup_path: Path) -> dict[str, str | list[str]]:
    """Parse the setup.py file and return the project configuration."""
    tree = ast.parse(setup_path.read_text(encoding="utf-8"))

    return extract_setup_keywords(tree)


def parse_pyproject(pyproject_path: Path) -> dict[str, str | list[str]]:
    """Parse the pyproject.toml file and return the project configuration."""
    with open(pyproject_path, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)
    return doc["project"]


class ProjectParser:
    """Parser for Python project configuration files."""

    MUTUAL_SECTIONS = [
        "version",
        "license",
        "description",
        "keywords",
        "classifiers",
    ]

    FORMAT_SECTIONS = {
        Format.SETUP: [
            "author",
            "author_email",
            "long_description",
            "url",
            "install_requires",
        ],
        Format.PYPROJECT: [
            "authors",
            "maintainers",
            "readme",
            "dependencies",
            "requires_python",
            "urls",
        ],
    }

    def __init__(self, license_data: dict[str, Any]):
        """
        Initialize the project configuration parser.

        Args:
            license_data: dictionary of license information for conversion
        """
        self.license_data = license_data
        self._transformers: dict[
            str, Callable[[Configuration], Configuration]
        ] = {
            "description": self._transform_description,
            "keywords": self._transform_keywords,
            "classifiers": self._transform_classifiers,
        }

    @staticmethod
    def detect_format(
        setup_path: Path, legacy_setup_content: str = LEGACY_SETUP
    ) -> Format:
        """
        Detect the configuration format based on setup.py content.

        Args:
            setup_path: Path to setup.py file
            legacy_setup_content: Content of legacy setup.py that indicates pyproject usage

        Returns:
            Detected configuration format
        """
        content = setup_path.read_text(encoding="utf-8")
        return (
            Format.PYPROJECT
            if content.strip() == legacy_setup_content
            else Format.SETUP
        )

    def parse(
        self, config_format: Format, setup_path: Path, pyproject_path: Path
    ) -> PyProject:
        """
        Parse the project configuration based on the detected format.

        Args:
            config_format: The configuration format to use
            setup_path: Path to setup.py file
            pyproject_path: Path to pyproject.toml file

        Returns:
            Parsed and normalized project configuration
        """
        raw_config = (
            parse_ast(setup_path)
            if config_format == Format.SETUP
            else parse_pyproject(pyproject_path)
        )

        transformed_config = self._apply_transformations(raw_config)
        return self._normalize_config(transformed_config, config_format)

    def _apply_transformations(self, config: PyProject) -> PyProject:
        """Apply transformations to configuration values."""
        result = config.copy()

        for key, transformer in self._transformers.items():
            if key in result:
                result[key] = transformer(result[key])

        return result

    def _normalize_config(
        self, config: PyProject, format: Format
    ) -> PyProject:
        """
        Normalize configuration to a consistent format regardless of source.

        Args:
            config: The configuration to normalize
            source_format: The format the configuration came from

        Returns:
            Normalized configuration
        """
        sections: PyProject = {
            keyword: config[keyword] for keyword in config
        } | {
            keyword: config[keyword]
            for keyword in self.FORMAT_SECTIONS[format]
        }

        if format == Format.SETUP:
            sections |= {
                "readme": sections.pop("long_description"),
                "license": convert_license(
                    sections["license"], self.license_data
                ),
                "maintainer": sections.pop("author"),
                "maintainer_email": sections.pop("author_email"),
            }

        return sections

    def _transform_description(self, description: str) -> str:
        """Transform the project description."""
        return description.replace("and kindle ", "").replace(
            "and Kindle ", ""
        )

    def _transform_keywords(self, _: Any) -> list[str]:
        """Transform keywords."""
        return ["ebook", "epub"]

    def _transform_classifiers(self, classifiers: list[str]) -> list[str]:
        """Transform Python classifiers."""
        supported_versions = build_supported_versions_list()
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

        return new_classifiers


def main(
    author_path: Path,
    setup_path: Path,
    pyproject_path: Path,
    license_path: Path,
) -> None:
    """
    Main function.

    Args:
        author_file (Path): Path to the authors file.
        setup_file (Path): Path to the setup.py file.
        pyproject_file (Path): Path to the pyproject.toml file.
        license_file (Path): Path to the license file.
    """
    authors = parse_authors(author_path)

    with license_path.open("r", encoding="utf-8") as f:
        license_data = json.load(f)

    parser = ProjectParser(license_data)
    update_file = parser.detect_format(setup_path)
    print(f"Detected format: {update_file.value}")

    sections = parser.parse(update_file, setup_path, pyproject_path)
    update_pyproject(pyproject_path, sections, authors)
    replace_setup(setup_path)


if __name__ == "__main__":
    _, setup_file, author_file, pyproject_file, license_file = sys.argv
    setup_path = Path(setup_file)
    author_path = Path(author_file)
    pyproject_path = Path(pyproject_file)
    license_path = Path(license_file)
    main(author_path, setup_path, pyproject_path, license_path)
