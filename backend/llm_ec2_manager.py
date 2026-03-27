import os
import boto3
import logging
import time
from dotenv import load_dotenv

load_dotenv()

# AWS Configuration
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
INSTANCE_ID = os.getenv("LLM_INSTANCE_ID") # e.g., 'i-0abcd1234efgh5678'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [EC2 MANAGER] - %(message)s')

def get_ec2_client():
    return boto3.client(
        'ec2',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
    )

def start_instance():
    """Starts the remote LLM instance to save on idle costs."""
    if not INSTANCE_ID:
        logging.error("LLM_INSTANCE_ID not found in .env. Skipping...")
        return False
        
    ec2 = get_ec2_client()
    try:
        logging.info(f"🚀 Starting EC2 Instance: {INSTANCE_ID}...")
        ec2.start_instances(InstanceIds=[INSTANCE_ID])
        
        # Wait for it to be running (optional)
        waiter = ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=[INSTANCE_ID])
        logging.info(f"✅ EC2 Instance {INSTANCE_ID} is now RUNNING.")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to start instance: {e}")
        return False

def stop_instance():
    """Stops the remote LLM instance to save on costs."""
    if not INSTANCE_ID:
        return False
        
    ec2 = get_ec2_client()
    try:
        logging.info(f"🛑 Stopping EC2 Instance: {INSTANCE_ID}...")
        ec2.stop_instances(InstanceIds=[INSTANCE_ID])
        logging.info(f"✅ Stop request sent for {INSTANCE_ID}.")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to stop instance: {e}")
        return False

def get_instance_status():
    """Checks the current power state of the machine."""
    if not INSTANCE_ID:
        return "CONFIG_MISSING"
        
    ec2 = get_ec2_client()
    try:
        response = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
        state = response['Reservations'][0]['Instances'][0]['State']['Name']
        return state
    except Exception as e:
        logging.error(f"❌ Failed to fetch status: {e}")
        return "UNKNOWN"

if __name__ == "__main__":
    # Test fetch status
    print(f"Current LLM Instance Status: {get_instance_status()}")
