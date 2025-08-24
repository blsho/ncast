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


def needed_episode(episode, exclude):
    if exclude:
        categories = set(map(lambda tag: tag["term"], episode.tags))
        if set(exclude).intersection(categories):
            return False
    return True


async def process_episode(episode, session, rss_podcast):
    episode_podcast = {}
    try:
        async with session.get(
            episode.link, headers={"User-Agent": ua.random}
        ) as article:
            content_parser = BeautifulSoup(await article.text(), "html.parser")
            episode_podcast["title"] = episode.title
            episode_podcast["author"] = episode.author
            episode_podcast["published"] = episode.published
            episode_podcast["guid"] = episode.guid
            episode_podcast["link"] = episode.link
            episode_podcast["enclosures"] = [{}]
            episode_podcast["enclosures"][0]["href"] = (
                content_parser.audio.source.attrs["src"]
            )
            episode_podcast["itunes_duration"] = content_parser.audio.attrs[
                "data-duration"
            ]

            description_sufix = (
                f'<br><p>Viac na <a href="{ episode.link }">{ episode.link }</a></p>'
            )
            episode_podcast["description"] = f"{episode.description}{description_sufix}"
            async with session.head(
                episode_podcast["enclosures"][0]["href"],
                headers={"User-Agent": ua.random},
            ) as voice:
                if voice.status == 200:
                    episode_podcast["enclosures"][0]["length"] = voice.headers[
                        "content-length"
                    ]
            episode_art = content_parser.find("h1").img.attrs["src"].split("?")[0]
            if episode_art.endswith((".png", ".jpg")):
                episode_podcast["image"]["href"] = episode_art
            content_parser.find(class_="entry-content").find("div").decompose()
            content_parser.find(class_="entry-content").find("span").decompose()
            episode_podcast["description"] = (
                f"{content_parser.find(class_="entry-content")}{description_sufix}"
            )
    except Exception:
        pass
    rss_podcast.entries.insert(0, episode_podcast)


# Function to process each task
async def process_feed(task_config, group):
    feed = task_config.get("feed")
    image = task_config.get("image")
    output = task_config.get("output")
    exclude = task_config.get("exclude")
    pub_url = task_config.get("pub_url")
    rss_articles = feedparser.parse(feed, agent=ua.random)
    rss_podcast = feedparser.parse(pub_url)
    parsed_guids = [entry["guid"] for entry in rss_podcast["entries"]]
    if len(parsed_guids) == 0:
        rss_podcast = copy.deepcopy(rss_articles)

    async with aiohttp.ClientSession() as session:
        tasks = [
            process_episode(episode, session, rss_podcast)
            for episode in rss_articles.entries
            if needed_episode(episode, exclude) and episode["guid"] not in parsed_guids
        ]
        await asyncio.gather(*tasks)
        template_j2 = Template(template)
        try:
            podcast_xml = template_j2.render(rss=rss_podcast, pic=image, group=group)
        except Exception as e:
            print(f"Error while templating: {e}")
        try:
            with open(output, "w") as f:
                f.write(podcast_xml)
        except Exception as e:
            print(f"Error writing to file for {feed}: {e}")


def thread(feed, group):
    asyncio.run(process_feed(feed, group))


def generate_page(config):
    web_filename = config.get("web_filename")
    template_j2 = Template(web_template)
    try:
        web = template_j2.render(config=config)
    except Exception as e:
        print(f"Error while templating: {e}")
    try:
        with open(web_filename, "w") as f:
            f.write(web)
    except Exception as e:
        print(f"Error writing to file for {web_filename}: {e}")


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

    with concurrent.futures.ThreadPoolExecutor() as executor:
        [
            executor.submit(thread, feed, group)
            for group in config["groups"]
            for feed in group["feeds"]
        ]

    generate_page(config)


if __name__ == "__main__":
    main()
