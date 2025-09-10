import re
from functools import lru_cache
from pathlib import Path

from beets.autotag import Item
from beets.importer import ImportSession, ImportTask, SingletonImportTask
from beets.plugins import BeetsPlugin
from beets.util import displayable_path

YOUTUBE_TITLE_JUNK = [
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?(?:Explicit|Clean|Parental\sAdvisory).*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?(?:HQ|HD|CDQ).*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?Audio.*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?Album.*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?Song.*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?Video.*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?Lyric.*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?Visualizer.*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?iTunes.*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?Official.*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?Original.*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?Version.*?[\)\]\}])"),
    re.compile(r"(?i)(?P<junk>[\(\[\{].*?Prod(?:uced|\.)?\sBy.*?[\)\]\}])"),
]


EXTRA_STRIP_PATTERNS = [
    re.compile(r"^\s*[-_\|]\s*(?P<title>.+)$"),
    re.compile(r"^(?P<title>.+)\s*[-_\|]\s*$"),
]


def track_title_from_path(p: Path) -> str:
    """Get track title from path."""
    return p.stem


def album_name_from_path(p: Path) -> str:
    """Get album name from path."""
    return p.parent.name


def artist_name_from_path(p: Path) -> str:
    """Get artist name from path."""
    return p.parent.parent.name


@lru_cache(maxsize=64)
def remove_album_name_pattern(album_name: str) -> re.Pattern:
    """Create a regex to remove an album name from a string.

    Matches (album name)
    """
    return re.compile("(?i)(?P<junk>\\({0}\\))".format(re.escape(album_name)))


@lru_cache(maxsize=64)
def remove_artist_name_pattern(artist_name: str) -> re.Pattern:
    """Create a regex to remove an artist name from a string.

    Matches (artist name) OR artist name
    """
    return re.compile("(?i)(?P<junk>\\(?{0}\\)?)".format(re.escape(artist_name)))


class FromYoutubeTitlePlugin(BeetsPlugin):
    """Set the title of each item to the filename, removing most of the common junk associated with
    YouTube titles like "(Official Audio)" and the name of the album or artist.

    This plugin works best if your music is downloaded in an Artist/Album/Track structure, since
    the album name and artist name can be inferred from that structure.

    Uses two configuration options:

    - `parent_is_album`: The parent directory of the track is the album title. Defaults to true.
      Disable if your music is not downloaded into album folders.
    - `parent_parent_is_artist`: The parent's parent directory of the track is the artist name.
      Defaults to true. Disable if your music is not in this structure.
    """

    def __init__(self):
        super(FromYoutubeTitlePlugin, self).__init__()

        self.config.add(
            {
                "parent_is_album": True,
                "parent_parent_is_artist": True,
            }
        )

        self.infer_album = self.config["parent_is_album"].get(bool)
        self.infer_artist = self.config["parent_parent_is_artist"].get(bool)

        self.register_listener("import_task_start", self.clean_youtube_metadata)

    def clean_youtube_metadata(self, task: ImportTask, session: ImportSession) -> None:
        """Clean YouTube title junk from tracks and conditionally set the album and artist."""
        if isinstance(task, SingletonImportTask) or not task.is_album:
            items = [task.item]  # type: ignore
        else:
            items = task.items

        for item in items:
            if not item.title:
                item.title = self.get_clean_title(item)

            if self.infer_album and not item.album:
                item.album = self.get_album(item)

            if self.infer_artist and not item.artist:
                item.artist = self.get_artist(item)

    def get_clean_title(self, item: Item) -> str:
        """Construct a clean title for the given track."""
        path = Path(displayable_path(item.path))

        raw_title = track_title_from_path(path)

        # Junk patterns specific to this import
        specific_junk_patterns: list[re.Pattern] = []

        if self.infer_album:
            album_name = album_name_from_path(path)
            specific_junk_patterns.append(remove_album_name_pattern(album_name))

        if self.infer_artist:
            artist_name = artist_name_from_path(path)
            specific_junk_patterns.append(remove_artist_name_pattern(artist_name))

        return self._replace_junk(raw_title, *specific_junk_patterns, *YOUTUBE_TITLE_JUNK)

    def _replace_junk(self, title: str, *patterns: re.Pattern) -> str:
        """Replace the named group 'junk' with an empty string in the title for all patterns."""
        new_title = title

        for pattern in patterns:
            match_obj = pattern.search(new_title)
            if match_obj is not None:
                new_title = new_title.replace(match_obj.group("junk"), "")

        new_title = new_title.strip()

        # Strip any leftover trailing or leading junk characters
        for pattern in EXTRA_STRIP_PATTERNS:
            match_obj = pattern.match(new_title)
            if match_obj is not None:
                new_title = match_obj.group("title")

        return new_title

    def get_album(self, item: Item) -> str:
        """Get the album name from the item's path."""
        path = Path(displayable_path(item.path))
        return album_name_from_path(path)

    def get_artist(self, item: Item) -> str:
        """Get the artist name from the item's path."""
        path = Path(displayable_path(item.path))
        return artist_name_from_path(path)
