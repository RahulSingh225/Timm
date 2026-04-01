"""
Head Analyst Worker v2.0

The strategic brain of the platform. Receives alerts from Level 1 agents
and produces context-rich LLM-powered analysis by:
1. Collecting all recent alerts (batch mode)
2. Injecting global cues, FII/DII flow data, sector rotation signals
3. Asking the LLM to produce structured Top 3 Trade Ideas
4. Falls back gracefully if LLM is offline
"""

import pika
import json
import os
import time
import logging
import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [HEAD ANALYST] - %(message)s')

# RabbitMQ Config
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "supersecretpassword")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "market_data_exchange")
QUEUE_NAME = 'head_analyst_queue'
DB_URL = os.getenv("DATABASE_URL")

# LLM Config
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
AI_MODEL = os.getenv("AI_MODEL", "llama3.2")

client = OpenAI(base_url=OPENAI_API_BASE, api_key=OPENAI_API_KEY)

# TTS (optional)
try:
    import pyttsx3
    tts_engine = pyttsx3.init()
    tts_engine.setProperty('rate', 170)
except Exception:
    tts_engine = None


def _log_run(status, duration_ms, symbol=None, error=None, llm_model=None, prompt_tokens=None, completion_tokens=None, prompt_preview=None, response_preview=None):
    """Log run to agent_runs table."""
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO agent_runs 
            (agent_name, run_status, duration_ms, symbol_processed, error_message, finished_at,
             llm_model, llm_prompt_tokens, llm_completion_tokens, llm_prompt_preview, llm_response_preview)
            VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s)
        """, ('head_analyst', status, duration_ms, symbol, error,
              llm_model, prompt_tokens, completion_tokens,
              prompt_preview[:500] if prompt_preview else None,
              response_preview[:500] if response_preview else None))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.warning(f"Failed to log run: {e}")


def _fetch_global_context():
    """Fetch latest global cues and FII/DII data from DB for LLM context injection."""
    context = {"global_cues": None, "fii_dii": None, "sector_leaders": []}

    if not DB_URL:
        return context

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        # Global cues
        cur.execute("""
            SELECT overall_bias, vix_value, vix_change_pct, spy_change_pct, 
                   gift_nifty, usd_inr, captured_at
            FROM global_cues ORDER BY captured_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            context["global_cues"] = {
                "bias": row[0] or "NEUTRAL",
                "vix": row[1],
                "vix_change": row[2],
                "spy_pct": row[3],
                "gift_nifty": row[4],
                "usd_inr": row[5],
                "captured_at": str(row[6]) if row[6] else None,
            }

        # Latest FII/DII flows
        cur.execute("""
            SELECT trade_date, fii_net_cash, dii_net_cash, pcr, sentiment_score
            FROM fii_dii_flows ORDER BY trade_date DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            context["fii_dii"] = {
                "date": str(row[0]),
                "fii_net": row[1],
                "dii_net": row[2],
                "pcr": row[3],
                "sentiment": row[4],
            }

        # Top 3 sectors by recent FII inflow
        cur.execute("""
            SELECT sector_name, net_investment_cr
            FROM sector_flows
            WHERE trade_date = (SELECT MAX(trade_date) FROM sector_flows)
            ORDER BY net_investment_cr DESC LIMIT 3
        """)
        context["sector_leaders"] = [
            {"sector": r[0], "net_cr": r[1]} for r in cur.fetchall()
        ]

        cur.close()
        conn.close()
    except Exception as e:
        logging.warning(f"Failed to fetch global context: {e}")

    return context


def _build_context_prompt(alert_data: dict, global_ctx: dict) -> str:
    """Build a rich, context-injected prompt for the LLM."""
    symbol = alert_data.get('symbol', 'UNKNOWN')
    signals = alert_data.get('signals', [])
    confidence = alert_data.get('confidence', 'N/A')
    trade_idea = alert_data.get('trade_idea', {})
    trend = alert_data.get('trend', {})

    # Global context section
    global_section = ""
    gc = global_ctx.get('global_cues')
    if gc:
        global_section = f"""
GLOBAL MARKET CONDITIONS:
- Market Bias: {gc['bias']}
- VIX: {gc['vix']} ({gc['vix_change']:+.1f}% change)
- US Markets (SPY): {gc['spy_pct']:+.2f}%
- GIFT Nifty: {gc['gift_nifty']}
- USD/INR: {gc['usd_inr']}"""

    fii_section = ""
    fii = global_ctx.get('fii_dii')
    if fii:
        fii_dir = "BOUGHT" if fii['fii_net'] and fii['fii_net'] > 0 else "SOLD"
        fii_section = f"""
FII/DII FLOWS (Latest):
- FII Net: ₹{fii['fii_net']} Cr ({fii_dir})
- DII Net: ₹{fii['dii_net']} Cr
- PCR: {fii['pcr']}"""

    sector_section = ""
    sectors = global_ctx.get('sector_leaders', [])
    if sectors:
        sector_list = ", ".join([f"{s['sector']} (₹{s['net_cr']}Cr)" for s in sectors])
        sector_section = f"\nTOP SECTORS BY FII FLOW: {sector_list}"

    # Trade idea section
    trade_section = ""
    if trade_idea and trade_idea.get('entry'):
        trade_section = f"""
SUGGESTED TRADE LEVELS:
- Direction: {trade_idea.get('direction', 'N/A')}
- Entry: ₹{trade_idea['entry']}
- Stoploss: ₹{trade_idea.get('stoploss', 'N/A')}
- Target: ₹{trade_idea.get('target', 'N/A')}
- Risk:Reward: {trade_idea.get('risk_reward', 'N/A')}"""

    prompt = f"""You are a senior proprietary trading desk analyst. You have received the following technical analysis alert.

STOCK: {symbol}
CONFIDENCE SCORE: {confidence}%
TREND: Daily={trend.get('daily', 'N/A')}, Micro={trend.get('micro', 'N/A')}, Alignment={trend.get('alignment', 'N/A')}

SIGNALS DETECTED:
{chr(10).join(f'  • {s}' for s in signals)}
{trade_section}
{global_section}
{fii_section}
{sector_section}

YOUR TASK:
1. In 3-4 punchy sentences, give the head trader a BRIEF on this stock.
2. State whether this setup ALIGNS or CONTRADICTS the global macro picture.
3. If there's a trade idea, validate or challenge the entry/SL/target levels.
4. End with a clear RECOMMENDATION: TRADE IT, WATCH IT, or SKIP IT.

Be direct. No pleasantries. Sound like a fast-paced prop desk."""

    return prompt


def generate_market_brief(alert_data: dict) -> tuple[str, dict]:
    """
    Generate an LLM-powered brief with full market context.
    Returns: (brief_text, llm_metadata)
    """
    global_ctx = _fetch_global_context()
    prompt = _build_context_prompt(alert_data, global_ctx)

    llm_meta = {"model": AI_MODEL, "prompt_tokens": None, "completion_tokens": None}

    try:
        logging.info(f"🧠 Asking LLM to analyze {alert_data.get('symbol', 'UNKNOWN')}...")

        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are a fast-paced quantitative prop desk analyst. Be direct and actionable."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=250
        )

        brief = response.choices[0].message.content.strip()
        usage = response.usage
        if usage:
            llm_meta["prompt_tokens"] = usage.prompt_tokens
            llm_meta["completion_tokens"] = usage.completion_tokens

        return brief, llm_meta

    except Exception as e:
        logging.error(f"LLM call failed: {e}")
        # Fallback: generate a non-LLM summary
        symbol = alert_data.get('symbol', '???')
        sig_count = len(alert_data.get('signals', []))
        signal_type = alert_data.get('signal_type', 'NEUTRAL')
        confidence = alert_data.get('confidence', 0)

        fallback = (
            f"{symbol}: {signal_type} setup with {sig_count} signals. "
            f"Confidence: {confidence}%. "
            f"[LLM offline — manual review recommended]"
        )
        return fallback, llm_meta


def process_alert(ch, method, properties, body):
    """Process an incoming alert from Level 1 agents."""
    start_time = time.monotonic()
    symbol = None

    try:
        alert_data = json.loads(body)
        symbol = alert_data.get('symbol')
        agent_source = alert_data.get('agent', 'Unknown')

        # Skip self-generated alerts to prevent loops
        if agent_source == 'Head Analyst':
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        logging.info(f"🚨 ALERT from {agent_source} Agent for {symbol}")

        # Generate context-rich brief
        brief, llm_meta = generate_market_brief(alert_data)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Print
        print(f"\n{'='*60}")
        print(f"📊 TRADING DESK BRIEF: {symbol}")
        print(f"{'='*60}")
        print(brief)
        print(f"{'='*60}\n")

        # Speak (if TTS available)
        if tts_engine:
            try:
                tts_engine.say(brief)
                tts_engine.runAndWait()
            except Exception:
                pass

        # Republish enriched alert
        enriched_alert = {
            **alert_data,
            "agent": "Head Analyst",
            "summary": brief,
        }

        ch.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=f'alert.enriched.{symbol}',
            body=json.dumps(enriched_alert, default=str),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        logging.info(f"📤 Published enriched alert for {symbol}")

        # Log run with LLM metadata
        prompt_preview = f"Analyzed {symbol} from {agent_source} agent"
        _log_run(
            'SUCCESS', elapsed_ms, symbol,
            llm_model=llm_meta.get('model'),
            prompt_tokens=llm_meta.get('prompt_tokens'),
            completion_tokens=llm_meta.get('completion_tokens'),
            prompt_preview=prompt_preview,
            response_preview=brief[:500]
        )

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logging.error(f"Error processing alert: {e}")
        _log_run('FAILED', elapsed_ms, symbol, error=str(e)[:500])
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def start_head_analyst():
    """Connects to RabbitMQ and listens for alerts from Level 1 agents."""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    # Listen to all agent alerts (but NOT enriched to avoid loops)
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='alert.swing.#')
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='alert.screener.#')
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='alert.options.#')
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='alert.vector.#')

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_alert)

    logging.info(f"🧠 Head Analyst v2.0 online. Using LLM: {AI_MODEL} @ {OPENAI_API_BASE}")
    logging.info("   Injecting global cues, FII/DII flows, and sector rotation context.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
        connection.close()


if __name__ == "__main__":
    start_head_analyst()