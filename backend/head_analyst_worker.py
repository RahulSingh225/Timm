import pika  # type: ignore
import json
import os
import pyttsx3  # type: ignore
import logging
from openai import OpenAI  # type: ignore
from dotenv import load_dotenv  # type: ignore

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [HEAD ANALYST] - %(message)s')

# Configuration
load_dotenv()
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "supersecretpassword")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "market_data_exchange")
QUEUE_NAME = 'head_analyst_queue'

# Load Environment Variables and Configure Local LLM (Ollama)
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
AI_MODEL = os.getenv("AI_MODEL", "llama3.2")

logging.info(f"Connecting to Local LLM at {OPENAI_API_BASE} using model {AI_MODEL}")

client = OpenAI(
    base_url=OPENAI_API_BASE,
    api_key=OPENAI_API_KEY
)

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
    Sends the structured JSON alert to the local LLM API
    to generate a fast, punchy trading brief.
    """
    symbol = alert_data.get('symbol', 'UNKNOWN')
    
    system_prompt = f"""
    You are a ruthless, highly experienced quantitative trading desk analyst. 
    You have just received a technical alert for the stock: {symbol}.
    
    Raw Alert Data:
    {json.dumps(alert_data, indent=2)}
    
    Your task:
    Provide a very brief, punchy, 3-sentence maximum script for the head trader.
    Do not use pleasantries. Do not explain what EMA or RSI is. 
    State the stock, state the technical setup, and state the logical next step or risk.
    Make it sound like a fast-paced prop desk update.
    """

    try:
        logging.info(f"🧠 Asking Local LLM to analyze setup for {symbol}...")
        
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are a fast-paced quantitative prop desk analyst."},
                {"role": "user", "content": system_prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logging.error(f"Failed to communicate with Local LLM API: {e}")
        return "System error: Unable to contact the Local Analysis server."

def process_alert(ch, method, properties, body):
    """
    Triggered when a Level 1 Agent publishes an alert.
    """
    try:
        alert_data = json.loads(body)
        symbol = alert_data.get('symbol')
        agent_source = alert_data.get('agent', 'Unknown')
        
        logging.info(f"🚨 ALERT RECEIVED from {agent_source} Agent for {symbol}")

        # Feed it to LLM
        brief = generate_market_brief(alert_data)
        
        # Print output
        print("\n" + "="*50)
        print(f"📊 TRADING DESK BRIEF: {symbol}")
        print("="*50)
        print(f"{brief}")
        print("="*50 + "\n")

        # Speak output
        speak_text(brief)

        # Republish the alert with the LLM brief attached so the frontend SSE can show it
        enriched_alert = {**alert_data, "summary": brief, "signal_type": "BULLISH" if any(kw in str(alert_data.get('signals', [])).upper() for kw in ['BULLISH', 'GOLDEN', 'BOUNCE', 'BUY']) else "BEARISH" if any(kw in str(alert_data.get('signals', [])).upper() for kw in ['BEARISH', 'DEATH', 'DROP', 'SELL']) else "NEUTRAL"}
        ch.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=f'alert.enriched.{symbol}',
            body=json.dumps(enriched_alert),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        logging.info(f"📤 Published enriched alert for {symbol} with LLM brief")

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