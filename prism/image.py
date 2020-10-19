from io import BytesIO
from wand.image import Image
from wand.color import Color
from PIL import Image as Img
import numpy
import logging

logger = logging.getLogger(__name__)


class ImageOperator(object):
    def __init__(self, image):
        self.image = image
        self.image.auto_orient()
        self.width, self.height = self.image.size
        self.filename = None

    @property
    def is_portrait(self):
        return self.width > self.height

    def resize_then_crop(self, geometry, preserve_ratio=True, gravity='center', **options):
        try:
            options.pop('resize_then_crop')
        except:
            pass
        return self.resize(geometry=geometry,
                           preserve_ratio=preserve_ratio,
                           resize_then_crop=True,
                           gravity=gravity,
                           **options
                           )

    def resize_then_fit(self, geometry, preserve_ratio=True, gravity='center', **options):
        try:
            options.pop('resize_then_fit')
        except:
            pass
        return self.resize(geometry=geometry,
                           preserve_ratio=preserve_ratio,
                           resize_then_fit=True,
                           gravity=gravity,
                           **options
                           )

    def hex_to_int(self, color_string):
        """
        #FFFFFFF returns as (255, 255, 255)
        FFFFFF returns as (255, 255, 255)

        :param color_string:
        :return:
        """
        cs = color_string.replace('#', '')
        if len(cs) == 3:
            return (
                int('%s%s' % (cs[0], cs[0]), base=16),
                int('%s%s' % (cs[1], cs[1]), base=16),
                int('%s%s' % (cs[2], cs[2]), base=16),
            )

        return (
            int('%s' % cs[0:2], base=16),
            int('%s' % cs[2:4], base=16),
            int('%s' % cs[4:6], base=16),
        )

    def fit_frame(self, background_color, width, height, opacity=100,
                  placement='center',
                  composite_x=0, composite_y=0, compression_quality=95):
        if placement == 'center':
            composite_x = int((width - self.image.width) / 2)
            composite_y = int((height - self.image.height) / 2)

        color_rgb = self.hex_to_int(background_color)
        transp = 1 - opacity / 100.0
        color_rgba_string = 'rgba(%s, %s, %s, %s)' % (color_rgb[0], color_rgb[1], color_rgb[2], transp)
        print("color_rgba", color_rgba_string)
        color = Color(color_rgba_string)
        cover = Image(width=width, height=height, background=color)
        for k in self.image.profiles:
            value = self.image.profiles[k]
            if value is not None:
                cover.profiles[k] = value
        cover.composite(self.image, composite_x, composite_y)
        self.image = cover
        self.image.compression_quality = compression_quality

    # this is a filter
    def translucent(self, background_color, opacity=20,
                    radius=10, sigma=10,
                    composite_width=None, composite_height=None,
                    composite_x=0, composite_y=0):

        if not composite_width:
            composite_width = self.image.width
        if not composite_height:
            composite_height = self.image.height

        color_rgb = self.hex_to_int(background_color)
        transp = 1 - opacity / 100.0
        color_rgba_string = 'rgba(%s, %s, %s, %s)' % (color_rgb[0], color_rgb[1], color_rgb[2], transp)
        color = Color(color_rgba_string)
        cover = Image(width=composite_width,
                      height=composite_height,
                      background=color)
        self.image.gaussian_blur(radius, sigma)
        self.image.composite(cover, composite_x, composite_y)

    def unsharp_mask(self, radius=9, sigma=0.75, amount=0.75, threshold=0.008):
        self.unsharp_mask(radius=radius, sigma=sigma, amount=amount, threshold=threshold)

    def resize(self, geometry,
               preserve_ratio=True,
               resize_then_crop=False,
               resize_then_fit=False,
               crop_x=0, crop_y=0, crop_width=0, crop_height=0,
               frame_bg_color='FFF', opacity=100,
               **options):
        """

        resizes the image

        :param geometry: (x,y) tuple, can be (x,) or (,y)
        :param gravity: can be one of (center, top_left) if both resize dimensions are given,
                        and resize_then_crop option is set, we'll crop it according to gravity
                        (from topleft or center)

                        Note, wand/magick doesn't honour gravity, so we calculate it by hand,
                        maybe because of magick version not sure.
        :param resize_then_crop: if false and both wanted width and height given,
                                 we resize it preserving aspect ratio - if not preserve_ratio -
                                 eg.
                                 resize((400,200)) will resize 1300,944 image to, (262, 200)
                                 resize((400,400)) will resize 1300,944 image to, (400, 306)
                                 for more information one should check imagemagick documentation
                                 if true, for portraits (y>x) we resize to wanted height, then crop to
                                 desired geometry

        :param preserve_ratio: we resize to given width and height without preserving ratio


        """
        wanted_width = geometry[0]
        wanted_height = geometry[1]
        if wanted_width:
            assert int(wanted_width) < 10000
        if wanted_height:
            assert int(wanted_height) < 10000

        x_offset = 0
        y_offset = 0

        gravity = 'top_left'
        if 'gravity' in options and options['gravity']:
            gravity = options['gravity']

        assert gravity in ('center', 'top_left', 'smart')
        use_smart_crop = gravity == 'smart'

        try:
            self.image.auto_orient()
        except:
            pass

        if wanted_width and wanted_height:

            if resize_then_crop:
                center_x, center_y = None, None
                org_w, org_h = self.image.width, self.image.height
                if use_smart_crop:
                    from smartcrop import point_of_interest
                    center_x, center_y = point_of_interest(self.filename)

                if self.height < wanted_height and self.width < wanted_width:
                    # this is upscaling
                    logging.info("we are upscaling")

                    """
                        590 x 393
                        720
                    """
                    # calc from width
                    next_height = wanted_width * (self.height / float(self.width))
                    if next_height >= wanted_height:
                        logging.debug("next height w:%s h:%s ", next_height, wanted_width)
                        self.image.transform(resize="%sx" % wanted_width)
                    else:
                        logging.debug("next height -2- w:%s h:%s ", next_height, wanted_width)
                        self.image.transform(resize="x%s" % wanted_height)

                    # self.image.unsharp_mask(radius=10, sigma=4, amount=1.0, threshold=0)

                else:
                    logger.info("we are downscaling")
                    ratio = self.width / float(self.height)
                    logger.debug("ratio: %0.2f", ratio)
                    new_width = wanted_height * ratio
                    new_height = wanted_width / ratio
                    logger.debug("New width if scale by height: %s (%s wanted)", new_width, wanted_width)
                    logger.debug("New height if scale by width: %s (%s wanted)", new_height, wanted_height)
                    if new_height >= wanted_height:
                        logger.debug("Scaling by width")
                        thumbnail_width = wanted_width
                        thumbnail_height = new_height
                    else:
                        logger.debug("Scaling by height")
                        thumbnail_height = wanted_height
                        thumbnail_width = new_width
                    thumbnail_width = int(round(thumbnail_width))
                    thumbnail_height = int(round(thumbnail_height))
                    logger.debug('%ix%i', thumbnail_width, thumbnail_height)
                    self.image.transform(resize="%ix%i" % (thumbnail_width, thumbnail_height))

                thumbnail_width, thumbnail_height = self.image.size

                logger.debug("thumbnail_width, thumbnail_height: %s, %s", thumbnail_width, thumbnail_height)

                if thumbnail_width > wanted_width:
                    if not center_x:
                        x_offset = int((thumbnail_width - wanted_width) / 2)
                    else:
                        # center_x = center_x * float(thumbnail_width / self.image.width)
                        x_offset = center_x  # int(center_x - (wanted_width))

                if thumbnail_height > wanted_height:
                    if not center_y:
                        y_offset = int((thumbnail_height - wanted_height) / 2)
                    else:
                        # center_y = center_y * float(thumbnail_height / self.image.height)
                        y_offset = center_y  # int(center_y - (wanted_height))

                logger.info("image size: %s", self.image.size)
                logger.info("now we are cropping to %sx%s+%s+%s", wanted_width, wanted_height, x_offset, y_offset)

                if gravity == 'center':
                    self.image.transform(crop="%sx%s+%s+%s" % (wanted_width, wanted_height, x_offset, y_offset))
                elif gravity == 'smart':

                    # x was 76 when width was 620
                    # now width is 100
                    x_offset = (x_offset * float(self.image.width)) / float(org_w)
                    y_offset = (y_offset * float(self.image.height)) / float(org_h)
                    print("now x_offset", x_offset, y_offset)

                    left = int(x_offset - float(wanted_width / 2.0))
                    if left < 0:
                        left = 0
                    top = int(y_offset - float(wanted_height / 2.0))
                    if top < 0:
                        top = 0

                    right = left + wanted_width
                    bottom = top + wanted_height
                    if bottom >= self.image.height:
                        bottom = self.image.height
                    if right >= self.image.width:
                        right = self.image.width

                    debug = False
                    if debug:
                        from wand.drawing import Drawing
                        with Drawing() as draw:
                            draw.fill_color = Color('rgb(255, 255, 255)')
                            draw.circle((x_offset, y_offset), (50, 50))
                            # draw.rectangle(left=x_offset, top=y_offset, width=50, height=50)
                            # draw.rectangle(left=left, top=top, right=right, bottom=bottom)
                            draw(self.image)
                    self.image.crop(left=left, top=top, right=right, bottom=bottom)
                elif gravity == 'top_left':
                    self.image.transform(crop="%sx%s+%s+%s" % (wanted_width, wanted_height, 0, 0))

            elif crop_x and crop_y and crop_width and crop_height:
                self.image.transform(crop="%sx%s+%s+%s" % (crop_width, crop_height, crop_x, crop_y),
                                     resize="%sx%s" % (wanted_width, wanted_height))

                # -unsharp <radius>{x<sigma>}{+<amount>}{+<threshold>}
                # That is, a radius is expected (or a leading "x" if omitted),
                # followed by optional parameters sigma, amount and threshold.
                # [Note that there is also a -sharpen option to convert. This is not an alias for
                # -unsharp, and (I'm pretty sure) employs a different sharpening routine internally.]
                #
                # A typical call to convert might look something like the following:
                #
                # $ convert ... -unsharp 1.5x1.2+1.0+0.10 <input file> <output file>
                # http://redskiesatnight.com/2005/04/06/sharpening-using-image-magick/
                # disabling sharpening for now
                # self.image.unsharp_mask(radius=0, sigma=1.4, amount=1.0, threshold=0.10)

                # The post Image Resizing suggests using "-unsharp 0x0.75+0.75+0.008"
                # as being good for images larger than 500 pixels.
                # self.image.unsharp_mask(radius=0, sigma=0.75, amount=0.75, threshold=0.008)

            else:
                if preserve_ratio:
                    self.image.transform(resize="%sx%s" % (wanted_width, wanted_height))
                    # we do a sharpen
                    # -unsharp <radius>{x<sigma>}{+<amount>}{+<threshold>}
                    # now
                    # disabling sharpening now
                    # self.image.unsharp_mask(radius=0, sigma=1.4, amount=1.0, threshold=0.10)
                    # -unsharp 10x4+1+0
                    # 10x4
                    # self.image.unsharp_mask(radius=10, sigma=4, amount=1.0, threshold=0)

                    # 10x2
                    # self.image.unsharp_mask(radius=10, sigma=2, amount=1, threshold=0)

                    # amt-0.8.jpg
                    # self.image.unsharp_mask(radius=0, sigma=2, amount=1.2, threshold=0)

                    # sigma 2.4
                    # self.image.unsharp_mask(radius=0, sigma=2.4, amount=1.2, threshold=0)

                    # self.image.unsharp_mask(radius=0, sigma=2.4, amount=0.8, threshold=0)

                    # create a background image so we can blend better, this is needed for jpg output,
                    # if its already png we dont put a frame
                    color_rgb = self.hex_to_int('#%s' % frame_bg_color)
                    transp = 1 - (opacity / 100.0)
                    color_rgba_string = 'rgba(%s, %s, %s, %s)' % (color_rgb[0], color_rgb[1], color_rgb[2], transp)
                    color = Color(color_rgba_string)
                    cover = Image(width=self.image.width, height=self.image.height, background=color)
                    for k in self.image.profiles:
                        value = self.image.profiles[k]
                        if value is not None:
                            cover.profiles[k] = value
                    # now blend it
                    cover.composite(self.image, 0, 0)
                    self.image = cover
                else:
                    self.image.transform(resize="%s!x%s!" % (wanted_width, wanted_width))

        elif wanted_width:
            self.image.transform(resize="%sx" % wanted_width)

        elif wanted_height:
            self.image.transform(resize="x%s" % wanted_height)

        if resize_then_fit:
            self.fit_frame('#%s' % frame_bg_color,
                           width=wanted_width,
                           height=wanted_height,
                           opacity=opacity,
                           placement='center',
                           composite_x=0,
                           composite_y=0)

    def save(self, file_name, compression_quality=75):
        self.image.compression_quality = compression_quality
        # self.image.transparentize(0.5)
        logger.info(">>> compression quality: %s", self.image.compression_quality)
        logger.info(">>> file_name: %s", file_name)
        self.image.save(filename=file_name)

    def write(self, file, fmt=None):
        print('format: %s' % self.image.format)
        if fmt:
            self.image.format = fmt
        self.image.save(file=file)

    def save_premultiplied_png(self, file_name):
        """
        this should run after save() as i couldnt find a better way to load image to PIL

        http://stackoverflow.com/questions/6591361/method-for-converting-pngs-to-premultiplied-alpha

        :param file_name:
        :return:
        """
        logger.info("convert to premultiplied alpha RGBA - %s", file_name)

        logger.info("converting to premultiplied alpha")
        im = Img.open(file_name).convert('RGBA')
        a = numpy.fromstring(im.tostring(), dtype=numpy.uint8)
        alpha_layer = a[3::4] / 255.0
        a[::4] *= alpha_layer
        a[1::4] *= alpha_layer
        a[2::4] *= alpha_layer

        im = Img.fromstring("RGBA", im.size, a.tostring())
        im.save(file_name)

    def smart_crop(self, file_name, wanted_width, wanted_height, **kwargs):
        assert wanted_width < 10000
        assert wanted_height < 10000
        from smartcrop import point_of_interest
        logger.info("trying smartcrop - %s %s %s", file_name, wanted_width, wanted_height)
        try:
            self.image.auto_orient()
        except:
            pass
        # get center
        x, y = point_of_interest(file_name)
        left = int(x - float(wanted_width / 2.0))
        if left < 0:
            left = 0
        top = int(y - float(wanted_height / 2.0))
        if top < 0:
            top = 0
        width = int(wanted_width / 2.0)
        height = int(wanted_height / 2.0)

        right = left + wanted_width
        bottom = top + wanted_height
        if bottom >= self.image.height:
            bottom = self.image.height
        if right >= self.image.width:
            right = self.image.width

        print("cropping from", left, top, right, bottom)
        self.image.crop(left=left, top=top, right=right, bottom=bottom)


def convert_to_premultiplied_png(file):
    """
    http://stackoverflow.com/questions/6591361/method-for-converting-pngs-to-premultiplied-alpha

    """
    logger.info("converting to premultiplied alpha")
    im = Img.open(file).convert('RGBA')
    a = numpy.fromstring(im.tobytes(), dtype=numpy.uint8)
    a = a.astype(numpy.float64)
    alpha_layer = a[3::4] / 255.0
    a[::4] *= alpha_layer
    a[1::4] *= alpha_layer
    a[2::4] *= alpha_layer
    im = Img.frombytes("RGBA", im.size, a.astype(numpy.uint8).tostring())
    f = BytesIO()
    im.save(f, 'png')
    f.seek(0)
    return f


if __name__ == "__main__":
    import sys

    filename = sys.argv[1]
    img = Image(filename=filename)
    imop = ImageOperator(img)
    # imop.resize((500,None))
    # imop.resize((300,120), resize_then_crop=True)
    imop.resize_then_crop((600, 400))
    imop.save("out.png")
