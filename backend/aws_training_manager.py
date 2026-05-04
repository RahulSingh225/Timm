# backend/aws_training_manager.py
"""
AWS TRAINING PIPELINE MANAGER (Phase 8)
Manages GPU spot instance lifecycle for ML training:
  - Request/manage spot instances (g4dn.xlarge with T4 GPU)
  - S3 model artifact storage with versioning
  - CloudWatch alerts for training failures
  - Cost tracking and monitoring
"""

import os
import json
import time
import logging
import boto3
from datetime import datetime, timedelta
from typing import Optional, Dict
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET = os.getenv("S3_MODEL_BUCKET", "timm-model-artifacts")
GPU_INSTANCE_TYPE = os.getenv("GPU_INSTANCE_TYPE", "g4dn.xlarge")
GPU_AMI_ID = os.getenv("GPU_AMI_ID", "")  # Deep Learning AMI
GPU_KEY_NAME = os.getenv("GPU_KEY_NAME", "timm-gpu-key")
GPU_SECURITY_GROUP = os.getenv("GPU_SECURITY_GROUP", "")
GPU_SUBNET_ID = os.getenv("GPU_SUBNET_ID", "")
TRAINING_INSTANCE_ID = os.getenv("TRAINING_INSTANCE_ID", "")


def _get_s3():
    return boto3.client("s3", aws_access_key_id=AWS_ACCESS_KEY,
                        aws_secret_access_key=AWS_SECRET_KEY, region_name=AWS_REGION)


def _get_ec2():
    return boto3.client("ec2", aws_access_key_id=AWS_ACCESS_KEY,
                        aws_secret_access_key=AWS_SECRET_KEY, region_name=AWS_REGION)


def _get_cloudwatch():
    return boto3.client("cloudwatch", aws_access_key_id=AWS_ACCESS_KEY,
                        aws_secret_access_key=AWS_SECRET_KEY, region_name=AWS_REGION)


# ═══════════════════════════════════════
#  S3 MODEL STORAGE
# ═══════════════════════════════════════

def ensure_s3_bucket():
    """Create the S3 bucket if it doesn't exist."""
    s3 = _get_s3()
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
        logger.info(f"✅ S3 bucket {S3_BUCKET} exists")
    except ClientError:
        try:
            if AWS_REGION == "us-east-1":
                s3.create_bucket(Bucket=S3_BUCKET)
            else:
                s3.create_bucket(Bucket=S3_BUCKET,
                                 CreateBucketConfiguration={"LocationConstraint": AWS_REGION})
            # Enable versioning
            s3.put_bucket_versioning(Bucket=S3_BUCKET,
                                     VersioningConfiguration={"Status": "Enabled"})
            logger.info(f"📦 Created S3 bucket {S3_BUCKET} with versioning")
        except Exception as e:
            logger.error(f"Failed to create S3 bucket: {e}")


def upload_model(local_path: str, model_name: str, version: int,
                 metadata: Optional[Dict] = None) -> str:
    """Upload a model artifact to S3 with metadata."""
    s3 = _get_s3()
    ext = os.path.splitext(local_path)[1]
    s3_key = f"models/{model_name}/v{version}/{model_name}_v{version}{ext}"

    try:
        extra_args = {"Metadata": {}}
        if metadata:
            for k, v in metadata.items():
                extra_args["Metadata"][k] = str(v)[:1024]
        extra_args["Metadata"]["uploaded_at"] = datetime.utcnow().isoformat()
        extra_args["Metadata"]["version"] = str(version)

        s3.upload_file(local_path, S3_BUCKET, s3_key, ExtraArgs=extra_args)
        s3_uri = f"s3://{S3_BUCKET}/{s3_key}"
        logger.info(f"📤 Uploaded {model_name} v{version} → {s3_uri}")
        return s3_uri
    except Exception as e:
        logger.error(f"Failed to upload model: {e}")
        return ""


