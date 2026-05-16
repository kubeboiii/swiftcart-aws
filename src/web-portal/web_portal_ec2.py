"""
SwiftCart Web Portal  (EC2 / non-containerized reference)

Runs directly on the EC2 instance in VPC A (Public). It is the front-end
REST API the customer interacts with:

  - Synchronous reads  -> Inventory Service in VPC B over the Transit Gateway
  - Asynchronous writes -> published to the SNS fan-out topic

NOTE: The modernized deployment replaces this with the 12-factor,
environment-driven, containerized version in web_portal.py (run via Docker).

Prerequisites on EC2:
    sudo yum update -y
    sudo yum install python3 -y
    pip3 install flask boto3 requests

Run with:  sudo python3 web_portal_ec2.py   (binds privileged port 80)
"""

import boto3
import json
import logging
import time
import uuid
import requests
from flask import Flask, jsonify, request
from botocore.exceptions import ClientError

# -----------------------------------------------------------------------------
# Configuration and Logging Initialization
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] WebPortal: %(message)s',
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Boto3 Setup for SNS (Event Publisher)
REGION = 'us-west-2'
sns_client = boto3.client('sns', region_name=REGION)

# YOU MUST REPLACE THIS with your actual AWS Account ID
AWS_ACCOUNT_ID = "YOUR_ACCOUNT_ID"
SNS_TOPIC_ARN = f"arn:aws:sns:{REGION}:{AWS_ACCOUNT_ID}:SwiftCart-Order-Fanout"

# INVENTORY SERVICE INTERNAL IP (Private IPv4 of the VPC B EC2 instance).
# Traffic routes over the Transit Gateway from VPC A into VPC B.
INVENTORY_SERVICE_IP = "10.20.1.X"
INVENTORY_API_URL = f"http://{INVENTORY_SERVICE_IP}:5000/api/v1/inventory"


# -----------------------------------------------------------------------------
# Web Routes
# -----------------------------------------------------------------------------
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "web_portal"}), 200


@app.route('/product/<sku>', methods=['GET'])
def view_product(sku):
    """
    Synchronous Read Path.
    Fetches real-time inventory data from VPC B over the Transit Gateway.
    """
    logger.info(f"Incoming product view request for SKU: {sku}")

    try:
        # 2-second timeout prevents cascading failures if VPC B is unreachable
        response = requests.get(f"{INVENTORY_API_URL}/{sku}", timeout=2)

        if response.status_code == 200:
            return jsonify({
                "page_render": "success",
                "product_details": response.json()['data']
            }), 200
        elif response.status_code == 404:
            return jsonify({"error": "Product not found in catalog"}), 404
        else:
            return jsonify({"error": "Upstream inventory service error"}), 502

    except requests.exceptions.RequestException as e:
        logger.error(f"Transit Gateway path or Inventory Service failure: {e}")
        return jsonify({
            "error": "Unable to connect to inventory service. "
                     "Check TGW routing and Security Groups."
        }), 503


@app.route('/checkout', methods=['POST'])
def checkout():
    """
    Asynchronous Write Path.
    Publishes an event to SNS for Fan-out. Returns immediate 202 Accepted.
    """
    payload = request.get_json()

    if not payload or 'sku' not in payload or 'quantity' not in payload:
        return jsonify({"error": "Malformed request payload"}), 400

    order_id = str(uuid.uuid4())
    customer_email = payload.get('email', 'guest@swiftcart.local')

    # Construct the Command payload
    order_event = {
        "order_id": order_id,
        "sku": payload['sku'],
        "quantity": payload['quantity'],
        "customer_email": customer_email,
        "timestamp": time.time()
    }

    try:
        # Publish to SNS.
        # This triggers both the Email subscription AND the SQS queue asynchronously.
        response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=json.dumps(order_event),
            Subject=f"SwiftCart Order Confirmation: {order_id}"
        )

        logger.info(f"Order event published successfully. MessageId: {response['MessageId']}")

        # Immediate return to user. Do not wait for database updates.
        return jsonify({
            "status": "Order Accepted",
            "order_id": order_id,
            "message": "Your order is being processed asynchronously."
        }), 202

    except ClientError as e:
        logger.error(f"SNS Publish Error. Check IAM Roles and VPC Endpoints: {e}")
        return jsonify({"error": "Internal event bus failure"}), 500


# -----------------------------------------------------------------------------
# Application Execution
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    # Web Portal binds to port 80 to accept traffic from the ALB
    # NOTE: Run via `sudo python3 web_portal_day1.py` to bind to privileged port 80
    app.run(host='0.0.0.0', port=80, debug=False)
