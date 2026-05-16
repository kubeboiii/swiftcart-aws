"""
SwiftCart Inventory Service

Runs on the EC2 instance in VPC B (Dark / Private). It serves a dual purpose:

  1. A Flask API on port 5000 for synchronous reads from the Web Portal
     (CQRS - Query path), reached over the Transit Gateway from VPC A.
  2. A background daemon thread long-polling SQS for asynchronous order
     processing (CQRS - Command path).

NOTE: In the modernized architecture the SQS consumer thread below is
replaced by the serverless AWS Lambda function (see
../lambda/lambda_function.py). This file is kept as the EC2-based
reference implementation.

Prerequisites on EC2:
    sudo yum update -y
    sudo yum install python3-pip -y
    pip3 install flask boto3
"""

import boto3
import json
import logging
import threading
import time
from flask import Flask, jsonify, request
from botocore.exceptions import ClientError

# -----------------------------------------------------------------------------
# Configuration and Logging Initialization
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] (%(threadName)-10s) %(message)s',
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Boto3 Client Setup utilizing IAM Instance Profile (No hardcoded credentials)
# Crucial: Region must match your VPC Endpoint configuration
REGION = 'us-west-2'
QUEUE_NAME = 'OrderProcessingQueue'

sqs_client = boto3.client('sqs', region_name=REGION)

try:
    response = sqs_client.get_queue_url(QueueName=QUEUE_NAME)
    QUEUE_URL = response['QueueUrl']
    logger.info(f"Successfully connected to SQS Queue: {QUEUE_URL}")
except ClientError as e:
    logger.error(f"Failed to fetch Queue URL. Check IAM permissions and VPC Endpoints: {e}")
    QUEUE_URL = None

# Mock Database for Lab Purposes (In-memory dict)
INVENTORY_DB = {
    "SKU-1001": {"name": "Mechanical Keyboard", "stock": 50, "price": 129.99},
    "SKU-1002": {"name": "Wireless Mouse", "stock": 120, "price": 49.99},
    "SKU-1003": {"name": "4K Monitor", "stock": 15, "price": 399.99}
}


# -----------------------------------------------------------------------------
# Synchronous Read Path: API Endpoints (CQRS - Query)
# -----------------------------------------------------------------------------
@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint for internal routing/monitoring."""
    return jsonify({"status": "healthy", "service": "inventory"}), 200


@app.route('/api/v1/inventory/<sku>', methods=['GET'])
def get_inventory(sku):
    """
    Synchronous read endpoint. Responds instantly to Web Portal requests
    originating over the Transit Gateway connection.
    """
    item = INVENTORY_DB.get(sku)
    if item:
        logger.info(f"Read request successful for SKU: {sku}")
        return jsonify({"status": "success", "data": item}), 200
    else:
        logger.warning(f"Read request failed. SKU not found: {sku}")
        return jsonify({"status": "error", "message": "SKU not found"}), 404


# -----------------------------------------------------------------------------
# Asynchronous Write Path: SQS Consumer Thread (CQRS - Command)
# -----------------------------------------------------------------------------
def process_sqs_messages():
    """
    Background worker that executes Long Polling against the SQS queue.
    This guarantees eventual consistency for inventory deductions.
    """
    if not QUEUE_URL:
        logger.error("SQS Worker thread terminating: QUEUE_URL is unavailable.")
        return

    logger.info("SQS Worker thread initialized. Beginning Long Polling...")

    while True:
        try:
            # WaitTimeSeconds=20 implements Long Polling.
            # Reduces API calls and costs significantly vs Short Polling.
            response = sqs_client.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
                MessageAttributeNames=['All']
            )

            messages = response.get('Messages', [])

            for msg in messages:
                receipt_handle = msg['ReceiptHandle']
                body = msg['Body']

                try:
                    # SNS wraps the actual message payload in a JSON envelope.
                    # We must parse the envelope, then parse the embedded Message string.
                    sns_envelope = json.loads(body)
                    order_data = json.loads(sns_envelope['Message'])

                    sku = order_data.get('sku')
                    quantity = order_data.get('quantity', 1)
                    order_id = order_data.get('order_id')

                    logger.info(f"Processing Order {order_id} for {quantity}x {sku}")

                    # Process Business Logic (Inventory Deduction)
                    if sku in INVENTORY_DB:
                        if INVENTORY_DB[sku]['stock'] >= quantity:
                            INVENTORY_DB[sku]['stock'] -= quantity
                            logger.info(
                                f"SUCCESS: Inventory deducted. New stock for {sku}: "
                                f"{INVENTORY_DB[sku]['stock']}"
                            )

                            # Only delete the message AFTER successful processing
                            sqs_client.delete_message(
                                QueueUrl=QUEUE_URL,
                                ReceiptHandle=receipt_handle
                            )
                        else:
                            logger.error(
                                f"FAILED: Insufficient stock for {sku}. Stock: "
                                f"{INVENTORY_DB[sku]['stock']}, Requested: {quantity}"
                            )
                            # In a real scenario, this goes to a Dead Letter Queue (DLQ)
                    else:
                        logger.error(f"FAILED: Unknown SKU {sku} in order {order_id}")

                except json.JSONDecodeError as e:
                    logger.error(f"Malformed JSON in SQS message: {e}")

        except ClientError as e:
            logger.error(f"SQS API Error: {e}")
            time.sleep(5)  # Backoff before retrying
        except Exception as e:
            logger.error(f"Unexpected error in worker thread: {e}")
            time.sleep(5)


# -----------------------------------------------------------------------------
# Application Execution
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    # Start the SQS consumer as a daemon thread so it exits when Flask stops
    sqs_thread = threading.Thread(target=process_sqs_messages, name="SQS-Poller-Thread")
    sqs_thread.daemon = True
    sqs_thread.start()

    # Run Flask API on all internal interfaces (0.0.0.0) on port 5000
    app.run(host='0.0.0.0', port=5000, debug=False)
