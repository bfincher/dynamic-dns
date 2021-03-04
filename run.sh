#!/bin/bash

docker run -d \
-p 53:53/udp \
-v /var/run/docker.sock:/var/run/docker.sock:ro \
--name dynamic-dns \
--network frontend \
--restart unless-stopped \
--log-opt max-size=10m \
--log-opt max-file=5 \
bfincher/dynamic-dns
