"""
Judge Node — Evaluates the debate between the Primary Builder and the Adversarial Critic.

Takes the completed setups and the critic's counter-arguments, applying
"Lessons Learned" from historical runs, and outputs the final approved lists.
"""

import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:JUDGE] - %(message)s')

OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
JUDGE_MODEL = os.getenv("AI_MODEL", "qwen2.5-coder:14b")


def judge_node(state: dict) -> dict:
    """
    Final decision maker for trade setups.
    Reads:
      - intraday_setups
      - options_setups
      - critic_debate
      - lessons_learned
      - defense_mode
    Writes:
      - intraday_setups (filtered)
      - options_setups (filtered)
      - avoid_list (appended)
      - all_evidence
    """
    intraday_setups = state.get("intraday_setups", [])
    options_setups = state.get("options_setups", [])
    critic_debate = state.get("critic_debate", [])
    lessons_learned = state.get("lessons_learned", [])
    defense_mode = state.get("defense_mode", False)
    avoid_list = state.get("avoid_list", [])
    
    all_setups = intraday_setups + options_setups
    evidence = []

    if not all_setups:
        logging.info("No built setups for the Judge to review.")
        return {}

    logging.info(f"⚖️  Judge analyzing {len(all_setups)} built setups against Critic arguments using {JUDGE_MODEL}...")

    # Build local lookup for critic arguments
    debate_map = {d["symbol"]: d for d in critic_debate}
    
    # Format lessons learned into a string
    lessons_text = ""
    if lessons_learned:
        lessons_text = "Historical Lessons to Apply Today:\n" + "\n".join([f"- Under {l.get('regime')} regime: {l.get('lesson')}" for l in lessons_learned])

    try:
        from openai import OpenAI
        client = OpenAI(base_url=OPENAI_API_BASE, api_key=OPENAI_API_KEY)
    except Exception as e:
        logging.error(f"Failed to initialize OpenAI client for Judge: {e}")
        return {}

    final_intraday = []
    final_options = []
    
    for setup in all_setups:
        symbol = setup.get("symbol")
        direction = setup.get("direction", "UNKNOWN")
        confidence = setup.get("confidence")
        
        critic_data = debate_map.get(symbol, {})
        critic_verdict = critic_data.get("critic_verdict", "APPROVE")
        critic_argument = critic_data.get("critic_argument", "None.")

        prompt = f"""You are the Chief Investment Officer (Judge). You must decide if we execute this trade.
        
System Settings:
- Defense Mode Active: {defense_mode} (If True, be extremely strict and cut position sizes).
{lessons_text}

Trade Proposal (Primary Builder):
- Stock: {symbol}
- Direction: {direction}
- Confidence: {confidence}%
- Target: {setup.get('target')}, Stop Loss: {setup.get('stoploss')}

Adversarial Critic Argument:
- Critic Verdict: {critic_verdict}
- Counter-Argument: {critic_argument}

Analyze the Primary Builder's setup against the Critic's objection and the historical lessons.
Decide the final outcome. You must reply strictly in valid JSON format:
{{
  "final_decision": "APPROVED" | "REJECTED" | "MODIFIED_TO_SCALP",
  "reasoning": "1 sentence explanation.",
  "position_size_modifier": 1.0 (default) or 0.5 (if Defense Mode or high risk)
}}
"""

        try:
            response = client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[
                    {"role": "system", "content": "You are the final Judge node. You output strict JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            raw_response = response.choices[0].message.content
            judgement = json.loads(raw_response)
            
            final_decision = judgement.get("final_decision", "REJECTED")
            reasoning = judgement.get("reasoning", "No valid reasoning provided.")
            size_mod = judgement.get("position_size_modifier", 1.0)
            
            # Enforce hard defense mode logic
            if defense_mode and size_mod > 0.5:
                size_mod = 0.5
                reasoning += " (Position halved due to Defense Mode)."
                
            logging.info(f"    ↳ {symbol} Final: {final_decision}. Reason: {reasoning}")
            
            evidence.append({
                "node": "judge",
                "symbol": symbol,
                "primary_confidence": confidence,
                "critic_argument": critic_argument,
                "final_decision": final_decision,
                "reasoning": reasoning,
                "size_modifier": size_mod
            })
            
            if final_decision in ["APPROVED", "MODIFIED_TO_SCALP"]:
                setup["judge_approved"] = True
                setup["judge_reason"] = reasoning
                setup["position_size_modifier"] = size_mod
                
                if final_decision == "MODIFIED_TO_SCALP":
                    setup["signal_type"] = f"SCALP_{setup.get('signal_type', '')}"
                
                # Sort back into correct list
                if "INTRADAY" in setup.get("trade_type", ""):
                    final_intraday.append(setup)
                else:
                    final_options.append(setup)
            else:
                avoid_list.append(symbol)

        except Exception as e:
            logging.warning(f"    ↳ {symbol} Judge failed to respond: {e}. Defaulting to REJECT to be safe.")
            avoid_list.append(symbol)

    logging.info(f"  Judge complete: Approved {len(final_intraday)} intraday and {len(final_options)} options setups.")

    return {
        "intraday_setups": final_intraday,
        "options_setups": final_options,
        "avoid_list": avoid_list,
        "all_evidence": evidence,
    }
