FROM python:3.8

# Development
RUN apt-get update
RUN apt-get install webp -y
# This specific version of ImageMagick is required for compatibility with Wand
RUN wget https://www.imagemagick.org/download/releases/ImageMagick-6.9.10-90.tar.xz && \
tar -xvf ImageMagick-6.9.10-90.tar.xz && \
cd ImageMagick-6.9.10-90 && \
./configure --with-webp=yes && \
make && \
make install && \
ldconfig /usr/local/lib

RUN pip install uwsgi uwsgitop

WORKDIR /prism
COPY requirements.txt ./
RUN pip install -U pip && pip install -r requirements.txt
COPY prism.uwsgi.ini ./
COPY prism ./prism/

# Expose HTTP port
EXPOSE 8000
# Expose uwsgi port
EXPOSE 3001

# These uwsgi options are set here as environment variables so they can be overridden later
ENV UWSGI_PROCESSES=2
ENV UWSGI_THREADS=2

CMD ["uwsgi", "prism.uwsgi.ini"] 
