import re
from typing import Iterator, Optional


SPOTIFY_TRACK_LINK_PATTERN = re.compile(r"https?://open\.spotify\.com/track/([0-9a-zA-Z]+)")


def find_first_spotify_track_link(message: str) -> Optional[str]:
    """Try to find a spotify track link, return track URI."""

    match = SPOTIFY_TRACK_LINK_PATTERN.search(message)
    if match is not None:
        return match.group(1)
    else:
        return None


def find_spotify_track_links(message: str) -> Iterator[str]:
    """Find all Spotify song links."""

    for match in SPOTIFY_TRACK_LINK_PATTERN.finditer(message):
        yield f"spotify:track:{match.group(1)}"
