import youtube_dl
from lxml import etree
import time
import requests
import sqlite3
import http.server
import socketserver
from threading import Thread
from concurrent.futures import Future
from random import randint

#TODO: youtube api/rss feed to get video list
#example request for youtube rss feed: https://www.youtube.com/feeds/videos.xml?channel_id=UCsB0LwkHPWyjfZ-JwvtwEXw
def call_with_future(fn, future, args, kwargs):
    try:
        result = fn(*args, **kwargs)
        future.set_result(result)
    except Exception as exc:
        future.set_exception(exc)

def threaded(fn):
    def wrapper(*args, **kwargs):
        future = Future()
        Thread(target=call_with_future, args=(fn, future, args, kwargs)).start()
        return future
    return wrapper

@threaded    
def start_server():
    PORT = 9000
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory='serve',**kwargs)
                
    with socketserver.TCPServer(('',PORT), Handler) as httpd:
        print(f'Serving at port {PORT}')
        httpd.serve_forever()

class RSSreader:
    """
    Parse the youtube ATOM file for a given channel and check for any new uploads within a week.
    """
    def __init__(self, feedurl):
        self.feedurl = feedurl
        
        
    @threaded
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
        db = sqlite3.connect('processed.db')
        c = db.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS processed (link text, date text)''')
        db.commit()
    
    @threaded
    def download_and_transform(self, videourl):
        
        #Check if link has already been processed
        db = sqlite3.connect('processed.db')
        c = db.cursor()
        c.execute('SELECT * FROM processed')
        processed_links = [x[0] for x in c.fetchall()]
        if videourl in processed_links:
            print('Already processed.')
            return 0

        ydl_opts = {
            'format':'bestaudio/best',
            'outtmpl':'serve/storage/%(title)s.%(ext)s',
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
        db.commit()

        return info

    @threaded
    def update_RSS(self, titletext, desctext, pubtext, linktext, duration, audiofile):
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
        desc = etree.SubElement(newItem, 'description')
        desc.text = desctext
        pub = etree.SubElement(newItem, 'pubDate')
        pub.text = pubtext
        link = etree.SubElement(newItem,'link')
        link.text = linktext
        guid = etree.SubElement(newItem, 'guid')
        guid.set('isPermaLink','false')
        guid.text = str(randint(1,10000))
        
        enc = etree.SubElement(newItem,'enclosure')
        enc.set('url', audiofile)
        enc.set('length', str(duration))
        enc.set('type','audio/mpeg')
    
        #Insert the element and overwrite the old RSS file
        channel.insert(3, newItem)
        tree.write(xmlfile, pretty_print=True, xml_declaration=True, encoding='UTF-8')
        print('xml updated')



if __name__ == "__main__":
    with open('channels.txt','r') as file:
        channels = file.readlines()

    server = start_server()
    SERVER_IP = 'localhost:9000'

    while True:
        for channel in channels:
            reader = RSSreader(channel.strip())
            values = reader.update_check()
            values = values.result()
            writer = RSSgenerator(f'serve/feed.xml')
            for url in values:
                info = writer.download_and_transform(url)
                info = info.result()
                if info != 0:
                    writer.update_RSS(info['title'],info['description'],info['upload_date'],info['webpage_url'],info['duration'],f"{SERVER_IP}/storage/{info['title']}.mp3")
        time.sleep(600)