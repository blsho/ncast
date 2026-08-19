#!/usr/bin/env python3

import feedparser
from jinja2 import Template
import sys
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import yaml
import concurrent.futures
import argparse
import aiohttp
import asyncio
import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


template = """<?xml version="1.0" encoding="{{ rss.encoding }}"?>
<rss version="2.0"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
	xmlns:content="http://purl.org/rss/1.0/modules/content/"
	xmlns:atom="http://www.w3.org/2005/Atom"
	xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
    xmlns:anchor="https://anchor.fm/xmlns"
	xmlns:podcast="https://podcastindex.org/namespace/1.0">
    <channel>
        <title>{{ rss.feed.title | escape }}</title>
        <description>{{ rss.feed.description | escape }}</description>
        <itunes:summary>{{ rss.feed.description | escape }}</itunes:summary>
        <itunes:type>episodic</itunes:type>
        {%- for link in rss.feed.links %}
        <link>{{ link.href }}</link>
        {%- endfor %}
        <image>
            <url>{{ pic }}</url>
            <title>{{ rss.feed.title | escape }}</title>
            <link>{{ rss.feed.link }}</link>
        </image>
        <lastBuildDate>{{ rss.feed.updated }}</lastBuildDate>
        <language>{{ rss.feed.language }}</language>
        <itunes:author>{{ rss.feed.link[8:] }}</itunes:author>
        <itunes:owner>
            <itunes:name>{{ rss.feed.link[8:] }}</itunes:name>
        </itunes:owner>
        <itunes:explicit>false</itunes:explicit>
        <itunes:category text="News" />
        <itunes:image href="{{ pic }}"/>
        <podcast:funding url="{{ group.funding }}">Ak chces ZdeNka, tak nebuť k*k*t a kúp si Nko.</podcast:funding>
        {%- for entry in rss.entries[:500] %}
        {%- if entry.enclosures[0] %}
        <item>
            <title>{{ entry.title | replace("\n", "") | replace("\t", "") }}</title>
            <description><![CDATA[{{ entry.description }}]]></description>
            <guid isPermaLink="false">{{ entry.guid }}</guid>
            <dc:creator>{{ entry.author }}</dc:creator>
            <pubDate>{{ entry.published }}</pubDate>
            <enclosure url="{{ entry.enclosures[0].href }}" length="{{ entry.enclosures[0].length }}" type="audio/mpeg" />
            <itunes:duration>{{ entry.itunes_duration }}</itunes:duration>
            <itunes:explicit>false</itunes:explicit>
            {%- if entry.image %}
            <itunes:image href="{{ entry.image.href }}"/>
            {%- endif %}
        </item>
        {%- endif %}
        {%- endfor %}
    </channel>
</rss>"""

web_template = """
{%- for group in config.groups %}
<h1>{{ group.header }}</h1>
<p>{{ group.description }}</p>
<table>
    <tr>
        <th>Čo</th>
        <th>Názov</th>
        <th>URL</th>
    </tr>
    {%- for feed in group.feeds %}
    <tr>
        <td>{{ feed.description }}</td>
        <td>{{ feed.name }}</td>
        <td><code>{{ feed.pub_url }}</code></td>
    </tr>
    {%- endfor %}
</table>
{%- endfor %}
"""

ua = UserAgent(os=["Windows", "Android", "iOS"], min_percentage=0.05)


def configure_logging(level_name: str = "INFO") -> None:
    """Configure the root logger using a level name from the YAML config."""
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")


def needed_episode(episode: dict[str, Any], exclude: list[str] | None) -> bool:
    """Return True when an episode should be kept according to the exclusion list."""
    try:
        if exclude:
            tags = getattr(episode, "tags", []) or []
            categories = {tag["term"] for tag in tags if isinstance(tag, dict) and "term" in tag}
            if categories.intersection(set(exclude)):
                return False
        return True
    except Exception as exc:
        logger.warning("Unable to evaluate episode exclusion for %s: %s", getattr(episode, "title", "unknown"), exc)
        return True


async def process_episode(
    episode: dict[str, Any],
    session: aiohttp.ClientSession,
    rss_podcast: Any,
) -> None:
    """Fetch the article HTML for one episode, extract audio metadata, and append it to the podcast feed."""
    episode_podcast = {}
    title = getattr(episode, "title", "unknown")
    try:
        logger.debug("Processing episode: %s", title)
        url = getattr(episode, "link", None)
        if not url:
            logger.warning("Episode %s has no link; skipping", title)
            return

        async with session.get(url, headers={"User-Agent": ua.random}) as article:
            article_text = await article.text()
            content_parser = BeautifulSoup(article_text, "html.parser")
            audio_tag = content_parser.find("audio")
            if audio_tag is None:
                logger.warning("No audio tag found for episode %s (%s)", title, url)
                return

            audio_src = audio_tag.find("source")
            if audio_src is None or not audio_src.get("src"):
                logger.warning("No audio source found for episode %s (%s)", title, url)
                return

            episode_podcast["title"] = title
            episode_podcast["author"] = getattr(episode, "author", "")
            episode_podcast["published"] = getattr(episode, "published", "")
            episode_podcast["guid"] = getattr(episode, "guid", "")
            episode_podcast["link"] = url
            episode_podcast["enclosures"] = [{"href": audio_src["src"]}]
            episode_podcast["itunes_duration"] = audio_tag.get("data-duration", "")
            episode_podcast["image"] = {}

            description_suffix = (
                f'<br><p>Viac na <a href="{url}">{url}</a></p>'
            )
            description = getattr(episode, "description", "") or ""
            episode_podcast["description"] = f"{description}{description_suffix}"

            async with session.head(
                episode_podcast["enclosures"][0]["href"],
                headers={"User-Agent": ua.random},
            ) as voice:
                if voice.status == 200:
                    length = voice.headers.get("content-length")
                    if length is not None:
                        episode_podcast["enclosures"][0]["length"] = length

            article_image = content_parser.find("h1")
            if article_image and article_image.find("img"):
                episode_art = article_image.img.attrs["src"].split("?")[0]
                if episode_art.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    episode_podcast["image"]["href"] = episode_art

            entry_content = content_parser.find(class_="entry-content")
            if entry_content is not None:
                first_div = entry_content.find("div")
                if first_div:
                    first_div.decompose()
                first_span = entry_content.find("span")
                if first_span:
                    first_span.decompose()
                episode_podcast["description"] = (
                    f"{entry_content}{description_suffix}"
                )

            rss_podcast.entries.insert(0, episode_podcast)
            logger.debug("Stored processed episode: %s", title)
    except Exception as exc:
        logger.exception("Error processing episode %s: %s", title, exc)


