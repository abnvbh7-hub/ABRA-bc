import boto3, os, dotenv, uuid
import requests
from botocore.client import Config

dotenv.load_dotenv()
s3 = boto3.client('s3', 
    endpoint_url=f"https://{os.getenv('BLAZE_ENDPOINT')}", 
    aws_access_key_id=os.getenv("BLAZE_KEYID"), 
    aws_secret_access_key=os.getenv("BLAZE_APPKEY"), 
    config=Config(signature_version='s3v4')
)

key = str(uuid.uuid4())
url = s3.generate_presigned_url(
    'put_object', 
    Params={'Bucket': os.getenv('B2_BUCKET_NAME'), 'Key': key, 'ContentType': 'image/jpeg'}, 
    ExpiresIn=3600
)
print('URL:', url)

res = requests.put(url, data=b'test', headers={'Content-Type': 'image/jpeg'})
print('Status:', res.status_code)
print('Response:', res.text)
