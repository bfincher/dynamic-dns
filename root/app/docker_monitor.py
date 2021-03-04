#!/usr/bin/python3

import docker
import os

thisImage = 'bfincher/dynamic-dns'


class Container:
    def __init__(self, id, virtualAlias, hostName, virtualHost, virtualPort):
        self.id = id
        self.virtualAlias = virtualAlias
        self.hostName = hostName
        self.virtualHost = virtualHost
        self.virtualPort = virtualPort

    def __eq__(self, obj):
        return self.id == obj.id

    def __str__(self):
        return "id = " + self.id[:10]

    def __unicode__(self):
        return self.__str__()

    @classmethod
    def fromConfig(cls, containerConfig):
        defaultVirtualAlias = os.environ.get('DEFAULT_VIRTUAL_ALIAS')
        for tag in containerConfig.image.tags:
            if tag == thisImage:
                return None

        attrs = containerConfig.attrs
        status = containerConfig.status
        if status != 'running' and status != 'paused':
            return None

        config = containerConfig.attrs['Config']
        envVars = config['Env']
        virtualHost = None
        virtualPort = None
        virtualAlias = None

        for envVar in envVars:
            if envVar.startswith('VIRTUAL_HOST'):
                virtualHost = envVar.partition('=')[2]
            elif envVar.startswith('VIRTUAL_PORT'):
                virtualPort = envVar.partition('=')[2]
            elif envVar.startswith('VIRTUAL_ALIAS'):
                virtualAlias = envVar.partition('=')[2]

        if not virtualAlias:
            if defaultVirtualAlias:
                virtualAlias = defaultVirtualAlias
            else:
                return

        if not virtualHost:
            return

        if not virtualPort:
            portBindings = containerConfig.ports
            for key in portBindings.keys():
                value = portBindings[key]
                if value and key.endswith('tcp'):
                    virtualPort = value[0]['HostPort']
                    break

        if virtualPort:
            networks = attrs.get('NetworkSettings').get('Networks')
            for key in networks.keys():
                ipAddr = attrs.get('NetworkSettings').get('Networks').get(key).get('IPAddress')
                break
            return Container(containerConfig.id, virtualAlias, config['Hostname'], virtualHost, virtualPort)
        else:
            return None


class DynamicDns:
    stopEventNames = ['kill', 'die', 'destroy', 'stop']

    def __init__(self):
        self.containers = {}
        self.client = docker.DockerClient(base_url='unix://var/run/docker.sock')

    def getContainers(self):
        containersList = self.client.containers
        for containerConfig in containersList.list():
            container = Container.fromConfig(containerConfig)
            if container:
                self.containers[container.id] = container

        for key in self.containers:
            print('%s -> %s' % (key, self.containers[key]))

        self.genHostsFile()

    def genHostsFile(self):
        hostsDir = os.environ['HOSTS_DIR']
        print("Generating new hosts file")

        with open(os.path.join(hostsDir, 'hosts'), 'w') as f:
            for container in self.containers.values():
                f.write("%s\t%s\n" % (container.virtualAlias, container.virtualHost))

    def processEvents(self):
        for event in self.client.events(decode=True):
            status = event.get('status')
            if status:
                if status == 'start':
                    self.processStartEvent(event)
                elif status in DynamicDns.stopEventNames:
                    self.processStopEvent(event)

                if not status.startswith('exec'):
                    print(event)

    def processStopEvent(self, event):
        id = event.get('id')
        if self.containers.pop(id, None):
            print("Generating new config due to removal of container %s" % id)
            self.genHostsFile()

    def processStartEvent(self, event):
        id = event.get('id')
        containerConfig = self.client.containers.get(id)
        container = Container.fromConfig(containerConfig)
        if container:
            genNewConfig = False
            oldContainer = self.containers.get(id)
            self.containers[id] = container
            print('adding %s to containers' % id)
            if oldContainer:
                if oldContainer != container:
                    genNewConfig = True
            else:
                genNewConfig = True

            if genNewConfig:
                self.genHostsFile()

            print("%s started.  Image name = %s" % (container, containerConfig.image))


if __name__ == '__main__':
    np = DynamicDns()
    np.getContainers()
    np.processEvents()
