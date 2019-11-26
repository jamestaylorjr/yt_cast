import youtube_dl
from lxml import etree
import time
import requests
import sqlite3

#TODO: youtube api/rss feed to get video list
#example request for youtube rss feed: https://www.youtube.com/feeds/videos.xml?channel_id=UCsB0LwkHPWyjfZ-JwvtwEXw

class RSSreader:
    """
    Parse the youtube ATOM file for a given channel and check for any new uploads within a week.
    """
    def __init__(self, feedurl):
        self.feedurl = feedurl

    def update_check(self):
        feed = requests.get(self.feedurl).content
        namespaces = {'atom':'http://www.w3.org/2005/Atom'}

        tree = etree.fromstring(feed)
        #upload_dates = tree.xpath('//atom:entry/atom:published/text()', namespaces=namespaces)
        links = tree.xpath('//atom:entry/atom:link/@href', namespaces=namespaces)
        
        return links
        
        

class RSSgenerator:
    """
    Generate XML to update an RSS file with new podcast entries.
    
    """
    
    def __init__(self, xmlfile):
        self.xmlfile = xmlfile
        self.db = sqlite3.connect('processed.db')
        self.c = self.db.cursor()
        self.c.execute('''CREATE TABLE IF NOT EXISTS processed (link text, date text)''')
        self.db.commit()
    
    def download_and_transform(self, videourl):
        
        #Check if link has already been processed
        c = self.c
        c.execute('SELECT * FROM processed')
        processed_links = [x[0] for x in c.fetchall()]
        if videourl in processed_links:
            print('Already processed.')
            return 0

        ydl_opts = {
            'format':'bestaudio/best',
            'postprocessors': [{
                'key':'FFmpegExtractAudio',
                'preferredcodec':'mp3',
                'preferredquality':'192'
            }]
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(videourl)

        print(info['webpage_url'], info['upload_date'])
        c.execute("INSERT INTO processed VALUES (?,?)", [info['webpage_url'],info['upload_date']])
        self.db.commit()

        return info

    def update_RSS(self, titletext, linktext, audiofile):
        """
        Update RSS feed with new entries downloaded and transcoded to mp3.
        ---------

        All fields should be filled with values returned from `RSSgenerator.download_and_transform()`

        """
        
        xmlfile = self.xmlfile
        #Get the current RSS file
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(xmlfile ,parser)
        root = tree.getroot()
        channel = root.find('channel')
        
        #Generate the new element
        newItem = etree.Element('item')
        title = etree.SubElement(newItem,'title')
        title.text = titletext
        link = etree.SubElement(newItem,'link')
        link.text = linktext
        enc = etree.SubElement(newItem,'enclosure')
        enc.set('url', audiofile)
        enc.set('type','audio/mpeg')

        #Insert the element and overwrite the old RSS file
        channel.insert(3, newItem)
        tree.write(xmlfile, pretty_print=True, xml_declaration=True, encoding='UTF-8')