# Function to process each task
async def process_feed(task_config: dict[str, Any], group: dict[str, Any]) -> None:
    """Parse one feed, process new episodes, render the RSS XML, and write it to disk."""
    feed = task_config.get("feed")
    image = task_config.get("image")
    output = task_config.get("output")
    exclude = task_config.get("exclude")
    pub_url = task_config.get("pub_url")

    try:
        logger.info("Processing feed: %s", feed)
        rss_articles = feedparser.parse(feed, agent=ua.random)
        rss_podcast = feedparser.parse(pub_url)
        parsed_guids = [entry["guid"] for entry in rss_podcast["entries"] if "guid" in entry]
        if len(parsed_guids) == 0:
            rss_podcast = copy.deepcopy(rss_articles)

        async with aiohttp.ClientSession() as session:
            tasks = [
                process_episode(episode, session, rss_podcast)
                for episode in rss_articles.entries
                if needed_episode(episode, exclude) and episode.get("guid") not in parsed_guids
            ]
            if tasks:
                logger.debug("Starting %s episode tasks for %s", len(tasks), feed)
                await asyncio.gather(*tasks)
            else:
                logger.info("No new episodes to process for %s", feed)

            template_j2 = Template(template)
            try:
                podcast_xml = template_j2.render(rss=rss_podcast, pic=image, group=group)
            except Exception as exc:
                logger.exception("Error while templating feed %s: %s", feed, exc)
                return
            try:
                with open(output, "w") as f:
                    f.write(podcast_xml)
                logger.info("Wrote RSS output for %s to %s", feed, output)
            except Exception as exc:
                logger.exception("Error writing to file for %s: %s", feed, exc)
    except Exception as exc:
        logger.exception("Unexpected failure while processing feed %s: %s", feed, exc)


def thread(feed: dict[str, Any], group: dict[str, Any]) -> None:
    """Run a single feed job inside an asyncio event loop in a worker thread."""
    try:
        logger.debug("Starting thread for feed: %s", feed.get("feed"))
        asyncio.run(process_feed(feed, group))
    except Exception as exc:
        logger.exception("Thread failed for feed %s: %s", feed.get("feed"), exc)


def generate_page(config: dict[str, Any]) -> None:
    """Render the webpage index from the configured groups and feeds."""
    web_filename = config.get("web_filename")
    logger.info("Generating web page: %s", web_filename)
    template_j2 = Template(web_template)
    try:
        web = template_j2.render(config=config)
    except Exception as exc:
        logger.exception("Error while templating web page: %s", exc)
        return
    try:
        with open(web_filename, "w") as f:
            f.write(web)
        logger.info("Wrote web page to %s", web_filename)
    except Exception as exc:
        logger.exception("Error writing web page to %s: %s", web_filename, exc)


# Load configuration from YAML file
def load_config(yaml_path: str) -> dict[str, Any]:
    """Load and return the YAML configuration from the given path."""
    try:
        with open(yaml_path, "r") as file:
            logger.info("Loaded config file: %s", yaml_path)
            return yaml.safe_load(file)
    except Exception as exc:
        logger.exception("Error loading config file %s: %s", yaml_path, exc)
        sys.exit(1)


# Parse command-line arguments
def parse_args() -> argparse.Namespace:
    """Parse the command-line arguments for the config file path."""
    parser = argparse.ArgumentParser(
        description="Process YAML configuration in parallel."
    )
    parser.add_argument("config", type=str, help="Path to the YAML configuration file")
    return parser.parse_args()


# Main function
def main() -> None:
    """Entry point: load config, dispatch feed jobs, and generate the index page."""
    args = parse_args()
    config = load_config(args.config)
    configure_logging(config.get("logging_level", config.get("log_level", "INFO")))

    try:
        groups = config.get("groups", [])
        logger.info("Dispatching %s group/feed tasks", sum(len(group.get("feeds", [])) for group in groups))
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(thread, feed, group)
                for group in groups
                for feed in group.get("feeds", [])
            ]
            for future in futures:
                try:
                    future.result()
                except Exception as exc:
                    logger.exception("A feed task failed: %s", exc)
    except Exception as exc:
        logger.exception("Main processing failed: %s", exc)
        raise

    generate_page(config)


if __name__ == "__main__":
    main()