def download_model(model_name: str, version: Optional[int] = None,
                   local_dir: str = "models") -> str:
    """Download latest (or specific version) model from S3."""
    s3 = _get_s3()
    os.makedirs(local_dir, exist_ok=True)

    try:
        prefix = f"models/{model_name}/"
        if version:
            prefix = f"models/{model_name}/v{version}/"

        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        if "Contents" not in response:
            logger.warning(f"No model found for {model_name} in S3")
            return ""

        # Get latest by LastModified
        objects = sorted(response["Contents"], key=lambda x: x["LastModified"], reverse=True)
        latest = objects[0]
        s3_key = latest["Key"]
        local_path = os.path.join(local_dir, os.path.basename(s3_key))

        s3.download_file(S3_BUCKET, s3_key, local_path)
        logger.info(f"📥 Downloaded {s3_key} → {local_path}")
        return local_path
    except Exception as e:
        logger.error(f"Failed to download model: {e}")
        return ""


def list_s3_models() -> list:
    """List all models in S3."""
    s3 = _get_s3()
    try:
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="models/", Delimiter="/")
        models = []
        for prefix in response.get("CommonPrefixes", []):
            name = prefix["Prefix"].replace("models/", "").rstrip("/")
            # Count versions
            versions = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix["Prefix"])
            n_versions = len(versions.get("Contents", []))
            models.append({"name": name, "versions": n_versions})
        return models
    except Exception as e:
        logger.error(f"Failed to list S3 models: {e}")
        return []


# ═══════════════════════════════════════
#  GPU SPOT INSTANCE MANAGEMENT
# ═══════════════════════════════════════

def request_spot_instance() -> Optional[str]:
    """Request a GPU spot instance for training (~70% cost savings)."""
    ec2 = _get_ec2()
    try:
        response = ec2.request_spot_instances(
            InstanceCount=1,
            Type="one-time",
            LaunchSpecification={
                "ImageId": GPU_AMI_ID,
                "InstanceType": GPU_INSTANCE_TYPE,
                "KeyName": GPU_KEY_NAME,
                "SecurityGroupIds": [GPU_SECURITY_GROUP] if GPU_SECURITY_GROUP else [],
                "SubnetId": GPU_SUBNET_ID if GPU_SUBNET_ID else None,
                "IamInstanceProfile": {"Name": "timm-training-role"},
                "BlockDeviceMappings": [{
                    "DeviceName": "/dev/sda1",
                    "Ebs": {"VolumeSize": 100, "VolumeType": "gp3"},
                }],
                "UserData": _get_training_userdata(),
            },
        )
        request_id = response["SpotInstanceRequests"][0]["SpotInstanceRequestId"]
        logger.info(f"🚀 Spot instance requested: {request_id}")
        return request_id
    except Exception as e:
        logger.error(f"Failed to request spot instance: {e}")
        return None


def start_training_instance() -> bool:
    """Start the dedicated training EC2 instance (if using on-demand)."""
    if not TRAINING_INSTANCE_ID:
        logger.warning("TRAINING_INSTANCE_ID not set")
        return False
    ec2 = _get_ec2()
    try:
        ec2.start_instances(InstanceIds=[TRAINING_INSTANCE_ID])
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[TRAINING_INSTANCE_ID])
        logger.info(f"✅ Training instance {TRAINING_INSTANCE_ID} started")
        return True
    except Exception as e:
        logger.error(f"Failed to start training instance: {e}")
        return False


def stop_training_instance() -> bool:
    """Stop the training instance after training completes."""
    if not TRAINING_INSTANCE_ID:
        return False
    ec2 = _get_ec2()
    try:
        ec2.stop_instances(InstanceIds=[TRAINING_INSTANCE_ID])
        logger.info(f"🛑 Training instance {TRAINING_INSTANCE_ID} stop requested")
        return True
    except Exception as e:
        logger.error(f"Failed to stop training instance: {e}")
        return False


