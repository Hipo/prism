import json
import os.path
import glob
import time
import datetime
import logging
import sentry_sdk
from sentry_sdk.integrations.wsgi import SentryWsgiMiddleware
from werkzeug.wrappers import Request, Response
from werkzeug.routing import Map, Rule
from werkzeug.exceptions import HTTPException, NotFound, BadRequest
from werkzeug.utils import redirect
from werkzeug.contrib.fixers import ProxyFix
from requests import HTTPError
from boto.s3.key import Key
from boto import connect_s3

import prism.core as core
import prism.settings as settings


logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

sentry_sdk.init()  # uses SENTRY_DSN env var


class App(object):

    def __init__(self, credentials_store):
        self.url_map = Map([
            Rule('/', endpoint='index'),
            Rule('/elb-health/', endpoint='elb_health_check'),
            Rule('/test/', endpoint='test'),
            Rule('/test/info', endpoint='test_info'),
            Rule('/test/resize', endpoint='test_resize'),
            Rule('/favicon.ico', endpoint='not_found'),
            Rule('/robots.txt', endpoint='not_found'),
            Rule('/setdpr/<dpr>', endpoint='set_dpr'),
        ])
        self.credentials_store = credentials_store

    def dispatch_request(self, request):
        adapter = self.url_map.bind_to_environ(request.environ)
        try:
            try:
                endpoint, values = adapter.match()
            except NotFound:
                endpoint = 'main'
                values = {}
            return getattr(self, endpoint)(request, **values)
        except HTTPException as e:
            return e

    def get_customer(self, request):
        subdomain = request.args.get('customer', None)
        if subdomain is None:
            subdomain = request.host.split('.' + settings.DOMAIN)[0]
        with sentry_sdk.configure_scope() as scope:
            scope.set_tag("customer", subdomain)
        customer = self.credentials_store.get_customer(subdomain)
        return customer

    def main(self, request):
        path = request.path[1:]
        _, extension = os.path.splitext(path.lower())
        if extension not in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
            raise NotFound()
        try:
            args = parse_args(path, request)
        except Exception as e:
            raise BadRequest(e)

        customer = self.get_customer(request)
        if extension == '.gif' and request.args.get('out', 'gif') == 'gif':
            s3_url = core.get_s3_url(customer.read_bucket_name, customer.read_bucket_region, path)
            if core.check_s3_object_exists(s3_url):
                return redirect(s3_url)
            raise NotFound()

        if args['command'] == 'info':
            return info(path, args, customer)
        else:
            return process(path, args, customer)

    def index(self, request):
        return Response('Coming Soon')

    def not_found(self, request):
        raise NotFound()

    def test(self, request):
        return Response(open('prism/static/test.html'), content_type='text/html')

    def elb_health_check(self, request):
        # If HTTPError occurs or can't find the given image gives Response as 500
        customer = self.credentials_store.get_default_customer()
        path = settings.TEST_IMAGE
        url = core.get_s3_url(customer.read_bucket_name, customer.read_bucket_region, path)
        try:
            if core.check_s3_object_exists(url):
                return Response("OK")
        except HTTPError:
            pass
        return Response(status=500)

    def test_info(self, request):
        customer = self.credentials_store.get_default_customer()
        return info(settings.TEST_IMAGE, None, customer)

    def test_resize(self, request):
        customer = self.credentials_store.get_default_customer()
        args = {
            'command': 'resize',
            'options': {
                'w': 200,
                'h': 200,
                'q': 95,
                'out_format': 'jpg',
                'premultiplied_alpha': None,
            },
            'no_redirect': True,
            'debug': True,
        }
        return process(settings.TEST_IMAGE, args, customer)

    def set_dpr(self, request, dpr):
        expires = datetime.datetime.utcnow() + datetime.timedelta(days=365)
        response = Response('var prism_dpr_set=%s;' % dpr, content_type='application/javascript')
        response.set_cookie('dpr', dpr, expires=expires)
        return response

    def wsgi_app(self, environ, start_response):
        request = Request(environ)
        response = self.dispatch_request(request)
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)


def info(path, args, customer):
    url = core.get_s3_url(customer.read_bucket_name, customer.read_bucket_region, path)
    try:
        im = core.fetch_image(url)
    except HTTPError as e:
        if e.response.status_code in (404, 403):
            raise NotFound()
        else:
            raise
    info = core.info(im)
    return json_response(info)


def fetch_image(original_url):
    try:
        return core.fetch_image(original_url)
    except HTTPError as e:
        if e.response.status_code in (404, 403):
            raise NotFound()
        else:
            raise
    except core.EmptyOriginalFile as e:
        raise BadRequest(e.message)
    except core.InvalidImageError as e:
        raise BadRequest(e.message)


