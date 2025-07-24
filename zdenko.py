#!/usr/bin/env python3

import feedparser
import requests
from jinja2 import Template
import sys
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

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
d = feedparser.parse(sys.argv[1], agent=ua.random)

for item in d.entries[:10]:
    article = requests.get(item.link, headers={"User-Agent": ua.random})
    content_parser = BeautifulSoup(article.content.decode(), "html.parser")
    try:
        item.enclosure = content_parser.audio.source.attrs["src"]
        item.duration = content_parser.audio.attrs["data-duration"]
        item.content = item.description
        voice = requests.head(item.enclosure, headers={"User-Agent": ua.random})
        if voice.status_code == 200:
            item.length = voice.headers["content-length"]
        episode_art = content_parser.find("h1").img.attrs["src"].split("?")[0]
        if episode_art.endswith((".png", ".jpg")):
            item.art = episode_art
        content_parser.find(class_="entry-content").find("div").decompose()
        content_parser.find(class_="entry-content").find("span").decompose()
        item.content = content_parser.find(class_="entry-content")
    except Exception:
        continue

template_j2 = Template(template)
podcast_xml = template_j2.render(rss=d, pic=sys.argv[2])
print(f"{podcast_xml}")
