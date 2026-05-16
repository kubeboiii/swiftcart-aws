"""
SwiftCart Web Portal  (Day 3 - Containerized, 12-Factor)

Slightly modified from Day 1 to pull all configuration from environment
variables, which is the 12-Factor App standard for containers. Runs inside
Docker on the VPC A EC2 host (see Dockerfile / docker-compose.yml).
"""

import boto3
import json
import logging
import os
import uuid
import requests
from flask import Flask, jsonify, request

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] WebContainer: %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Config driven by environment variables injected by Docker
REGION = os.environ.get('AWS_REGION', 'us-west-2')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
INVENTORY_API_URL = os.environ.get('INVENTORY_API_URL')

sns_client = boto3.client('sns', region_name=REGION)


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "web_portal_container"}), 200


@app.route('/checkout', methods=['POST'])
def checkout():
    payload = request.get_json()
    if not payload or 'sku' not in payload:
        return jsonify({"error": "Malformed request payload"}), 400

    order_id = str(uuid.uuid4())

    order_event = {
        "order_id": order_id,
        "sku": payload['sku'],
        "quantity": payload.get('quantity', 1),
        "customer_email": payload.get('email', 'guest@swiftcart.local')
    }

    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=json.dumps(order_event),
            Subject=f"SwiftCart Order: {order_id}"
        )
        logger.info("Container processed checkout. Event sent to SNS.")
        return jsonify({"status": "Accepted", "order_id": order_id}), 202
    except Exception as e:
        logger.error(f"Failed to publish to SNS: {e}")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    # Binds to 0.0.0.0 so Docker can map the port
    app.run(host='0.0.0.0', port=80, debug=False)