def process(path, args, customer):
    cmd = args['command']
    options = args['options']
    original_url = core.get_s3_url(customer.read_bucket_name, customer.read_bucket_region, path)
    if args['debug']:
        im = core.fetch_image(original_url)
        f = core.resize(im, cmd, options)
        r = Response(f, mimetype='image/jpeg')
        return r
    result_path = core.get_thumb_filename(path, cmd, options)
    result_url = core.get_s3_url(customer.write_bucket_name, customer.write_bucket_region, result_path)
    exists = core.check_s3_object_exists(result_url)
    if args['with_info'] or args['force'] or not exists:
        clear_old_tmp_files()
        im = fetch_image(args=args, original_url=original_url, exists=exists)
        f = core.resize(im.clone(), cmd, options)
        bucket = dict(
            id=customer.write_bucket_name,
            key_id=customer.write_bucket_key_id,
            region=customer.write_bucket_region,
            secret_key=customer.write_bucket_secret_key,
        )
        core.upload_file(bucket, f, result_path)
        if args['with_info']:
            info = core.info(im)
            info['url'] = result_url
            return json_response(info)
    if args['no_redirect']:
        r = Response()
        # Tell nginx to serve the url for us
        # https://www.nginx.com/resources/wiki/start/topics/examples/x-accel/#x-accel-redirect
        r.headers['X-Accel-Redirect'] = '/s3/' + result_url.split('https://')[1]
        return r
    else:
        return redirect(result_url)


def make_bool(x):
    if x.lower() in ('false', '0'):
        return False
    else:
        return True


def int_or_none(x):
    if x is None:
        return None
    else:
        return int(x)


def get_command(args):
    commands = ('resize',
                'resize_then_crop',
                'resize_then_fit',
                'info',
                'smart_crop',
                'requeue',
                'invalidate')

    command = args.get('cmd', 'resize')
    if command not in commands:
        raise Exception('Error: parameter is wrong - command')
    return command


def get_dimensions(args, command):
    max_dimension = 10000
    if args.get('premultiplied'):
        # We use a smaller max_dimension in this case because convert_to_premultiplied_png needs to make an in-memory copy
        max_dimension = 4000
    width = args.get('w', args.get('width', None))
    height = args.get('h', args.get('height', None))
    if width:
        try:
            width = int(width)
        except Exception:
            raise Exception('width or height is not an integer')
        if width > max_dimension:
            raise Exception(f'width should be < {max_dimension}')

    if height:
        try:
            height = int(height)
        except Exception:
            raise Exception('width or height is not an integer')
        if height > max_dimension:
            raise Exception(f'height should be < {max_dimension}')

    if command == 'resize':
        if not (width or height):
            raise Exception('width or height is required')
    elif command in ('resize_then_crop', 'resize_then_fit'):
        if not (width and height):
            raise Exception('width and height is required')
    return width, height


def get_output_format(default_out_format, command, args, accepted_formats):
    if command == 'resize_then_fit':
        default_out_format = 'png'
    if 'out' in args and args['out']:
        out_format = args['out'].lower()
        if out_format not in ('jpg', 'jpeg', 'png', 'webp'):
            raise Exception('Error 111 - image format should be jpg, png or webp: %s' % out_format)
    elif 'image/webp' in accepted_formats:
        # we only force webp if the browser supports it && the url doesn't specify an out format
        out_format = 'webp'
    else:
        out_format = default_out_format
    return out_format


def make_retina(width, height, dpr):
    if width:
        width = int(dpr * float(width))
    if height:
        height = int(dpr * float(height))
    return width, height


def convert_filters_to_json(args):
    filters = args.get('filters', None)
    if filters:
        # we need filter as json data, because every filter can have N parameters.
        try:
            filters = json.loads(filters)
        except Exception:
            raise Exception("Error 108 - couldn't decode json")
    return filters


def get_opacity(command, args):
    default_opacity = 100
    # this is to replicate a bug in the original version
    # opacity argument is ignored
    if command == 'resize_then_crop' or args.get('out') == 'jpg':
        default_opacity = 0
    # options['opacity'] = args.get('opacity', default_opacity)
    return default_opacity


def parse_args(path, request):
    args = request.args
    new_args = {}
    options = {}

    _, extension = os.path.splitext(path)

    command = get_command(args=args)
    options['resize_then_crop'] = int(args.get('resize_then_crop', '0'))
    if options['resize_then_crop']:
        command = 'resize_then_crop'

    width, height = get_dimensions(args=args, command=command)

    retina = make_bool(args.get('retina', 'false'))
    if retina and 'dpr' in request.cookies:
        width, height = make_retina(width, height, request.cookies['dpr'])

    options['w'] = width
    options['h'] = height
    options['preserve_ratio'] = make_bool(args.get('preserve_ratio', 'true'))
    options['crop_x'] = args.get('crop_x', None)
    options['crop_y'] = args.get('crop_y', None)
    options['crop_width'] = args.get('crop_width', None)
    options['crop_height'] = args.get('crop_height', None)
    options['frame_bg_color'] = args.get('frame_bg_color', 'FFF')
    options['gravity'] = args.get('gravity', 'center')
    options['premultiplied_alpha'] = args.get('premultiplied', None)
    options['q'] = int(args.get('quality', '95'))
    options['opacity'] = get_opacity(command=command, args=args, )
    options['filters'] = convert_filters_to_json(args=args)
    options['out_format'] = get_output_format(default_out_format=extension[1:],
                                              command=command,
                                              args=args,
                                              accepted_formats=request.headers.get('accept', ''))

    new_args['options'] = options
    new_args['command'] = command
    new_args['with_info'] = args.get('with_info', False)
    new_args['no_redirect'] = make_bool(args.get('no_redirect', '0'))
    new_args['debug'] = make_bool(args.get('debug', '0'))
    new_args['force'] = make_bool(args.get('force', '0'))
    return new_args


