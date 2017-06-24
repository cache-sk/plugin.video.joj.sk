# -*- coding: UTF-8 -*-
# /*
# *      Copyright (C) 2013 Maros Ondrasek
# *
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with this program; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *
# */

import re
import urllib2
import cookielib
import random
import urlparse
from xml.etree.ElementTree import fromstring

import util
from provider import ContentProvider

BASE_URL = {"JOJ":  "http://joj.sk",
        "JOJ Plus": "http://plus.joj.sk",
        "WAU":      "http://wau.joj.sk"}

class JojContentProvider(ContentProvider):
    def __init__(self, username=None, password=None, filter=None):
        ContentProvider.__init__(self, 'joj.sk', 'http://www.joj.sk/', username, password, filter)
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.LWPCookieJar()))
        urllib2.install_opener(opener)
        self.debugging = True

    def debug(self, text):
        if self.debugging:
            print "[DEBUG][%s] %s" % (self.name, text)

    def capabilities(self):
        return ['categories', 'resolve', '!download']


    def _fix_url(self, url):
        if url.startswith('//'):
            url = 'http:'+ url
        return url

    def _list_article(self, data):
        url_and_title_match = re.search(r'<a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)"', data)
        if url_and_title_match is None:
            return None
        item = {}
        item['title'] = url_and_title_match.group('title')
        #print 'title = ', item['title']
        item['url'] = self._fix_url(url_and_title_match.group('url'))
        #print 'url = ', item['url']
        subtitle_match = re.search(r'<h4 class="subtitle">[^>]+>([^<]+)', data)
        if subtitle_match:
            item['subtitle'] = subtitle_match.group(1)
        img_match = re.search(r'<img src="([^"]+)"', data)
        if img_match:
            item['img'] = self._fix_url(img_match.group(1))
        return item

    def list_base(self, url):
        result = []
        self.info("list_base %s"% url)
        data = util.request(url)
        data = util.substr(data, '<section class="s s-container s-videozone s-archive s-tv-archive">', '<div class="s-footer-wrap">')
        for article_match in re.finditer('<article class="b-article article-md media-on">(.+?)</article>', data, re.DOTALL):
            article_dict = self._list_article(article_match.group(1))
            if article_dict is not None:
                item = self.dir_item()
                item.update(article_dict)
                item['url'] = item['url'] + "#s"
                result.append(item)
        return result

    def list_show(self, url, list_series=False, list_episodes=False):
        result = []
        self.info("list_show %s"%(url))
        data = util.request(url)
        if list_series:
            series_data = util.substr(data, r'<select name="season" data-ajax data-ajax-result-elements="headerPart,episodeListing">', '</select>')
            for serie_match in re.finditer(r'option\s(?:selected\s)?value="(?P<url>[^"]+)">(?P<title>[^<]+)<', series_data):
                item = self.dir_item()
                item['title'] = serie_match.group('title')
                item['url'] = self._fix_url(serie_match.group('url'))
                result.append(item)
        if list_episodes:
            episodes_data = util.substr(data, r'<section class="s s-container s-archive-serials">', "</section>")
            for article_match in re.finditer(r'<article class=".+?media-on">(.+?)</article>', episodes_data, re.DOTALL):
                article_dict = self._list_article(article_match.group(1))
                if article_dict is not None:
                    item = self.video_item()
                    item.update(article_dict)
                    item['title'] += ' ' + item.get('subtitle','')
                    result.append(item)

            title_to_key = {
             'Dátum':'date',
             'Názov epizódy':'title',
             'Sledovanosť':'seen',
             'Séria':'season',
             'Epizóda':'episode'}
            headers_match = re.search('<div class="i head e-video-categories">(.+?)</div>', episodes_data, re.DOTALL)
            if headers_match is not None:
                headers = []
                for span_match in re.finditer('<span[^>]*>([^<]+)</span>', headers_match.group(1)):
                    key = title_to_key.get(span_match.group(1))
                    if key is None:
                        print "undefined key", span_match.group(1)
                        headers.append("")
                    else:
                        headers.append(key)
                archive_list_pattern  = r'<a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)[^>]+>\s+'
                for key in headers:
                    if key in ("", "title"):
                        archive_list_pattern += r'^.+?$\s+'
                    else:
                        archive_list_pattern += r'<span>(?P<%s>[^<]*)</span>\s+'%key
                for archive_list_match in re.finditer(archive_list_pattern, episodes_data, re.MULTILINE):
                    item = self.video_item()
                    groupdict = archive_list_match.groupdict()
                    if 'season' in groupdict and 'episode' in groupdict:
                        # joj sometimes don't provide season/episode numbers
                        # for latest episodes, so mark them as 0.
                        try:
                            season = int(archive_list_match.group('season'))
                        except Exception:
                            season = 0
                        try:
                            episode = int(archive_list_match.group('episode'))
                        except Exception:
                            episode = 0
                        item['title'] = "(S%02d E%02d) - %s"%(season, episode,
                                archive_list_match.group('title'))
                    else:
                        item['title'] = "(%s) - %s"%(archive_list_match.group('date'),
                                archive_list_match.group('title'))
                    item['url'] = self._fix_url(archive_list_match.group('url'))
                    result.append(item)

            pagination_data = util.substr(data, '<nav>','</nav>')
            next_match = re.search(r'a href="(?P<url>[^"]+)" aria-label="Ďalej"', pagination_data, re.DOTALL)
            if next_match:
                item = self.dir_item()
                item['type'] = 'next'
                item['url'] = self._fix_url(next_match.group(1))
                result.append(item)
        return result

    def list(self, url):
        self.info("list %s" % url)
        url_parsed = urlparse.urlparse(url)
        if not url_parsed.path:
            if url not in BASE_URL.values():
                print "not joj.sk url!"
                return []
            return self.subcategories(url)
        if url_parsed.fragment == "s":
            result = self.list_show(url, list_series=True)
            if not result:
                result = self.list_show(url, list_episodes=True)
            return result
        return self.list_show(url, list_episodes=True)

    def categories(self):
        return[
            self.dir_item("JOJ", BASE_URL["JOJ"]),
            self.dir_item("JOJ Plus", BASE_URL["JOJ Plus"]),
            self.dir_item("WAU", BASE_URL["WAU"])]

    def subcategories(self, base_url):
        live = self.video_item()
        live['title'] = '[B]Live[/B]'
        live['url'] = base_url + '/live.html'
        return [live] + self.list_base(base_url + '/archiv-filter')

    def resolve(self, item, captcha_cb=None, select_cb=None):
        result = []
        item = item.copy()
        url = item['url']
        if url.endswith('live.html'):
            channel = urlparse.urlparse(url).netloc.split('.')[0]
            for original, replacement in {'joj': 'joj', 'plus': 'jojplus'}.items():
                if channel == original:
                    channel = replacement
                    break
            for quality, resolution in {'lq': '180p', 'mq': '360p', 'hq': '540p'}.items():
                item = self.video_item()
                item['quality'] = resolution
                item['url'] = 'http://http-stream.joj.sk/joj/' + channel + '/index-' + quality + '.m3u8'
                result.append(item)
        else:
            data = util.request(url)
            data = util.substr(data, '<div class="s-archive">','<div class="s s-container s-archive">')
            iframe_url = re.search('<iframe src="([^"]+)"', data).group(1)
            #print 'iframe_url = ', iframe_url
            pageid = urlparse.parse_qs(iframe_url)['context'][0]
            #print 'pageid = ', pageid
            clipid = urlparse.urlparse(iframe_url).path.split('/')[-1]
            #print 'clipid = ', clipid
            videophp_url = "http://media.joj.sk/services/Video.php?pageId=%s&clip=%s"% (pageid, clipid.replace('-','%2D'))
            #print 'videophp_url = ', videophp_url
            playlist = fromstring(util.request(videophp_url))
            balanceurl = 'http://media.joj.sk/balance.xml?nc=%d' % random.randint(1000, 9999)
            balance = fromstring(util.request(balanceurl))
            for video in playlist.find('files').findall('file'):
                item = self.video_item()
                item['img'] = playlist.attrib.get('large_image')
                item['length'] = playlist.attrib.get('duration')
                item['quality'] = video.attrib.get('label')
                item['url'] = 'https://nn.geo.joj.sk/' + video.attrib.get('path').replace('dat/', 'storage/')
                result.append(item)
            result.reverse()
        if select_cb:
            return select_cb(result)
        return result

