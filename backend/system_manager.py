import os
import sys
from dotenv import load_dotenv
load_dotenv()
import pika
import json
import logging
import subprocess

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SYSTEM MANAGER] - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
QUEUE_NAME = 'system_commands'

def process_command(ch, method, properties, body):
    try:
        payload = json.loads(body)
        task = payload.get('task')
        
        logging.info(f"Received manual trigger: {task}")
        
        # Determine which scraper to run
        if task == 'sync_fii':
            logging.info("Executing FII/DII scrapers...")
            # We can run both the specific participant scraper and the flows scraper
            subprocess.run([sys.executable, "nse_flows_scrapper.py"], check=False)
            subprocess.run([sys.executable, "nse_participant_scraper.py"], check=False)
            logging.info("✅ FII/DII scrapers completed.")
            
        elif task == 'sync_nsdl':
            logging.info("Executing NSDL Tradewise and Sector scrapers...")
            subprocess.run([sys.executable, "nsdl_tradewise_scraper.py"], check=False)
            subprocess.run([sys.executable, "nsdl_sector_scraper.py"], check=False)
            logging.info("✅ NSDL Scrapers completed.")
            
        elif task == 'seed_db':
            logging.info("Executing script to seed DB (Historical Run)...")
            subprocess.run([sys.executable, "seed_historical.py"], check=False)
            logging.info("✅ Seed action called.")

        elif task == 'sync_yfinance':
            logging.info("Executing yFinance data ingestion...")
            subprocess.run([sys.executable, "yfinance_producer.py"], check=False)
            logging.info("✅ yFinance ingestion completed.")
            
        else:
            logging.warning(f"Unknown task received: {task}")
            
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logging.error(f"Error processing command: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_listening():
    credentials = pika.PlainCredentials(os.getenv('RABBITMQ_USER', 'admin'), os.getenv('RABBITMQ_PASS', 'supersecretpassword'))
    connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials))
    channel = connection.channel()

    # Make sure queue exists
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    
    # We only process one command at a time
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_command)

    logging.info("🕹️ System Manager online. Listening for dashboard manual overrides...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logging.info("System Manager shutting down...")
        channel.stop_consuming()
        connection.close()

if __name__ == "__main__":
    start_listening()
