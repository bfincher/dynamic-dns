**Description**

The original thought process behind this project was to be a companion to jwilder's [nginx-proxy](https://github.com/nginx-proxy/nginx-proxy).  
One of the complaints about nginx-proxy is the fact that it requires virtual hosts.  For me, I needed to run a local DNS as I didn't
have the ability to create virtual hosts on my domain name.  This project will monitor running docker containers in a way similar to
nginx-proxy and create dnsmasq hosts entries for discovered containers.  In order for a container to be processed, it must have a 
VIRTUAL_HOST environment variable.  See [nginx-proxy](https://github.com/nginx-proxy/nginx-proxy) for a full description of the requirements.

**Usage**

```
    docker run -d \
    -p 53:53/udp
    -v /var/run/docker.sock:/var/run/docker.sock:ro \
    --name dynamic-dns \
    --restart unless-stopped \
    bfincher/dynamic-dns
```

