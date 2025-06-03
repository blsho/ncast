import feedparser
import requests
from jinja2 import Template

template = """<?xml version="1.0" encoding="{{ encoding }}"?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/"
	xmlns:content="http://purl.org/rss/1.0/modules/content/"
	xmlns:atom="http://www.w3.org/2005/Atom" version="2.0"
	xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:anchor="https://anchor.fm/xmlns"
	xmlns:podcast="https://podcastindex.org/namespace/1.0">
    <channel>
        <title>{{ feed.title | escape }}</title>
        <description>{{ feed.description | escape}}</description>
        {%- for link in feed.links %}
        <link>{{ link.href }}</link>
        {%- endfor %}
        <image>
            <url>https://img.projektn.sk/wp-static/2015/05/dennikn-logo.png</url>
            <title>Dennik N</title>
            <link>https://dennikn.sk/</link>
        </image>
        <lastBuildDate>{{ feed.updated }}</lastBuildDate>
        <language>{{ feed.language }}</language>
        <itunes:author>dennikn.sk</itunes:author>
        <itunes:owner>
            <itunes:name>dennikn.sk</itunes:name>
        </itunes:owner>
        <itunes:explicit>No</itunes:explicit>
        <itunes:category text="News" />
        <itunes:image href="https://img.projektn.sk/wp-static/2015/05/dennikn-logo.png"/>
        {%- for entry in entries %}
        {%- if entry.enclosure %}
        <item>
            <title>{{ entry.title | replace("\n", "") | replace("\t", "") }}</title>
            <description><![CDATA[{{ entry.description }}]]></description>
            <guid isPermaLink="false">{{ entry.guid }}</guid>
            <dc:creator>{{ entry.author }}</dc:creator>
            <pubDate>{{ entry.published }}</pubDate>
            <enclosure url="{{ entry.enclosure }}" type="audio/mpeg" />
        </item>
        {%- endif %}
        {%- endfor %}
    </channel>
</rss>"""

d = feedparser.parse("https://dennikn.sk/feed")

for item in d.entries:
    url_prefix = f"https://a-static.projektn.sk/{item.published_parsed[0]}/{item.published_parsed[1]:02}/neural-audio-elevenlabs-{item.guid[22:]}-"
    url = ""
    for i in range(9, 1, -1):
        url_voice = f"{url_prefix}{i}.mp3"
        response = requests.head(url_voice)
        if response.status_code == 200:
            url = url_voice
            break
    if url:
        item.enclosure =  url

template_j2 = Template(template)
podcast_xml = template_j2.render(d)
print(f"{podcast_xml}")
