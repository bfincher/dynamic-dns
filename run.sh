#!/bin/bash

docker run -d \
-p 53:53/udp \
-v /var/run/docker.sock:/var/run/docker.sock:ro \
--name dynamic-dns \
--network frontend \
--restart unless-stopped \
bfincher/dynamic-dns
