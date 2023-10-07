import logging
import os
import typing
from dataclasses import dataclass, field
from functools import partial
import urllib.parse
import boto
import boto.s3.connection
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from io import BytesIO
from boto.s3.key import Key
from wand.image import Image

from prism.image import ImageOperator, convert_to_premultiplied_png


logger = logging.getLogger(__name__)


# retry configuration for use with Requests to retry
# connection, timeout and status 500 responses.
retries = Retry(total=5,
                backoff_factor=0.1,
                status_forcelist=[500])


class EmptyOriginalFile(Exception):
    message = 'The original file has 0 bytes.'


class InvalidImageError(Exception):
    message = 'InvalidImageError. Image file is corrupted or invalid.'


def info(img):
    img.auto_orient()  # orient the image properly using exif info
    data = {'img_type': img.type,
            'alpha_channel': img.alpha_channel,
            'exif': {},
            'width': img.width,
            'height': img.height
            }
    for key in img.metadata:
        try:
            data['exif'][key] = img.metadata[key]
        except UnicodeDecodeError:
            pass
    return data


def resize(img, cmd, options):
    imop = ImageOperator(img)
    width = options['w']
    height = options['h']

    fn = getattr(imop, cmd)
    # calling our resize function now, yeahh !!!
    logging.info("resizing %s w: %s, h: %s, options: %s", fn, width, height, options)
    fn((width, height), **options)

    filters = options.get('filters')
    if filters:
        for filter in filters:
            logging.info("adding filter %s", filter)
            fn_filter = getattr(imop, filter['id'])

            t = {}
            for k, v in filter.iteritems():
                t[k.replace('-', '_')] = v
            fn_filter(**t)

    imop.image.compression_quality = options['q']
    f = BytesIO()
    imop.write(f, options['out_format'])
    f.seek(0)

    if options['premultiplied_alpha']:
        f = convert_to_premultiplied_png(f)
        f.seek(0)
    return f


def get_thumb_filename(file_name, cmd, options):
    # Note: The filenames produced by this function do not match those of previous versions of Prism.
    # We cannot match the format of the previous version in Python 3.
    # This causes s3 misses against all previously generated images. We are ok with that.

    # Only options with non default values are included in the params attached to the filename.
    # It is important to ensure the defaults here match those in app.parse_args
    # Note: The ordering of this dict determines the order of params in the filename.
    # New params should be added to the end of this dict.
    default_options = {
        'w': None,
        'h': None,
        'q': 95,
        'crop_width': None,
        'crop_height': None,
        'crop_y': None,
        'crop_x': None,
        'frame_bg_color': 'FFF',
        'gravity': 'center',
        'preserve_ratio': True,
        'premultiplied_alpha': None,
        'filters': None,
    }

    params = []
    for k in default_options:
        if options[k] != default_options.get(k) and options[k] is not None:
            value = options[k]
            params.append(f'{k}__{value}')
    param_string = '--'.join(params)

    out_format = options['out_format']
    if out_format == "":
        # Fallback to "png" on extensionless original objects.
        extension = ".png"
    else:
        extension = '.%s' % options['out_format']

    new_filename = f'{file_name}--{cmd}--{param_string}{extension}'

    return 'prism-images/' + new_filename


def split_endpoint_url(endpoint_url: str) -> typing.Tuple[str, int, bool]:
    """ Split the endpoint url into parts to use with boto.s3.connection.S3Connection

    Primarily for using alternative S3 endpoints such as Ceph, Minio, DigitalOcean Spaces, etc.
    """
    parsed_url = urllib.parse.urlparse(endpoint_url)
    host = parsed_url.hostname
    assert host, "S3 endpoint URL must contain a hostname"
    secure = parsed_url.scheme == 'https'
    port = parsed_url.port or (443 if secure else 80)
    return host, port, secure


