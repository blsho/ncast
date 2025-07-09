#!/usr/bin/env python

import feedparser
import requests
from jinja2 import Template
import sys
from bs4 import BeautifulSoup

template = """<?xml version="1.0" encoding="{{ rss.encoding }}"?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/"
	xmlns:content="http://purl.org/rss/1.0/modules/content/"
	xmlns:atom="http://www.w3.org/2005/Atom" version="2.0"
	xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:anchor="https://anchor.fm/xmlns"
	xmlns:podcast="https://podcastindex.org/namespace/1.0">
    <channel>
        <title>{{ rss.feed.title | escape }}</title>
        <description>{{ rss.feed.description | escape}}</description>
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
        <itunes:explicit>No</itunes:explicit>
        <itunes:category text="News" />
        <itunes:image href="{{ pic }}"/>
        {%- for entry in rss.entries %}
        {%- if entry.enclosure %}
        <item>
            <title>{{ entry.title | replace("\n", "") | replace("\t", "") }}</title>
            <description><![CDATA[{{ entry.description }}]]></description>
            <guid isPermaLink="false">{{ entry.guid }}</guid>
            <dc:creator>{{ entry.author }}</dc:creator>
            <pubDate>{{ entry.published }}</pubDate>
            <enclosure url="{{ entry.enclosure }}" length="{{ entry.length }}" type="audio/mpeg" />
            <itunes:duration>{{ entry.duration }}</itunes:duration>
        </item>
        {%- endif %}
        {%- endfor %}
    </channel>
</rss>"""

d = feedparser.parse(sys.argv[1])
url_fqdn = "a-static.projektn.sk" if d.feed.link[8:]=="dennikn.sk" else "static.novydenik.com"

for item in d.entries[:10]:
    article = requests.get(item.link)
    content_parser = BeautifulSoup(article.content.decode(), 'html.parser')
    try:
        item.enclosure =  content_parser.audio.source.attrs['src']
        item.duration = content_parser.audio.attrs['data-duration']
        voice = requests.head(item.enclosure)
        if voice.status_code == 200:
            item.length = voice.headers['content-length']
    except AttributeError:
        continue

template_j2 = Template(template)
podcast_xml = template_j2.render(rss=d, pic=sys.argv[2])
print(f"{podcast_xml}")
