import re
from selectolax.parser import HTMLParser

TAGS_TO_REMOVE = {"script", "style", "svg", "nav", "footer", "header", "noscript", "iframe"}


def prune_dom(raw_html: str) -> str:
    parser = HTMLParser(raw_html)

    for tag in parser.css(",".join(TAGS_TO_REMOVE)):
        tag.decompose()

    root = parser.css_first("main") or parser.css_first("article") or parser.css_first("body")
    if not root:
        return ""

    text = root.text(separator="\n", strip=True)
    return re.sub(r"\n\s*\n", "\n\n", text).strip()