def get_training_cost_estimate() -> Dict:
    """Estimate training costs based on recent usage."""
    # g4dn.xlarge pricing (ap-south-1)
    ON_DEMAND_HOURLY = 0.526   # USD/hr
    SPOT_HOURLY = 0.158        # ~70% discount
    S3_GB_MONTHLY = 0.025      # USD/GB/month

    try:
        s3 = _get_s3()
        total_size = 0
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="models/")
        for obj in response.get("Contents", []):
            total_size += obj["Size"]
        s3_cost = (total_size / (1024**3)) * S3_GB_MONTHLY
    except Exception:
        s3_cost = 0

    return {
        "gpu_instance_type": GPU_INSTANCE_TYPE,
        "on_demand_hourly_usd": ON_DEMAND_HOURLY,
        "spot_hourly_usd": SPOT_HOURLY,
        "spot_savings_pct": round((1 - SPOT_HOURLY / ON_DEMAND_HOURLY) * 100),
        "s3_storage_monthly_usd": round(s3_cost, 3),
        "estimated_monthly_training_usd": round(SPOT_HOURLY * 2 * 30, 2),  # ~2hrs/day
    }


def _get_training_userdata() -> str:
    """Bootstrap script for spot instances."""
    import base64
    script = """#!/bin/bash
set -e
cd /home/ubuntu/Timm/backend
source /home/ubuntu/.venv/bin/activate
python run_graph.py --phase training
# Upload models to S3 after training
aws s3 sync models/ s3://{bucket}/models/ --exclude "*.tmp"
# Self-terminate after training
sudo shutdown -h now
""".format(bucket=S3_BUCKET)
    return base64.b64encode(script.encode()).decode()


# ═══════════════════════════════════════
#  CLOUDWATCH ALERTS
# ═══════════════════════════════════════

def setup_cloudwatch_alerts(sns_topic_arn: str = ""):
    """Configure CloudWatch alarms for training monitoring."""
    cw = _get_cloudwatch()
    try:
        # Training failure alarm
        cw.put_metric_alarm(
            AlarmName="timm-training-failure",
            AlarmDescription="Alert when ML training fails",
            MetricName="TrainingFailures",
            Namespace="Timm/ML",
            Statistic="Sum",
            Period=3600, EvaluationPeriods=1,
            Threshold=1, ComparisonOperator="GreaterThanOrEqualToThreshold",
            ActionsEnabled=bool(sns_topic_arn),
            AlarmActions=[sns_topic_arn] if sns_topic_arn else [],
        )

        # Model degradation alarm (Sharpe drops below 0.3)
        cw.put_metric_alarm(
            AlarmName="timm-model-degradation",
            AlarmDescription="Alert when production model Sharpe drops",
            MetricName="ProductionSharpe",
            Namespace="Timm/ML",
            Statistic="Average",
            Period=86400, EvaluationPeriods=3,
            Threshold=0.3, ComparisonOperator="LessThanThreshold",
            ActionsEnabled=bool(sns_topic_arn),
            AlarmActions=[sns_topic_arn] if sns_topic_arn else [],
        )

        # GPU cost alarm (>$50/day)
        cw.put_metric_alarm(
            AlarmName="timm-gpu-cost-high",
            AlarmDescription="Alert when GPU costs exceed budget",
            MetricName="GPUCostUSD",
            Namespace="Timm/ML",
            Statistic="Sum",
            Period=86400, EvaluationPeriods=1,
            Threshold=50, ComparisonOperator="GreaterThanThreshold",
            ActionsEnabled=bool(sns_topic_arn),
            AlarmActions=[sns_topic_arn] if sns_topic_arn else [],
        )

        logger.info("✅ CloudWatch alarms configured")
    except Exception as e:
        logger.error(f"Failed to setup CloudWatch: {e}")


def publish_training_metric(metric_name: str, value: float, unit: str = "None"):
    """Publish a custom metric to CloudWatch."""
    cw = _get_cloudwatch()
    try:
        cw.put_metric_data(
            Namespace="Timm/ML",
            MetricData=[{
                "MetricName": metric_name,
                "Value": value,
                "Unit": unit,
                "Timestamp": datetime.utcnow(),
            }]
        )
    except Exception as e:
        logger.warning(f"Failed to publish metric {metric_name}: {e}")
