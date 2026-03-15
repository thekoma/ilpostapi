import html
import re


def clean_html_text(text: str) -> str:
    """Pulisce il testo da tag HTML e caratteri speciali."""
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)

    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\n": " ",
        "\r": " ",
        "\t": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = " ".join(text.split())
    return text.strip()


def format_duration(milliseconds: int) -> str:
    """Converte i millisecondi in formato MM:SS."""
    if not milliseconds:
        return "N/D"

    total_seconds = milliseconds // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def format_date_main(isodate):
    """Formatta giorno e mese della data."""
    if not isodate:
        return "N/D"
    try:
        from datetime import datetime

        date = datetime.fromisoformat(isodate.replace("Z", "+00:00"))
        return f"{date.day:02d}/{date.month:02d}"
    except (ValueError, AttributeError):
        return "N/D"


def format_date_year(isodate):
    """Estrae l'anno dalla data."""
    if not isodate:
        return ""
    try:
        from datetime import datetime

        date = datetime.fromisoformat(isodate.replace("Z", "+00:00"))
        return str(date.year)
    except (ValueError, AttributeError):
        return ""


def format_date_time(isodate):
    """Formatta l'ora della data."""
    if not isodate:
        return ""
    try:
        from datetime import datetime

        date = datetime.fromisoformat(isodate.replace("Z", "+00:00"))
        return f"{date.hour:02d}:{date.minute:02d}"
    except (ValueError, AttributeError):
        return ""


def escapejs(text):
    """Escape di stringhe per JavaScript."""
    if not text:
        return ""
    text = str(text)
    chars = {
        "\\": "\\\\",
        '"': '\\"',
        "'": "\\'",
        "\n": "\\n",
        "\r": "\\r",
        "\t": "\\t",
        "\f": "\\f",
        "\b": "\\b",
        "<": "\\u003C",
        ">": "\\u003E",
        "&": "\\u0026",
    }
    return "".join(chars.get(c, c) for c in text)
