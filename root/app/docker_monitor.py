#!/usr/bin/python3

import logging
import os
import sys
import docker

# for testing purposes
rootDir = '/'
thisImage = 'bfincher/dynamic-dns'

def getNginxConfigFile():
    return os.path.join(rootDir, 'nginx_config/default.conf')

def getConfigDir():
    return os.path.join(rootDir, "config")

logging.root.setLevel(logging.INFO)
logger = logging.getLogger('docker_monitor')
logger.addHandler(logging.StreamHandler(stream=sys.stdout))


class Container:

    def __init__(self, containerId, virtualAlias, hostName, virtualHost, virtualPort):  # pylint: disable=too-many-arguments
        self.containerId = containerId
        self.virtualAlias = virtualAlias
        self.hostName = hostName
        self.virtualHost = virtualHost
        self.virtualPort = virtualPort
        self.isHttps = False

    def setIsHttps(self):
        self.isHttps = True

    def __eq__(self, obj):
        return (self.containerId == obj.containerId and
            self.virtualAlias == obj.virtualAlias and
            self.hostName == obj.hostName and
            self.virtualHost == obj.virtualHost and
            self.virtualPort == obj.virtualPort and
            self.isHttps == obj.isHttps)

    def __str__(self):
        return "containerId = " + self.containerId[:10]

    @classmethod
    def fromConfig(cls, containerConfig):
        for tag in containerConfig.image.tags:
            if tag == thisImage:
                return None

        status = containerConfig.status
        if status not in ['running', 'paused']:
            return None

        config = containerConfig.attrs['Config']
        print('BKF config = %s' % config)
        envVars = config['Env']
        virtualHostTuple = _getVirtualHost(envVars)
        virtualPort = _getVirtualPort(envVars, containerConfig)
        virtualAlias = _getVirtualAlias(envVars)

        if not virtualAlias:
            logger.info("Container %s has no virtual alias", containerConfig.id)
            return None

        if not virtualHostTuple:
            logger.info("Container %s has no virtual host", containerConfig.id)
            return None

        if not virtualPort:
            logger.info("Container %s has no virtual port", containerConfig.id)
            return None

        container = Container(containerConfig.id, virtualAlias, config['Hostname'], virtualHostTuple[1], virtualPort)
        if virtualHostTuple[0]:
            container.setIsHttps()
        return container


def _getVirtualHost(envVars):
    for envVar in envVars:
        if envVar.startswith('VIRTUAL_HOST'):
            return (False, envVar.partition('=')[2])
        if envVar.startswith('VIRTUAL_HOST_HTTPS'):
            return (True, envVar.partition('=')[2])

    return None


def _getVirtualPort(envVars, containerConfig):
    for envVar in envVars:
        if envVar.startswith('VIRTUAL_PORT'):
            return envVar.partition('=')[2]

    # if not in env var, look in port bindings
    portBindings = containerConfig.ports
    for key in portBindings.keys():
        value = portBindings[key]
        if value and isinstance(key, str) and key.endswith('tcp'):
            return value[0]['HostPort']

    return None


def _getVirtualAlias(envVars):
    for envVar in envVars:
        if envVar.startswith('VIRTUAL_ALIAS'):
            return envVar.partition('=')[2]

    defaultVirtualAlias = os.environ.get('DEFAULT_VIRTUAL_ALIAS')
    if defaultVirtualAlias:
        return defaultVirtualAlias

    return None

def _readNginxConfigPrefix():
    with open(os.path.join(getConfigDir(), "nginx_prefix.conf")) as f:
        return f.read()


class DynamicDns:
    stopEventNames = ['kill', 'die', 'destroy', 'stop']

    def __init__(self):
        self.containers = {}
        self.client = None
        self._initDockerClient()
        self.nginxConfigPrefix = _readNginxConfigPrefix()

    # in a separate method for testing purposes
    def _initDockerClient(self):
        self.client = docker.DockerClient(base_url='unix://var/run/docker.sock')

    def getContainers(self):
        containersList = self.client.containers
        for containerConfig in containersList.list():
            container = Container.fromConfig(containerConfig)
            if container:
                self.containers[container.containerId] = container

        for key, value in self.containers.items():
            logger.info('%s -> %s', key, value)

        self.genHostsFile()
        self.genNginxConfig()

    def genHostsFile(self):
        hostsDir = os.environ['HOSTS_DIR']
        logger.info("Generating new hosts file")

        with open(os.path.join(hostsDir, 'hosts'), 'w', encoding='utf8') as f:
            for container in self.containers.values():
                f.write(f"{container.virtualAlias}\t{container.virtualHost}\n")

    def genNginxConfig(self):
        with open(getNginxConfigFile(), 'w', encoding='utf-8') as f:
            f.write(self.nginxConfigPrefix)
            f.write("\n")
            for container in self.containers.values():
                f.write(f"upstream {container.containerId} {{\n")
                f.write(f"    server {container.ip}:{container.virtualPort};\n")
                f.write("}\n")
                f.write("server {\n")
                f.write(f"    server_name {container.virtualAlias};\n")
                if container.isHttps:
                    f.write("    listen 443 ssl;\n")
                else:
                    f.write("    listen 80;\n")
                f.write("    access_log /var/log/nginx/access.log vhost;\n")
                f.write("    location / {\n")
                f.write(f"        proxy_pass http://{container.containerId};\n")
                f.write("    }\n")

                if container.isHttps:
                    certPath = f"/etc/letsencrypt/live/{container.virtualAlias}"
                    f.write(f"\n    ssl_certificate {certPath}/fullchain.pem;\n")
                    f.write(f"\n    ssl_certificate {certPath}/privkey.pem;\n")
                f.write("}\n\n")


    def processEvents(self):
        for event in self.client.events(decode=True):
            status = event.get('status')
            if status:
                if status == 'start':
                    self.processStartEvent(event)
                elif status in DynamicDns.stopEventNames:
                    self.processStopEvent(event)

    def processStopEvent(self, event):
        containerId = event.get('id')
        if self.containers.pop(containerId, None):
            logger.info("Generating new config due to removal of container %s", containerId)
            self.genHostsFile()
            self.genNginxConfig()

    def processStartEvent(self, event):
        containerId = event.get('id')
        containerConfig = self.client.containers.get(containerId)
        container = Container.fromConfig(containerConfig)
        if container:
            genNewConfig = False
            oldContainer = self.containers.get(containerId)
            self.containers[containerId] = container
            logger.info('adding %s to containers', containerId)
            if oldContainer:
                if oldContainer != container:
                    genNewConfig = True
            else:
                genNewConfig = True

            if genNewConfig:
                self.genHostsFile()
                self.genNginxConfig()

            logger.info("%s started.  Image name = %s", container, containerConfig.image)


if __name__ == '__main__':
    np = DynamicDns()
    np.getContainers()
    np.processEvents()
