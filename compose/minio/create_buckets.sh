#!/bin/sh

set -o errexit
set -o nounset

# Get the list of buckets to create from CLI arguments
BUCKETS=${1+"$@"}

mc config host add local ${S3_ENDPOINT_URL} ${AWS_ACCESS_KEY_ID} ${AWS_SECRET_ACCESS_KEY}
for BUCKET in ${BUCKETS}; do
    echo "Creating bucket ${BUCKET}..."
    mc rm -r --force local/${BUCKET} | true
    mc mb -p local/${BUCKET}
    # mc policy set download local/${BUCKET}
    # mc policy set public local/${BUCKET}
    mc anonymous set upload local/${BUCKET}
    mc anonymous set download local/${BUCKET}
    mc anonymous set public local/${BUCKET}
done
