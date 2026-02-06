"""RSS feed fetching and parsing."""

import re
from datetime import datetime, timezone

import feedparser

from .models import RssPost


def extract_image_urls(content: str) -> list[str]:
    """Extract image URLs from HTML content."""
    # Match src attributes in img tags
    img_pattern = r'<img[^>]+src=["\']([^"\']+)["\']'
    urls = re.findall(img_pattern, content, re.IGNORECASE)
    return urls


def time_struct_to_datetime(time_struct) -> datetime | None:
    """Convert feedparser time struct to datetime."""
    if not time_struct:
        return None
    try:
        return datetime(*time_struct[:6], tzinfo=timezone.utc)
    except Exception:
        return None


def fetch_feed(url: str) -> list[RssPost]:
    """Fetch and parse an RSS feed, returning posts."""
    feed = feedparser.parse(url)
    posts = []

    for entry in feed.entries:
        # Get content - try different fields
        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            content = entry.summary
        elif hasattr(entry, "description"):
            content = entry.description

        # Extract images from content
        image_urls = extract_image_urls(content)

        # Also check for enclosures (attachments)
        if hasattr(entry, "enclosures"):
            for enc in entry.enclosures:
                if enc.get("type", "").startswith("image/"):
                    image_urls.append(enc.get("href", ""))

        # Parse published date (feedparser pre-parses into *_parsed attributes)
        published = None
        if hasattr(entry, "published_parsed"):
            published = time_struct_to_datetime(entry.published_parsed)
        elif hasattr(entry, "updated_parsed"):
            published = time_struct_to_datetime(entry.updated_parsed)

        # Extract author
        author = None
        if hasattr(entry, "author"):
            author = entry.author
        elif hasattr(entry, "author_detail"):
            author = entry.author_detail.get("name")

        post = RssPost(
            guid=entry.get("id", entry.get("link", "")),
            title=entry.get("title", ""),
            link=entry.get("link", ""),
            content=content,
            author=author,
            published=published,
            image_urls=image_urls,
        )
        posts.append(post)

    return posts
