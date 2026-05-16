"""
SwiftCart Order Processor  (AWS Lambda)

This serverless function replaces the EC2 background worker thread. It is
invoked by AWS via an SQS Event Source Mapping (batch size = 10). AWS
infrastructure polls the queue on our behalf; the function only runs when
messages exist and scales out automatically under load.

Runtime:      Python 3.12
Architecture: arm64 (Graviton - faster & cheaper for serverless)
Execution role: SwiftCart-ServerlessProcessor-Role
  (sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes,
   logs:CreateLogStream)

NOTE: Because Lambda is stateless, a production version would write the
state change to DynamoDB or RDS instead of an in-memory structure.
"""

import json
import logging
import time

# Configure logging for CloudWatch
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    AWS Lambda handler for processing SQS messages.
    The AWS infrastructure handles the polling. This function is invoked
    ONLY when messages exist, receiving up to 10 messages in the 'event' object.
    """
    logger.info(f"Lambda invoked. Received {len(event['Records'])} messages in batch.")

    # We must track failures. If a message fails to process, we do NOT want it
    # deleted from the queue. SQS handles retries based on Lambda's response.
    batch_item_failures = []

    for record in event['Records']:
        message_id = record['messageId']
        try:
            # 1. Parse the SNS envelope wrapper
            sns_envelope = json.loads(record['body'])

            # 2. Parse the actual order payload from the SNS message
            order_data = json.loads(sns_envelope['Message'])

            sku = order_data.get('sku')
            quantity = order_data.get('quantity', 1)
            order_id = order_data.get('order_id')
            customer_email = order_data.get('customer_email')

            # Simulated Processing Time
            logger.info(
                f"Processing Order ID: {order_id} | SKU: {sku} | "
                f"Qty: {quantity} | Customer: {customer_email}"
            )
            time.sleep(0.5)

            # In a real environment, you would execute an UPDATE statement
            # against DynamoDB/RDS here.
            # Example: dynamodb_client.update_item(...)

            logger.info(f"SUCCESS: Order {order_id} processed successfully.")

        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Error for message {message_id}: {str(e)}")
            # If the payload is completely malformed, fail the message -> DLQ
            batch_item_failures.append({"itemIdentifier": message_id})

        except Exception as e:
            logger.error(f"Unexpected error processing message {message_id}: {str(e)}")
            batch_item_failures.append({"itemIdentifier": message_id})

    # Return partial batch failure response. AWS SQS will automatically delete
    # the successful messages and make the failed ones visible again for retry.
    return {
        "batchItemFailures": batch_item_failures
    }
