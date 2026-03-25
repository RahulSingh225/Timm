import feedparser
import pika
import json
import logging
from datetime import datetime
from time import mktime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NEWS AGENT] - %(message)s')

RABBITMQ_HOST = 'localhost'
EXCHANGE_NAME = 'market_data_exchange'

# Top Indian Financial Feeds
RSS_FEEDS = {
    "Moneycontrol_Markets": "https://www.moneycontrol.com/rss/marketreports.xml",
    "Mint_Markets": "https://www.livemint.com/rss/markets",
    "ET_Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
}

def fetch_and_publish_news():
    credentials = pika.PlainCredentials('admin', 'supersecretpassword')
    connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials))
    channel = connection.channel()
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)

    for source, url in RSS_FEEDS.items():
        logging.info(f"Scraping {source}...")
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:5]: # Grab the top 5 latest news items per source
            # Convert RSS time to ISO format
            pub_date = datetime.now()
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime.fromtimestamp(mktime(entry.published_parsed))

            payload = {
                "title": entry.title,
                "content": entry.summary if hasattr(entry, 'summary') else "",
                "source": source,
                "url": entry.link,
                "publishedAt": pub_date.isoformat()
            }

            channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key="market.news.macro",
                body=json.dumps(payload),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logging.info(f"Published News: {entry.title[:50]}...")

    connection.close()

if __name__ == "__main__":
    fetch_and_publish_news()