import os


DOMAIN = os.environ.get('DOMAIN')
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_WRITE_BUCKET = os.environ.get('S3_WRITE_BUCKET')
AWS_REGION = os.environ.get('AWS_REGION')
TEST_IMAGE = os.environ.get('TEST_IMAGE')
MULTI_CUSTOMER_MODE = os.environ.get('MULTI_CUSTOMER_MODE', 'false').lower() == 'true'
SECRETS_BUCKET = os.environ.get('SECRETS_BUCKET')
DEFAULT_CUSTOMER = os.environ.get('DEFAULT_CUSTOMER')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