def json_response(data):
    return Response(json.dumps(data), content_type='application/json')


def clear_old_tmp_files():
    tmp_files = glob.glob('/tmp/magick-*')
    now = time.time()
    for tmp_file in tmp_files:
        try:
            if os.stat(tmp_file).st_mtime < now - 300:
                os.remove(tmp_file)
        except Exception:
            # An error might occur if the file has already been deleted by another process. We don't care.
            pass


class Customer(object):
    def __init__(self,
                 read_bucket_name=None,
                 read_bucket_key_id=None,
                 read_bucket_secret_key=None,
                 read_bucket_region=None,
                 write_bucket_name=None,
                 write_bucket_key_id=None,
                 write_bucket_secret_key=None,
                 write_bucket_region=None,
                 **kwargs):
        self.read_bucket_name = read_bucket_name
        self.read_bucket_key_id = read_bucket_key_id
        self.read_bucket_secret_key = read_bucket_secret_key
        self.read_bucket_region = read_bucket_region
        self.write_bucket_name = write_bucket_name or read_bucket_name
        self.write_bucket_key_id = write_bucket_key_id or read_bucket_key_id
        self.write_bucket_secret_key = write_bucket_secret_key or read_bucket_secret_key
        self.write_bucket_region = write_bucket_region or read_bucket_region


class CredentialsStore(object):
    def __init__(self, bucket, default_customer):
        self.bucket_name = bucket
        self.default_customer = default_customer
        self.customers_credentials = {}
        self.expiration_time = None

    def _get_credentials(self):
        if not self.customers_credentials or self.expiration_time < datetime.datetime.now():
            logger.info('Loading credentials from %s', self.bucket_name)
            # Get the credentials from the private secrets bucket.
            # Boto authenticates using the IAM role assigned to the ec2 instances.
            try:
                s3 = connect_s3()
                bucket = s3.get_bucket(self.bucket_name, validate=False)
                k = Key(bucket, 'credentials.json')
                self.customers_credentials = json.loads(k.get_contents_as_string())
                self.expiration_time = datetime.datetime.now() + datetime.timedelta(minutes=5)
            except Exception:
                logger.exception("Exception while getting customer credentials")
                sentry_sdk.capture_exception()
                # if we have a stale data continue to use it
                # s3 may be unavailable or the new credentials may be unparsable
                # so we extend the timeout by a minute instead of continuously requesting
                # and waiting on every request
                if self.customers_credentials:
                    self.expiration_time += datetime.timedelta(minutes=1)
                    return self.customers_credentials
        return self.customers_credentials

    def get_customer(self, customer_key):
        credentials = self._get_credentials()[customer_key]
        return Customer(**credentials)

    def get_default_customer(self):
        return self.get_customer(self.default_customer)


class SingleCustomerCredentialsStore(object):
    def __init__(self, credentials, default_customer=None):
        self.credentials = credentials

    def get_customer(self, customer_key):
        return Customer(**self.credentials)

    def get_default_customer(self):
        return self.get_customer(None)


if settings.MULTI_CUSTOMER_MODE:
    credentials_store = CredentialsStore(bucket=settings.SECRETS_BUCKET, default_customer=settings.DEFAULT_CUSTOMER)
elif settings.S3_BUCKET:
    credentials_store = SingleCustomerCredentialsStore({
            "read_bucket_name": settings.S3_BUCKET,
            "read_bucket_region": settings.AWS_REGION,
            "read_bucket_key_id": settings.AWS_ACCESS_KEY_ID,
            "read_bucket_secret_key": settings.AWS_SECRET_ACCESS_KEY,
            "write_bucket_name": settings.S3_WRITE_BUCKET or settings.S3_BUCKET,
        })
else:
    raise Exception('S3_BUCKET must be set if MULTI_CUSTOMER_MODE is not true')

app = App(credentials_store=credentials_store)
app = SentryWsgiMiddleware(app)
# ProxyFix reads the X-Forwarded-* headers set by proxies (like ELB)
# and updates the request so things like request.scheme is correct.
app = ProxyFix(app)
