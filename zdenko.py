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
        <description>{{ rss.feed.description | escape}}</description>
        <itunes:summary>{{ rss.feed.description | escape}}</itunes:summary>
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
        <podcast:funding url="https://predplatne.dennikn.sk/">Ak chces ZdeNka, tak nebuť k*k*t a kúp si Nko.</podcast:funding>
        {%- for entry in rss.entries %}
        {%- if entry.enclosure %}
        <item>
            <title>{{ entry.title | replace("\n", "") | replace("\t", "") }}</title>
            <description><![CDATA[{{ entry.content }} <br><p>Viac na <a href="{{ entry.link }}">{{ entry.link }}</a></p>]]></description>
            <guid isPermaLink="false">{{ entry.guid }}</guid>
            <dc:creator>{{ entry.author }}</dc:creator>
            <pubDate>{{ entry.published }}</pubDate>
            <enclosure url="{{ entry.enclosure }}" length="{{ entry.length }}" type="audio/mpeg" />
            <itunes:duration>{{ entry.duration }}</itunes:duration>
            <itunes:explicit>false</itunes:explicit>
            {%- if entry.art %}
            <itunes:image href="{{ entry.art }}"/>
            {%- endif %}
        </item>
        {%- endif %}
        {%- endfor %}
    </channel>
</rss>"""

ua = UserAgent(os=["Windows", "Android", "iOS"], min_percentage=0.05)

async def process_episode(episode, session):
    try:
        async with session.get(episode.link, headers={"User-Agent": ua.random}) as article:
            content_parser = BeautifulSoup(await article.text(), "html.parser")
            episode.enclosure = content_parser.audio.source.attrs["src"]
            episode.duration = content_parser.audio.attrs["data-duration"]
            episode.content = episode.description
            print(f"enclosure: {episode.enclosure}")
            async with session.head(episode.enclosure, headers={"User-Agent": ua.random}) as voice:
                if voice.status == 200:
                    episode.length = voice.headers["content-length"]
            episode_art = content_parser.find("h1").img.attrs["src"].split("?")[0]
            if episode_art.endswith((".png", ".jpg")):
                episode.art = episode_art
            content_parser.find(class_="entry-content").find("div").decompose()
            content_parser.find(class_="entry-content").find("span").decompose()
            episode.content = content_parser.find(class_="entry-content")
    except Exception:
        pass

# Function to process each task
async def process_feed(task_config):
    feed = task_config.get("feed")
    image = task_config.get("image")
    output = task_config.get("output")
    d = feedparser.parse(feed, agent=ua.random)

    async with aiohttp.ClientSession() as session:
        tasks = [process_episode(episode, session)for episode in d.entries]
        await asyncio.gather(*tasks)
        template_j2 = Template(template)
        podcast_xml = template_j2.render(rss=d, pic=image)
        try:
            with open(output, "w") as f:
                f.write(podcast_xml)
        except Exception as e:
            print(f"Error writing to file for {feed}: {e}")

def thread(cfg):
    asyncio.run(process_feed(cfg))

# Load configuration from YAML file
def load_config(yaml_path):
    try:
        with open(yaml_path, "r") as file:
            return yaml.safe_load(file)
    except Exception as e:
        print(f"Error loading config file: {e}")
        sys.exit(1)


# Parse command-line arguments
def parse_args():
    parser = argparse.ArgumentParser(
        description="Process YAML configuration in parallel."
    )
    parser.add_argument("config", type=str, help="Path to the YAML configuration file")
    return parser.parse_args()

# Main function
def main():
    args = parse_args()
    config = load_config(args.config)

    if not isinstance(config, list):
        print("Configuration must be a list of dictionaries.")
        sys.exit(1)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        [executor.submit(thread, cfg) for cfg in config]


if __name__ == "__main__":
    main()
