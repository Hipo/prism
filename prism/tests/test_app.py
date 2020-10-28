import unittest

from prism.app import get_dimensions, get_output_format, get_command, make_retina, convert_filters_to_json, get_opacity


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
