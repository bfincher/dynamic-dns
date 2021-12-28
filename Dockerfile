from bfincher/alpine-python3:3.15 

env PYTHONBUFFERED 1

workdir /app

copy requirements.txt /app
run apk add --no-cache dnsmasq && \
    pip3 install -r requirements.txt && \
    mkdir -p /run/nginx/

copy root/ /

env HOSTS_DIR=/app/hosts 

EXPOSE 53/udp
