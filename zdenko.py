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

for item in d.entries:
    url_prefix = f"https://{url_fqdn}/{item.published_parsed[0]}/{item.published_parsed[1]:02}/neural-audio-elevenlabs-{item.guid.split('=')[-1]}-"
    url = ""
    for i in range(9, 0, -1):
        url_voice = f"{url_prefix}{i}.mp3"
        response = requests.head(url_voice)
        if response.status_code == 200:
            url = url_voice
            length = response.headers['content-length']
            break
    if url:
        item.enclosure =  url
        item.length = length
        response = requests.get(item.link)
        content_parser = BeautifulSoup(response.content.decode(), 'html.parser')
        item.duration = content_parser.audio.attrs['data-duration']

template_j2 = Template(template)
podcast_xml = template_j2.render(rss=d, pic=sys.argv[2])
print(f"{podcast_xml}")
