import os
import re

files_to_update = [
    "main.py",
    "system_manager.py",
    "swing_agent_worker.py",
    "yfinance_producer.py",
    "nse_participant_scraper.py",
    "db_vault_worker.py",
    "news_scraper_producer.py",
    "options_agent_worker.py",
    "option_footprint_producer.py",
    "nsdl_sector_scraper.py",
    "nse_flows_scrapper.py",
    "nsdl_tradewise_scraper.py"
]

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    original = content
    
    # 1. Ensure `os` and `dotenv` are imported and loaded
    if "import os" not in content:
        # Inject right after the first import or at the top safely
        first_import_match = re.search(r'import \w+', content)
        if first_import_match:
            idx = first_import_match.start()
            content = content[:idx] + "import os\nfrom dotenv import load_dotenv\nload_dotenv()\n" + content[idx:]
    else:
        # Ensure load_dotenv exists if os does
        if "load_dotenv" not in content:
            content = content.replace("import os", "import os\nfrom dotenv import load_dotenv\nload_dotenv()")
    
    # 2. Update RABBITMQ_HOST constant
    content = re.sub(r"RABBITMQ_HOST\s*=\s*'localhost'", "RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')", content)
    
    # 3. Update DB_URL in db_vault_worker.py
    # `DB_URL = "postgresql://admin:supersecretpassword@localhost:5432/propdesk"`
    content = re.sub(r'DB_URL\s*=\s*".*?"', 'DB_URL = os.getenv("DATABASE_URL", "postgresql://admin:supersecretpassword@localhost:5432/propdesk")', content)
    
    # 4. Update PlainCredentials ('admin', 'supersecretpassword')
    content = re.sub(r"pika\.PlainCredentials\('admin',\s*'supersecretpassword'\)", 
                     "pika.PlainCredentials(os.getenv('RABBITMQ_USER', 'admin'), os.getenv('RABBITMQ_PASS', 'pwd'))", content)
    content = content.replace("'pwd'", "'supersecretpassword'") # safe placeholder replacement

    # 5. Fix ConnectionParameters('localhost', 5672)
    content = re.sub(r"pika\.ConnectionParameters\('localhost',\s*5672", 
                     "pika.ConnectionParameters(os.getenv('RABBITMQ_HOST', 'localhost'), 5672", content)
                     
    # 6. Fix `pika.ConnectionParameters(RABBITMQ_HOST)` to add credentials where missing
    # like in nse_flows_scrapper.py and nsdl_sector_scraper.py
    missing_creds_pattern = r"pika\.ConnectionParameters\(RABBITMQ_HOST\)"
    replacement_creds = "pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', pika.PlainCredentials(os.getenv('RABBITMQ_USER', 'admin'), os.getenv('RABBITMQ_PASS', 'supersecretpassword')))"
    content = re.sub(missing_creds_pattern, replacement_creds, content)
    
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Updated {filepath}")

for f in files_to_update:
    if os.path.exists(f):
        update_file(f)
