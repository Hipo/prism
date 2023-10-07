import os
import json
import unittest
import urllib.parse

from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from prism.app import get_dimensions, get_output_format, get_command, make_retina, convert_filters_to_json, get_opacity
from prism.app import App, CredentialsStore, Customer
from prism.core import upload_file, S3ConnectionConfig
from prism import settings


def make_image_request(subdomain: str, path: str, query_args: dict) -> Request:
    """
    Create a mock Request object for testing.
    """
    query_string = urllib.parse.urlencode(query_args)
    base_url = f"http://{subdomain}.{settings.DOMAIN}"
    builder = EnvironBuilder(method="GET", base_url=base_url, path=path, query_string=query_string)
    env = builder.get_environ()
    request = Request(env)
    return request


TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOMER_NAMES = list(json.load(open(os.path.join(TESTS_DIR, 'config/test_credentials.json'))).keys())
TEST_SECRETS_BUCKET = os.environ['TEST_SECRETS_BUCKET']


def upload_credentials():
    config = S3ConnectionConfig()
    config_path = os.path.join(TESTS_DIR, 'config/test_credentials.json')
    with open(config_path, 'rb') as f:
        upload_file(TEST_SECRETS_BUCKET, config, f, 'credentials.json')


def upload_source_images(customer: Customer):

    image_source_config = S3ConnectionConfig(
        key_id=customer.read_bucket_key_id,
        secret_key=customer.read_bucket_secret_key,
        region=customer.read_bucket_region,
        endpoint_url=customer.read_bucket_endpoint_url,
    )
    assert customer.read_bucket_name, 'Customer read_bucket_name is not set'

    test_images_path = os.path.join(TESTS_DIR, 'images')
    test_images = os.listdir(test_images_path)
    for image_fname in test_images:
        with open(os.path.join(test_images_path, image_fname), 'rb') as f:
            upload_file(customer.read_bucket_name, image_source_config, f, image_fname)
    return test_images


class TestApp(unittest.TestCase):
    def setUp(self):
        upload_credentials()
        self.credentials_store = CredentialsStore(bucket=TEST_SECRETS_BUCKET, default_customer=CUSTOMER_NAMES[0])
        for customer_name in CUSTOMER_NAMES:
            self.test_images = upload_source_images(self.credentials_store.get_customer(customer_name))

    def test_main(self):
        app = App(credentials_store=self.credentials_store)

        for customer_name in CUSTOMER_NAMES:
            for image_fname in self.test_images:
                request = make_image_request(
                    subdomain=customer_name,
                    path=f"{image_fname}",
                    query_args={
                        "w": 100,
                        "h": 100
                    }
                )
                print("Request:", request)
                resp = app.main(request)
                print("Response:", resp, resp.headers)
                assert resp.status_code == 302


class TestGetCommand(unittest.TestCase):
    def test_values(self):
        self.assertEqual(get_command({'cmd': 'resize_then_fit'}), 'resize_then_fit')
        self.assertRaises(Exception, get_command, {'cmd': ''})


class TestGetDimensions(unittest.TestCase):
    def test_dimensions(self):
        self.assertEqual(get_dimensions({'height': 200, 'width': 200}, 'resize'), (200, 200))
        self.assertEqual(get_dimensions({'height': 200, 'width': 200}, 'resize_then_crop'), (200, 200))

    def test_values(self):
        self.assertRaises(Exception, get_dimensions, {}, 'resize')
        self.assertRaises(Exception, get_dimensions, {'height': 200}, 'resize_then_crop')
        self.assertRaises(Exception, get_dimensions, {'width': 200}, 'resize_then_crop')
        self.assertRaises(Exception, get_dimensions, {'height': 10001, 'width': 10001}, 'resize')
        self.assertEqual(get_dimensions({'height': 4001, 'width': 4001}, 'resize'), (4001, 4001))
        self.assertRaises(Exception, get_dimensions, {'height': 4001, 'width': 4001, 'premultiplied': True}, 'resize')
        self.assertRaises(Exception, get_dimensions, {'height': '', 'width': ''}, 'resize')


class TestGetOutputFormat(unittest.TestCase):
    def test_values(self):
        self.assertEqual(get_output_format('jpg', 'resize_then_fit', {}, {}), 'png')
        self.assertEqual(get_output_format('jpg', 'resize', {'out': 'png'}, {}), 'png')
        self.assertEqual(get_output_format('jpg', 'resize', {}, {}), 'jpg')
        self.assertEqual(get_output_format('jpg', 'resize', {}, {'image/webp'}), 'webp')
        self.assertRaises(Exception, get_output_format, 'jpg', 'resize', {'out': 'rar'}, {})


class TestMakeRetina(unittest.TestCase):
    def test_values(self):
        self.assertEqual(make_retina(100, 100, 2), (200, 200))
        self.assertEqual(make_retina(None, 100, 2), (None, 200))
        self.assertEqual(make_retina(100, None, 2), (200, None))


class TestConvertFiltersToJson(unittest.TestCase):
    def test_values(self):
        self.assertEqual(convert_filters_to_json({'filters': '["foo", {"bar":["baz", null, 1.0, 2]}]'}), ["foo", {"bar": ["baz", None, 1.0, 2]}])
        self.assertRaises(Exception, convert_filters_to_json, {'filters': '["foo", "bar":["baz", null, 1.0, 2]}]'})


class TestGetOpacity(unittest.TestCase):
    def test_values(self):
        self.assertEqual(get_opacity('resize', {'out': 'png'}), 100)
        self.assertEqual(get_opacity('resize', {'out': 'jpg'}), 0)
        self.assertEqual(get_opacity('resize_then_crop', {'out': 'png'}), 0)