@dataclass
class S3ConnectionConfig:
    """Config for connecting to S3 with fallback to environment variables."""
    key_id: typing.Optional[str] = field(default_factory=partial(os.environ.get, 'AWS_ACCESS_KEY_ID'))
    secret_key: typing.Optional[str] = field(default_factory=partial(os.environ.get, 'AWS_SECRET_ACCESS_KEY'))
    region: typing.Optional[str] = field(default_factory=partial(os.environ.get, 'AWS_REGION'))
    endpoint_url: typing.Optional[str] = field(default_factory=partial(os.environ.get, 'S3_ENDPOINT_URL'))


def get_s3_client(config: typing.Optional[S3ConnectionConfig] = None) -> boto.s3.connection.S3Connection:
    """ Get an S3 connection using the given configuration.

    @TODO Simplify this when Prism is updated to use boto3
    """

    config = config or S3ConnectionConfig()

    if config.endpoint_url:
        host, port, secure = split_endpoint_url(config.endpoint_url)
        conn = boto.s3.connection.S3Connection(
            config.key_id,
            config.secret_key,
            host=host,
            port=port,
            is_secure=secure,
            calling_format=boto.s3.connection.OrdinaryCallingFormat(),
        )
    elif config.region and config.region != 'us-east-1':
        host = 's3-%s.amazonaws.com' % config.region
        conn = boto.s3.connect_to_region(
            config.region,
            aws_access_key_id=config.key_id,
            aws_secret_access_key=config.secret_key,
            host=host,
        )
    else:
        conn = boto.connect_s3(config.key_id, config.secret_key)
    
    return conn


def get_s3_url(bucket_name, bucket_region, path, endpoint=None):
    """Get the public URL for an S3 object.

    @TODO simplify this when boto v2 is updated to boto v3 
    @TODO shouldn't this use signed urls or pull from the bucket directly?
    """

    if endpoint:
        url = '{endpoint}/{bucket}/{path}'.format(
            endpoint=endpoint.rstrip("/"),
            bucket=bucket_name,
            path=path.lstrip("/")
        )
    else:
        # we use region specific urls because s3 virtual hosts don't work with https
        # when the bucket name contains a '.'
        if bucket_region == 'us-east-1':
            subdomain = 's3'  # oh amazon :(
        else:
            subdomain = 's3-' + bucket_region
        url = 'https://{subdomain}.amazonaws.com/{bucket}/{path}'.format(
            subdomain=subdomain, bucket=bucket_name, path=path
        )
    logger.debug("S3 public URL: %s", url)
    return url


def fetch_image(url):
    s = requests.Session()
    s.mount('https://', HTTPAdapter(max_retries=retries))
    print(f"Fetching {url}")
    r = s.get(url, timeout=5.0)
    t = r.elapsed.total_seconds()
    logging.info('S3 GET request time: %0.2f', t)
    r.raise_for_status()
    if r.headers['content-length'] == '0':
        raise EmptyOriginalFile
    try:
        im = Image(file=BytesIO(r.content))
    except Exception:
        raise InvalidImageError
    return im


def check_s3_object_exists(url):
    s = requests.Session()
    s.mount('https://', HTTPAdapter(max_retries=retries))
    try:
        r = s.head(url, timeout=1.0)
        t = r.elapsed.total_seconds()
        logging.info('S3 HEAD request time: %0.2f', t)
        r.raise_for_status()
    except requests.HTTPError as e:
        if e.response.status_code in (404, 403):
            return False
        else:
            raise
    return True


def upload_file(bucket_name: str, s3_config: S3ConnectionConfig, file: typing.BinaryIO, new_filename: str) -> str:
    """
    uploads file to s3 bucket under prism-images folder
    """

    conn = get_s3_client(s3_config)

    bucket = conn.get_bucket(bucket_name)

    extension = new_filename.rsplit('.', 1)[-1].lower()

    k = Key(bucket)
    k.key = new_filename
    k.content_type = 'image/%s' % extension
    k.set_contents_from_file(file, policy='public-read')

    s3_path = k.generate_url(expires_in=0, query_auth=False, force_http=True)
    if '?' in s3_path:
        # strip http auth stuff in url if any
        # we just upload public stuff
        s3_path = s3_path.split('?')[0]

    return s3_path
