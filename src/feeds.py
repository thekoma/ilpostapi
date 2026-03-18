import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urlparse, urlunparse

from helpers import clean_html_text
from utils.logging import get_logger

logger = get_logger(__name__)


def _clean(text: str) -> str:
    """Pulisce il testo per i feed XML."""
    if not text:
        return ""
    return clean_html_text(text)


def _clean_html_attrs(html: str) -> str:
    """Rimuove attributi data-* e tag <style> dall'HTML."""
    if not html:
        return ""
    html = re.sub(r'<style[^>]*>.*?</style>', "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'\s+data-[\w-]+="[^"]*"', "", html)
    return html


def _sanitize_url(url: str) -> str:
    """Percent-encode caratteri non-ASCII nell'URL (es. … → %E2%80%A6)."""
    if not url:
        return ""
    parsed = urlparse(url)
    safe_path = quote(parsed.path, safe="/:@!$&'()*+,;=-._~")
    return urlunparse(parsed._replace(path=safe_path))


class PodcastRSSGenerator:
    def generate_feed(self, podcast_data, episodes_data, request_base_url, self_url=None):
        base_url = os.getenv("BASE_URL") or request_base_url.rstrip("/")
        podcast_id = podcast_data["id"]

        rss = ET.Element(
            "rss",
            {
                "version": "2.0",
                "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
                "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
                "xmlns:atom": "http://www.w3.org/2005/Atom",
            },
        )

        channel = ET.SubElement(rss, "channel")

        # --- Channel metadata ---

        # Atom self-link (required for validation)
        atom_link = ET.SubElement(channel, "atom:link")
        atom_link.set("href", self_url or f"{base_url}/podcast/{podcast_id}/rss")
        atom_link.set("rel", "self")
        atom_link.set("type", "application/rss+xml")

        # Title
        title = ET.SubElement(channel, "title")
        title.text = _clean(podcast_data["title"])

        # Link - use share_url from Il Post if available
        link = ET.SubElement(channel, "link")
        link.text = podcast_data.get("share_url") or f"{base_url}/podcast/{podcast_id}"

        # Description
        description = ET.SubElement(channel, "description")
        description.text = _clean(podcast_data.get("description", ""))

        # Author (multiple formats for max compatibility)
        author_name = _clean(podcast_data.get("author", "Il Post"))

        managing_editor = ET.SubElement(channel, "managingEditor")
        managing_editor.text = f"podcast@ilpost.it ({author_name})"

        itunes_author = ET.SubElement(channel, "itunes:author")
        itunes_author.text = author_name

        # Image (multiple formats)
        image_url = podcast_data.get("image", "")

        if image_url:
            image = ET.SubElement(channel, "image")
            img_title = ET.SubElement(image, "title")
            img_title.text = _clean(podcast_data["title"])
            img_url = ET.SubElement(image, "url")
            img_url.text = image_url
            img_link = ET.SubElement(image, "link")
            img_link.text = podcast_data.get("share_url") or f"{base_url}/podcast/{podcast_id}"

            itunes_image = ET.SubElement(channel, "itunes:image")
            itunes_image.set("href", image_url)

        # Language
        language = ET.SubElement(channel, "language")
        language.text = "it"

        # Copyright
        copyright_elem = ET.SubElement(channel, "copyright")
        copyright_elem.text = f"\u00a9 {datetime.now().year} {author_name}"

        # Category
        itunes_category = ET.SubElement(channel, "itunes:category")
        itunes_category.set("text", "News")
        itunes_subcategory = ET.SubElement(itunes_category, "itunes:category")
        itunes_subcategory.set("text", "Daily News")

        # Explicit
        itunes_explicit = ET.SubElement(channel, "itunes:explicit")
        itunes_explicit.text = "false"

        # Type (episodic vs serial)
        itunes_type = ET.SubElement(channel, "itunes:type")
        itunes_type.text = "episodic"

        # Owner
        itunes_owner = ET.SubElement(channel, "itunes:owner")
        itunes_name = ET.SubElement(itunes_owner, "itunes:name")
        itunes_name.text = author_name
        itunes_email = ET.SubElement(itunes_owner, "itunes:email")
        itunes_email.text = "podcast@ilpost.it"

        # --- Episodes ---

        for ep in episodes_data["data"]:
            item = ET.SubElement(channel, "item")

            ep_audio_url = _sanitize_url(ep["episode_raw_url"])
            ep_share_url = ep.get("share_url") or ""

            # GUID - prefer share_url (stable permalink) over audio URL
            guid = ET.SubElement(item, "guid")
            if ep_share_url:
                guid.text = ep_share_url
                guid.set("isPermaLink", "true")
            else:
                guid.text = ep_audio_url
                guid.set("isPermaLink", "true")

            # Title
            ep_title = ET.SubElement(item, "title")
            ep_title.text = _clean(ep["title"])

            # Link - canonical URL to episode page
            ep_link = ET.SubElement(item, "link")
            ep_link.text = ep_share_url or ep.get("url") or ep_audio_url

            # Description / Summary / Content
            content_html = ep.get("content_html") or ep.get("description", "")
            summary_text = ep.get("summary", "")
            description_clean = _clean(content_html)

            if description_clean:
                item_desc = ET.SubElement(item, "description")
                item_desc.text = description_clean

                # content:encoded preserves HTML
                content_encoded = ET.SubElement(item, "content:encoded")
                content_encoded.text = _clean_html_attrs(content_html)

            # itunes:summary - use the short summary if available, otherwise description
            itunes_summary = ET.SubElement(item, "itunes:summary")
            if summary_text:
                itunes_summary.text = _clean(summary_text)
            elif description_clean:
                itunes_summary.text = description_clean[:4000]

            # Author - per-episode author (can differ from podcast author)
            ep_author_name = _clean(ep.get("author", "")) or author_name

            ep_author = ET.SubElement(item, "author")
            ep_author.text = f"podcast@ilpost.it ({ep_author_name})"

            itunes_author_ep = ET.SubElement(item, "itunes:author")
            itunes_author_ep.text = ep_author_name

            # Episode image (per-episode artwork)
            ep_image = ep.get("image")
            if ep_image:
                itunes_ep_image = ET.SubElement(item, "itunes:image")
                itunes_ep_image.set("href", ep_image)

            # Publication date
            if ep.get("date"):
                pubDate = ET.SubElement(item, "pubDate")
                try:
                    pub_date = datetime.fromisoformat(ep["date"])
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone(timedelta(hours=1)))
                    pubDate.text = pub_date.strftime("%a, %d %b %Y %H:%M:%S %z")
                except (ValueError, TypeError):
                    pubDate.text = datetime.now(
                        tz=timezone(timedelta(hours=1))
                    ).strftime("%a, %d %b %Y %H:%M:%S %z")

            # Duration
            if ep.get("milliseconds") is not None:
                duration_secs = ep["milliseconds"] // 1000
                hours = duration_secs // 3600
                minutes = (duration_secs % 3600) // 60
                seconds = duration_secs % 60

                itunes_duration = ET.SubElement(item, "itunes:duration")
                if hours > 0:
                    itunes_duration.text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    itunes_duration.text = f"{minutes:02d}:{seconds:02d}"

            # Episode type
            ep_type = ep.get("episode_type", "full")
            if ep_type and ep_type != "full":
                itunes_ep_type = ET.SubElement(item, "itunes:episodeType")
                itunes_ep_type.text = ep_type

            # Enclosure (audio file)
            enclosure = ET.SubElement(item, "enclosure")
            enclosure.set("url", ep_audio_url)
            enclosure.set("type", "audio/mpeg")
            enclosure.set("length", str(ep.get("size", "0")))

        return ET.tostring(rss, encoding="unicode", method="xml", xml_declaration=True)


class PodcastRDFGenerator:
    def generate_feed(self, podcast_data, episodes_data, request_base_url):
        base_url = os.getenv("BASE_URL") or request_base_url.rstrip("/")
        podcast_id = podcast_data["id"]

        rdf = ET.Element(
            "rdf:RDF",
            {
                "xmlns:rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                "xmlns": "http://purl.org/rss/1.0/",
                "xmlns:dc": "http://purl.org/dc/elements/1.1/",
                "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
                "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            },
        )

        channel_url = podcast_data.get("share_url") or f"{base_url}/podcast/{podcast_id}"

        channel = ET.SubElement(
            rdf, "channel", {"rdf:about": f"{base_url}/podcast/{podcast_id}/rdf"}
        )

        title = ET.SubElement(channel, "title")
        title.text = _clean(podcast_data["title"])

        link = ET.SubElement(channel, "link")
        link.text = channel_url

        description = ET.SubElement(channel, "description")
        description.text = _clean(podcast_data.get("description", ""))

        dc_language = ET.SubElement(channel, "dc:language")
        dc_language.text = "it"

        dc_publisher = ET.SubElement(channel, "dc:publisher")
        dc_publisher.text = "Il Post"

        author_name = _clean(podcast_data.get("author", "Il Post"))

        author = ET.SubElement(channel, "author")
        name = ET.SubElement(author, "name")
        name.text = author_name
        uri = ET.SubElement(author, "uri")
        uri.text = podcast_data.get("share_url") or "https://www.ilpost.it"

        dc_creator = ET.SubElement(channel, "dc:creator")
        dc_creator.text = author_name

        # Image
        if podcast_data.get("image"):
            itunes_image = ET.SubElement(channel, "itunes:image")
            itunes_image.set("href", podcast_data["image"])

        items = ET.SubElement(channel, "items")
        seq = ET.SubElement(items, "rdf:Seq")

        for ep in episodes_data["data"]:
            ep_audio_url = _sanitize_url(ep["episode_raw_url"])
            ep_url = ep.get("share_url") or ep_audio_url

            ET.SubElement(seq, "rdf:li", {"rdf:resource": ep_url})

            item = ET.SubElement(rdf, "item", {"rdf:about": ep_url})

            item_title = ET.SubElement(item, "title")
            item_title.text = _clean(ep["title"])

            item_link = ET.SubElement(item, "link")
            item_link.text = ep_url

            # Description
            content_html = ep.get("content_html") or ep.get("description", "")
            if content_html:
                item_desc = ET.SubElement(item, "description")
                item_desc.text = _clean(content_html)

                content_encoded = ET.SubElement(item, "content:encoded")
                content_encoded.text = _clean_html_attrs(content_html)

            # Summary
            if ep.get("summary"):
                dc_abstract = ET.SubElement(item, "dc:description")
                dc_abstract.text = _clean(ep["summary"])

            # Per-episode author
            ep_author_name = _clean(ep.get("author", "")) or author_name
            dc_ep_creator = ET.SubElement(item, "dc:creator")
            dc_ep_creator.text = ep_author_name

            # Date
            if ep.get("date"):
                dc_date = ET.SubElement(item, "dc:date")
                try:
                    pub_date = datetime.fromisoformat(ep["date"])
                    dc_date.text = pub_date.strftime("%Y-%m-%dT%H:%M:%S%z")
                except (ValueError, TypeError):
                    dc_date.text = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")

            # Enclosure
            ET.SubElement(
                item,
                "enclosure",
                {"rdf:resource": ep_audio_url, "type": "audio/mpeg"},
            )

        return ET.tostring(rdf, encoding="unicode", method="xml", xml_declaration=True)


rss_generator = PodcastRSSGenerator()
rdf_generator = PodcastRDFGenerator()
