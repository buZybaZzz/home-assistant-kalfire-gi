"""Name new test reports using values submitted through the GitHub issue form."""

import json
import os
import re
import urllib.request

DEFAULT_TITLE = "[Test report] Gi model - firmware"
OTHER_VERSION = "Other / unknown (specify below)"


def field(body: str, label: str) -> str | None:
    pattern = r"(?m)^### " + re.escape(label) + r"[ \t]*\r?\n(?:[ \t]*\r?\n)*((?!### )[^\r\n]+)"
    match = re.search(pattern, body)
    if not match:
        return None
    value = " ".join(match.group(1).split())
    return None if value in ("_No response_", "No response", "") else value


def make_title(title: str, body: str) -> str | None:
    if title != DEFAULT_TITLE:
        return None
    model = field(body, "Exact Gi model")
    version = field(body, "Kalfire Gi Local version tested")
    if not model or not version:
        return None
    if version == OTHER_VERSION:
        version = field(body, "Other integration version or build") or "unknown version"

    # GitHub limits issue titles to 256 characters. Avoid invisible control characters.
    def clean(value: str) -> str:
        return "".join(c for c in value if c.isprintable()).strip()

    model, version = clean(model), clean(version)
    if not model or not version:
        return None
    return f"[Test report] {model[:120]} — {version[:115]}"[:256]


def api_request(url: str, token: str, payload: dict | None = None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "kalfire-gi-test-report-title",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url, data=data, headers=headers, method="PATCH" if data else "GET"
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> None:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as event_file:
        event = json.load(event_file)
    issue = event["issue"]
    # Restrict writes to this repository and preserve an author-edited title.
    url = f"{os.environ['GITHUB_API_URL']}/repos/{os.environ['GITHUB_REPOSITORY']}/issues/{issue['number']}"
    token = os.environ["GITHUB_TOKEN"]
    current = api_request(url, token)
    new_title = make_title(current["title"], current.get("body") or "")
    if new_title:
        api_request(url, token, {"title": new_title})
        print("Updated test report title")
    else:
        print("Not a default test report, missing fields, or title already changed; skipped")


if __name__ == "__main__":
    main()
