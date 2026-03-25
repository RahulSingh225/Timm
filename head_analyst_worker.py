import pika
import json
import os
import pyttsx3
import logging
import google.generativeai as genai
from dotenv import load_dotenv

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [HEAD ANALYST] - %(message)s')

# Configuration
load_dotenv()
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
RABBITMQ_USER = os.getenv("RABBITMQ_USER")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE")
QUEUE_NAME = os.getenv("RABBITMQ_SWING_QUEUE")

# Load Environment Variables and Configure Gemini

GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")

if not GOOGLE_API_KEY:
    logging.error("GEMINI_API_KEY missing from .env file!")
    exit(1)

genai.configure(api_key=GOOGLE_API_KEY)

# Use the fast, cost-effective Flash model for rapid analysis
# You can upgrade to 'gemini-1.5-pro' if you need deep, complex reasoning later
model = genai.GenerativeModel('gemini-2.5-flash')

# Initialize Offline Text-to-Speech Engine
try:
    tts_engine = pyttsx3.init()
    tts_engine.setProperty('rate', 170) 
except Exception as e:
    logging.warning(f"TTS Engine failed to initialize: {e}. Voice output will be disabled.")
    tts_engine = None

def speak_text(text):
    """Speaks the generated summary aloud."""
    if tts_engine:
        logging.info("🎙️ Broadcasting audio...")
        tts_engine.say(text)
        tts_engine.runAndWait()

def generate_market_brief(alert_data):
    """
    Sends the structured JSON alert to the Gemini API
    to generate a fast, punchy trading brief.
    """
    symbol = alert_data.get('symbol', 'UNKNOWN')
    
    system_prompt = f"""
    You are a ruthless, highly experienced quantitative trading desk analyst. 
    You have just received a technical alert for the stock: {symbol}.
    
    Raw Alert Data:
    {json.dumps(alert_data, indent=2)}
    
    Your task:
    Provide a very brief, punchy, 3-sentence maximum audio script for the head trader.
    Do not use pleasantries. Do not explain what EMA or RSI is. 
    State the stock, state the technical setup, and state the logical next step or risk.
    Make it sound like a fast-paced prop desk update.
    """

    try:
        logging.info(f"🧠 Asking Gemini to analyze setup for {symbol}...")
        
        # Call the Gemini API
        response = model.generate_content(system_prompt)
        
        return response.text.strip()
        
    except Exception as e:
        logging.error(f"Failed to communicate with Gemini API: {e}")
        return "System error: Unable to contact the Gemini analysis server."

def process_alert(ch, method, properties, body):
    """
    Triggered when a Level 1 Agent publishes an alert.
    """
    try:
        alert_data = json.loads(body)
        symbol = alert_data.get('symbol')
        agent_source = alert_data.get('agent', 'Unknown')
        
        logging.info(f"🚨 ALERT RECEIVED from {agent_source} Agent for {symbol}")

        # Feed it to Gemini
        brief = generate_market_brief(alert_data)
        
        # Print output
        print("\n" + "="*50)
        print(f"📊 TRADING DESK BRIEF: {symbol}")
        print("="*50)
        print(f"{brief}")
        print("="*50 + "\n")

        # Speak output
        speak_text(brief)

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logging.error(f"Error processing alert: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_head_analyst():
    """Connects to RabbitMQ and listens for all alerts."""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='alert.#')
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_alert)

    logging.info("🧠 Head Analyst (Powered by Gemini) is online and listening for alerts...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logging.info("Head Analyst shutting down...")
        channel.stop_consuming()
        connection.close()

if __name__ == "__main__":
    start_head_analyst()