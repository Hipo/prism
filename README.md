# Prism - the image transformation service from Hipo


[![Docker Image Version](https://img.shields.io/docker/v/hipolabs/prism?label=hipolabs%2Fprism)](https://hub.docker.com/r/hipolabs/prism 'DockerHub')

## How It Works
Prism is an image transformation proxy for AWS S3. The source image is determined from the URL path. The transformation is determined from the URL query parameters. The transformed image is uploaded to S3 and a HTTP 302 Redirect response is returned pointing to the new image. Subsequent requests for the same image with the same parameters return the same S3 redirect without reprocessing the image.

![Prism Flow Diagram](flow.png)

### Example request:
http://prism-dev.tryprism.com -> This is the live server domain.

URL: `https://prism-dev.tryprism.com/images/test-1.jpg?h=200`  
Image file: `images/test-1.jpg`  
Parameters: `h=200`

Response Redirect Location: `https://s3.amazonaws.com/tryprism-dev/prism-images/images/test-1.jpg--resize--h__200.jpg`


### Usage

#### Set width
`http://prism-dev.tryprism.com/images/test-1.jpg?w=100`  
![ ](http://prism-dev.tryprism.com/images/test-1.jpg?w=100)

#### Set height 
`http://prism-dev.tryprism.com/images/test-1.jpg?h=100`  
![ ](http://prism-dev.tryprism.com/images/test-1.jpg?h=100)

#### Set output format 
`http://prism-dev.tryprism.com/images/test-1.jpg?h=100&out=png`  
out options are `jpg`, `png`, `webp`.  
If no option is specified and the client accepts webp then webp will be used by default)  
![ ](http://prism-dev.tryprism.com/images/test-1.jpg?h=100&out=png)

#### Pad image to fit the exact dimensions specified
`http://prism-dev.tryprism.com/images/test-1.jpg?cmd=resize_then_fit&w=100&h=100`  
![ ](http://prism-dev.tryprism.com/images/test-1.jpg?cmd=resize_then_fit&w=100&h=100)

#### Pad image to fit the exact dimensions specified, with background color specified
`http://prism-dev.tryprism.com/images/test-1.jpg?cmd=resize_then_fit&w=100&h=100&frame_bg_color=000`  
![ ](http://prism-dev.tryprism.com/images/test-1.jpg?cmd=resize_then_fit&w=100&h=100&frame_bg_color=000)

#### Resize and crop to dimensions
`http://prism-dev.tryprism.com/images/test-1.jpg?cmd=resize_then_crop&w=100&h=100`  
![ ](http://prism-dev.tryprism.com/images/test-1.jpg?cmd=resize_then_crop&w=100&h=100)

#### Crop first and resize to dimensions
`http://prism-dev.tryprism.com/images/test-1.jpg?cmd=resize&w=100&h=100&crop_x=0&crop_y=0&crop_width=200&crop_height=200`  
(crop_* parameters are relative to original image dimensions)  
![ ](http://prism-dev.tryprism.com/images/test-1.jpg?cmd=resize&w=100&h=100&crop_x=0&crop_y=0&crop_width=200&crop_height=200)





## Configuration
Prism has two different modes of operation; Single Customer Mode and Multi Customer Mode.

### Single Customer Mode (default)
In Single Customer Mode Prism reads and writes to a single S3 bucket. Use this mode when serving images for a single project.

Required Environment Variables:
* DOMAIN [`images.myproject.com`]
* S3_BUCKET [`myproject-images`]
* TEST_IMAGE [`images/test-1.jpg`]
* AWS_REGION [`us-east-1`]
* AWS_ACCESS_KEY_ID (The access key must provide read & write access to the `S3_BUCKET` (and `S3_WRITE_BUCKET` if provided).
* AWS_SECRET_ACCESS_KEY

Optional Environment Variables:
* S3_WRITE_BUCKET [`myproject-prism-images`] (If not provided, default is `S3_BUCKET`.)
* S3_ENDPOINT_URL (If using a non-AWS implementation of S3 like OpenStack, DigitalOcean, etc)

### Multi Customer Mode
In Multi Customer Mode Prism can handle requests for multiple customers together, where each customer has a separate S3 bucket and separate credentials. The customers are separated by subdomain. The configuration and credentials for each subdomain are loaded from a `credentials.json` stored in the SECRETS_BUCKET. 

Required Environment Variables:
* MULTI_CUSTOMER_MODE=true
* DOMAIN [`tryprism.com`]
* SECRETS_BUCKET [`super-secret-private-bucket`]
* DEFAULT_CUSTOMER (for tests) [`prism-test`]
* TEST_IMAGE [`images/test-1.jpg`]
* AWS_REGION (for the SECRETS_BUCKET) [`us-east-1`]
* AWS_ACCESS_KEY_ID (for the SECRETS_BUCKET)
* AWS_SECRET_ACCESS_KEY (for the SECRETS_BUCKET)


#### Example credentials.json
This JSON file maps subdomains to customer credentials.

WARNING: This file must not be publicly accessible!

```
{
    "foo": {
        "read_bucket_name": "foo-production",
        "read_bucket_region": "us-east-1",
        "read_bucket_key_id": "AKIABLABLA...",
        "read_bucket_secret_key": "XFiefjlfkjgls....",
    },
    "bar": {
        "read_bucket_name": "bar-images",
        "read_bucket_region": "eu-west-1",
        "read_bucket_key_id": "AKIAKABC...",
        "read_bucket_secret_key": "SNf1jJf2ffD....",
    },
}
```

Note: `write_bucket_*` parameters may be included to separate read and write buckets.

### TEST_IMAGE
The TEST_IMAGE setting is used to provide an image to be used for the test and health check endpoints. In multi customer mode the DEFAULT_CUSTOMER setting must also be set for the test endpoints to work.

### uWSGI Configuration

The Prism app runs under uWSGI. By default, it runs with 2 processes and 2 threads per process. These settings can be overridden using the UWSGI_PROCESSES and UWSGI_THREADS environment variables. Similarly, other options can be passed to uWSGI using UWSGI_* environment variables.


## Deployment
The Docker container runs a uwsgi process with a HTTP socket (port 8000) and a uwsgi socket (port 3001). For local development and testing connecting to the HTTP server is sufficient. For production use it is recommended to use Nginx in front of uwsgi. A sample Nginx configuration including caching setup is included here: [nginx-sample.conf](nginx-sample.conf)

To run docker container use following command:

`docker-compose -f docker-compose.yml -f docker-compose.development.yml up`

The `8000` port of the container is mapped to the `8001` port of the host. Use `localhost:8001` to access the app.

`http://localhost:8001/test`. This test url runs the same command both on your local and the live Prism server, and provides comparisons between local and live prism server image resizing operations. 

