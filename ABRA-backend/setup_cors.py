import boto3, os, dotenv
from botocore.client import Config
dotenv.load_dotenv()

s3 = boto3.client('s3', 
    endpoint_url=f'https://{os.getenv("BLAZE_ENDPOINT")}', 
    aws_access_key_id=os.getenv("BLAZE_KEYID"), 
    aws_secret_access_key=os.getenv("BLAZE_APPKEY"), 
    config=Config(signature_version='s3v4')
)

cors_configuration = {
    'CORSRules': [{
        'AllowedHeaders': ['*'],
        'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
        'AllowedOrigins': ['*'],
        'ExposeHeaders': ['ETag'],
        'MaxAgeSeconds': 3000
    }]
}

s3.put_bucket_cors(
    Bucket=os.getenv('B2_BUCKET_NAME'),
    CORSConfiguration=cors_configuration
)

print('CORS rules applied successfully!')
