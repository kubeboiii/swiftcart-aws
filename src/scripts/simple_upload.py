"""
Minimal S3 uploader: pushes index.html to the static-assets bucket so the
CloudFront default behavior has something to serve from the S3 origin.

Prerequisites (local machine):
    pip install boto3
    aws configure   # run before executing this script
"""

import boto3
import os

BUCKET_NAME = 'swiftcart-static-assets-YOUR-ACCOUNT-ID'
FILE_TO_UPLOAD = 'index.html'


def upload_to_s3():
    s3_client = boto3.client('s3')

    # Explicit ContentType so the browser renders it as a page, not a download
    extra_args = {'ContentType': 'text/html'}

    print(f"Uploading {FILE_TO_UPLOAD} to s3://{BUCKET_NAME}...")
    try:
        s3_client.upload_file(
            FILE_TO_UPLOAD, BUCKET_NAME, FILE_TO_UPLOAD, ExtraArgs=extra_args
        )
        print("Upload successful!")
    except Exception as e:
        print(f"Failed to upload: {e}")


if __name__ == '__main__':
    # Create a dummy index.html if it doesn't exist locally
    if not os.path.exists(FILE_TO_UPLOAD):
        with open(FILE_TO_UPLOAD, 'w') as f:
            f.write("<h1>SwiftCart Edge Content</h1>"
                    "<p>Served from S3 via CloudFront</p>")

    upload_to_s3()
