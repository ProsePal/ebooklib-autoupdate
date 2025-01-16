import re
import sys


def update_readme(readme_file: str) -> None:
    with open(readme_file, "r") as f:
        content: str = f.read()

    sections: list[str] = re.split(r"(```.*?```)", content, flags=re.DOTALL)
    updated_sections: list[str] = []

    for section in sections:
        if not section.startswith("```"):
            section = re.sub(
                r"^(#+)(\s)", r"#\1\2", section, flags=re.MULTILINE
            )
            section = section.replace("and kindle ", "")
        updated_sections.append(section)

    preamble = (
        "# EbookLib-autoupdate\n\n"
        "This is a fork of the popular Ebooklib library that aims to keep a "
        "package updated with changes from the original codebase. Any changes"
        " to [https://github.com/aerkalov/ebooklib] are merged into this "
        "package on a weekly basis.\n\n"
    )

    text = preamble + "".join(updated_sections)

    with open(readme_file, "w") as f:
        f.write(text)


if __name__ == "__main__":
    update_readme(sys.argv[1])
