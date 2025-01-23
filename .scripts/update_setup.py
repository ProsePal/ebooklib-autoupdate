# /// script
# dependencies = [
#     "requests",
#     "toml",
# ]
# ///

import ast
import re
import sys
from collections.abc import Generator

import requests
import toml


def create_author_line(sections: dict) -> str:
    name = sections["author"]
    email = sections["author_email"]

    return "{ " + f"name = {name}, email = {email} " + "}"


def convert_long_description(long_description: str) -> str:
    return long_description.lstrip("read(").rstrip(")").strip("'\"")


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
        return spdx_id
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
        lines = [line.strip() for line in file]

    lines = iter(lines)

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

        elif isinstance(sections.get(key), list):
            if line == "]":
                continue
            sections[key].append(line.strip("\"'"))

    sections["author"] = create_author_line(sections)
    sections.pop("author_email")
    sections["readme"] = convert_long_description(sections["long_description"])
    sections.pop("long_description")
    sections["license"] = convert_license(sections["license"])

    return sections


def update_pyproject(toml_file: str, sections: dict[str, str | list[str]]):
    """Updates pyproject.toml with new values."""
    with open(toml_file, "r") as f:
        data = toml.load(f)

    dependencies: dict[str, str] = {
        re.split(r"[<>=!~]", dependency)[0].strip(): dependency
        for dependency in data["project"]["dependencies"]
    }

    requires_python = min(
        classifier.strip("Programming Language :: Python :: ")
        for classifier in sections["classifiers"]
        if "Python" in classifier
    )

    data["project"]["requires-python"] = f">={requires_python}"

    for key, value in sections.items():
        if key == "install_requires":
            for dependency in dependencies:
                if dependency not in value:
                    data["project"]["dependencies"].remove(
                        dependencies[dependency]
                    )
        elif key == "url":
            data["project"]["urls"]["Homepage"] = value
        else:
            data["project"][key] = value

    with open(toml_file, "w") as f:
        toml.dump(data, f)


def update_setup_config(
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


def make_value(value: str | list[str]) -> ast.AST:
    nodes = {
        str: ast.Constant(value),
        list: ast.List(
            elts=[ast.Constant(value=x) for x in value], ctx=ast.Load()
        ),
    }
    return nodes[type(value)]


def make_call_value(id: str, value: str) -> ast.Call:
    return ast.Call(
        func=ast.Name(id=id, ctx=ast.Load()), args=[make_value(value)]
    )


def extract_setup_keywords(ast_tree: ast.AST) -> dict[str, str | list[str]]:
    """
    Extract keyword arguments and their values from the setup() call in an AST
    """
    for node in ast.walk(ast_tree):
        if (
            hasattr(node, "value")
            and hasattr(node.value, "func")
            and hasattr(node.value.func, "id")
            and node.value.func.id == "setup"
        ):
            return {
                keyword.arg: get_value(keyword.value)
                for keyword in node.value.keywords
            }
    raise ValueError("setup() call not found")


def build_setup_ast(
    tree: ast.AST, config: dict[str, str | list[str]]
) -> ast.AST:
    """
    Build a new AST for setup.py from config dictionary.
    """
    keywords = []
    for key, value in config.items():
        ast.keyword(
            arg=key, value=make_call_value("read", value)
        ) if key == "long_description" else ast.keyword(
            arg=key, value=make_value(value)
        )

    for node in ast.walk(tree):
        if (
            hasattr(node, "value")
            and hasattr(node.value, "func")
            and hasattr(node.value.func, "id")
            and node.value.func.id == "setup"
        ):
            node.value.keywords = keywords

    return tree


def update_setup(setup_file: str) -> dict[str, str | list[str]]:
    with open(setup_file, "r") as f:
        tree = ast.parse(f.read())

    supported_versions = ["3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "3.12"]

    keywords = extract_setup_keywords(tree)
    updated_keywords = update_setup_config(keywords, supported_versions)
    transformed_ast = build_setup_ast(tree, updated_keywords)

    with open(setup_file, "w") as f:
        f.write(ast.unparse(transformed_ast))

    return updated_keywords


if __name__ == "__main__":
    update_setup(sys.argv[1])
    sections = parse_setup(sys.argv[1])
    update_pyproject(sys.argv[2], sections)
