"""Update issue form options from GitHub published releases."""

import json
import os
import pathlib
import urllib.request

TEMPLATE = pathlib.Path(".github/ISSUE_TEMPLATE/test-report.yml")
START = "        # BEGIN RELEASE VERSIONS\n"
END = "        # END RELEASE VERSIONS\n"


def update(releases):
    tags = list(dict.fromkeys(item["tag_name"] for item in releases if not item["draft"]))
    if not tags:
        raise ValueError("No published releases found; keeping existing options")
    content = TEMPLATE.read_text(encoding="utf-8")
    if content.count(START) != 1 or content.count(END) != 1:
        raise ValueError("Release option markers missing or duplicated")
    before, rest = content.split(START, 1)
    _, after = rest.split(END, 1)
    options = "".join(f"        - {json.dumps(tag, ensure_ascii=True)}\n" for tag in tags)
    updated = before + START + options + END + after
    if updated != content:
        TEMPLATE.write_text(updated, encoding="utf-8")


def main():
    owner_repo = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{owner_repo}/releases?per_page=100"
    releases = []
    while url:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                "User-Agent": "kalfire-gi-version-options",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            releases.extend(json.load(response))
            links = response.headers.get("Link", "")
        url = next(
            (
                part.split(";")[0].strip().strip("<>")
                for part in links.split(",")
                if 'rel="next"' in part
            ),
            None,
        )
    update(releases)


if __name__ == "__main__":
    main()
