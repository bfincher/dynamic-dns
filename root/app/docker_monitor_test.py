'''
Created on Dec 29, 2021

@author: bfincher
'''
import logging
import os
from shutil import rmtree
import unittest
from docker_monitor import Container, DynamicDns, thisImage

logging.getLogger("docker_monitor").setLevel(logging.CRITICAL)


class TestContainerConfig:

    class Image: #pylint: disable=too-few-public-methods

        def __init__(self):
            self.tags = []

    def __init__(self, id, status): #pylint: disable=redefined-builtin
        self.image = self.Image()
        self.id = id
        self.env = []
        self.config = {'Env': self.env}
        self.attrs = {'Config': self.config}

        self.status = status
        self.ports = {}

    @classmethod
    def create(cls, id, status, virtualHost, virtualPort, virtualAlias, hostName): #pylint: disable=too-many-arguments, redefined-builtin
        config = TestContainerConfig(id, status)
        config.addEnvVar(f"VIRTUAL_HOST={virtualHost}")
        config.addEnvVar(f"VIRTUAL_PORT={virtualPort}")
        config.addEnvVar(f"VIRTUAL_ALIAS={virtualAlias}")
        config.setHostName(hostName)
        return config

    def addTag(self, tag):
        self.image.tags.append(tag)

    def addEnvVar(self, envVar):
        self.env.append(envVar)

    def setHostName(self, hostName):
        self.config['Hostname'] = hostName


class ContainerTest(unittest.TestCase):

    def __init__(self, methodName='runTest'):
        super().__init__(methodName)
        self.testContainerConfig = None

    def setUp(self):
        self.testContainerConfig = TestContainerConfig.create("testId",
                                                              "running",
                                                              "TEST_VIRTUAL_HOST",
                                                              "1234",
                                                              "TEST_VIRTUAL_ALIAS",
                                                              "testHostname")

    def test(self):
        container = Container.fromConfig(self.testContainerConfig)
        self._compare(container, "testId", "TEST_VIRTUAL_HOST", "1234", "TEST_VIRTUAL_ALIAS", "testHostname")

        # try again with paused state
        self.testContainerConfig.status = 'paused'
        container = Container.fromConfig(self.testContainerConfig)
        self._compare(container, "testId", "TEST_VIRTUAL_HOST", "1234", "TEST_VIRTUAL_ALIAS", "testHostname")

    def testNotRunningOrPaused(self):
        self.testContainerConfig.status = 'stopped'
        container = Container.fromConfig(self.testContainerConfig)
        self.assertEqual(None, container)

    def testTagIsThisImage(self):
        self.testContainerConfig.addTag(thisImage)
        container = Container.fromConfig(self.testContainerConfig)
        self.assertEqual(None, container)

    def testNoVirtualHost(self):
        self.testContainerConfig.env.remove("VIRTUAL_HOST=TEST_VIRTUAL_HOST")
        container = Container.fromConfig(self.testContainerConfig)
        self.assertEqual(None, container)

    def testNoVirtualPort(self):
        self.testContainerConfig.env.remove("VIRTUAL_PORT=1234")
        container = Container.fromConfig(self.testContainerConfig)
        self.assertEqual(None, container)

    def testVirtualPortFromBindings(self):
        self.testContainerConfig.env.remove("VIRTUAL_PORT=1234")
        self.testContainerConfig.ports[1] = 'test'  # int keys should be skipped
        self.testContainerConfig.ports['port_tcp'] = [{'HostPort': "2345"}]
        container = Container.fromConfig(self.testContainerConfig)
        self._compare(container, "testId", "TEST_VIRTUAL_HOST", "2345", "TEST_VIRTUAL_ALIAS", "testHostname")

    def testNoVirtualAlias(self):
        self.testContainerConfig.env.remove("VIRTUAL_ALIAS=TEST_VIRTUAL_ALIAS")
        container = Container.fromConfig(self.testContainerConfig)
        self.assertEqual(None, container)

    def testDefaultVirtualAlias(self):
        self.testContainerConfig.env.remove("VIRTUAL_ALIAS=TEST_VIRTUAL_ALIAS")
        try:
            os.environ['DEFAULT_VIRTUAL_ALIAS'] = 'defaultValue'
            container = Container.fromConfig(self.testContainerConfig)
            self._compare(container, "testId", "TEST_VIRTUAL_HOST", "1234", "defaultValue", "testHostname")
        finally:
            del os.environ['DEFAULT_VIRTUAL_ALIAS']

    def _compare(self, container, containerId, virtualHost, virtualPort, virtualAlias, hostName): #pylint: disable=too-many-arguments
        self.assertEqual(containerId, container.containerId)
        self.assertEqual(virtualHost, container.virtualHost)
        self.assertEqual(virtualPort, container.virtualPort)
        self.assertEqual(virtualAlias, container.virtualAlias)
        self.assertEqual(hostName, container.hostName)


class TestDynamicDns(unittest.TestCase):

    class DockerClient: #pylint: disable=too-few-public-methods

        class ContainersList:

            def __init__(self):
                self.theList = []

            def list(self):
                return self.theList

            def get(self, containerId):
                for container in self.theList:
                    if container.id == containerId:
                        return container
                return None

        def __init__(self):
            self.containers = self.ContainersList()
            self._events = [{}]

        def events(self, decode=True): #pylint: disable=unused-argument
            return self._events

    class DymanicDnsForTest(DynamicDns): #pylint: disable=too-few-public-methods

        def __init__(self, client):
            super().__init__()
            self.client = client
            self.genHostsFileCallCount = 0

        def _initDockerClient(self):
            pass  # no action necessary as the constructor has already set self.client

        def genHostsFile(self):
            DynamicDns.genHostsFile(self)
            self.genHostsFileCallCount += 1

    @classmethod
    def setUpClass(cls):
        super(TestDynamicDns, cls).setUpClass()
        if os.path.exists("hostsDir"):
            rmtree("hostsDir")
        os.mkdir("hostsDir")
        os.environ['HOSTS_DIR'] = "hostsDir"

    @classmethod
    def tearDownClass(cls):
        super(TestDynamicDns, cls).tearDownClass()
        # rmtree("hostsDir")
        del os.environ['HOSTS_DIR']

    def setUp(self):
        self.client = self.DockerClient()
        self.instanceForTest = self.DymanicDnsForTest(self.client)

        self.config1 = TestContainerConfig.create("id1",
                                                  "running",
                                                  "vh1",
                                                  "1",
                                                  "va1",
                                                  "h1")

        self.config2 = TestContainerConfig.create("id2",
                                                  "paused",
                                                  "vh2",
                                                  "2",
                                                  "va2",
                                                  "h2")

        self.config3 = TestContainerConfig.create("id3",
                                                  "not_running",
                                                  "vh3",
                                                  "3",
                                                  "va3",
                                                  "h3")

        self.config4 = TestContainerConfig.create("id4",
                                                  "running",
                                                  "vh4",
                                                  "4",
                                                  "va4",
                                                  "h4")

        self.config5 = TestContainerConfig.create("id5",
                                                  "running",
                                                  "vh5",
                                                  "5",
                                                  "va5",
                                                  "h5")

        # intentionally omitting config5 from this list
        self.client.containers.theList = [self.config1, self.config2, self.config3, self.config4]

        self.instanceForTest.getContainers()

    def testGetContainers(self):
        self.assertEqual(3, len(self.instanceForTest.containers))
        self.assertContainerIn(Container.fromConfig(self.config1), self.instanceForTest.containers)
        self.assertContainerIn(Container.fromConfig(self.config2), self.instanceForTest.containers)
        self.assertContainerIn(Container.fromConfig(self.config4), self.instanceForTest.containers)

        self.assertTrue(os.path.exists("hostsDir/hosts"))
        with open("hostsDir/hosts", "r", encoding='utf8') as f:
            lines = f.readlines()

        self.assertEqual(3, len(lines))
        self.assertIn("va1\tvh1\n", lines)
        self.assertIn("va2\tvh2\n", lines)
        self.assertIn("va4\tvh4\n", lines)

    def testStopEvent(self):
        for eventStatus in DynamicDns.stopEventNames:
            with self.subTest(eventStatus):
                events = self.client.events()[0]
                events['id'] = 'id2'
                events['status'] = eventStatus

                self.instanceForTest.processEvents()
                self.assertTrue(os.path.exists("hostsDir/hosts"))
                with open("hostsDir/hosts", "r", encoding='utf8') as f:
                    lines = f.readlines()

                # called once for the initial and once for the removed event
                self.assertEqual(2, self.instanceForTest.genHostsFileCallCount)

                self.assertEqual(2, len(lines))
                self.assertIn("va1\tvh1\n", lines)
                self.assertIn("va4\tvh4\n", lines)

    def testStopEventUnknownContainer(self):
        events = self.client.events()[0]
        events['id'] = 'id5'
        events['status'] = DynamicDns.stopEventNames[0]

        self.instanceForTest.processEvents()
        # called once for the initial
        self.assertEqual(1, self.instanceForTest.genHostsFileCallCount)

    def testStartEvent(self):
        events = self.client.events()[0]
        events['id'] = 'id5'
        events['status'] = 'start'
        self.instanceForTest.client.containers.list().append(self.config5)

        self.instanceForTest.processEvents()

        # called once for the initial, once for the new event
        self.assertEqual(2, self.instanceForTest.genHostsFileCallCount)

        with open("hostsDir/hosts", "r", encoding='utf8') as f:
            lines = f.readlines()

        self.assertEqual(4, len(lines))
        self.assertIn("va1\tvh1\n", lines)
        self.assertIn("va2\tvh2\n", lines)
        self.assertIn("va4\tvh4\n", lines)
        self.assertIn("va5\tvh5\n", lines)

    def testStartEventNoContainer(self):
        events = self.client.events()[0]
        events['id'] = 'id3'  # id3 doesn't have a valid status
        events['status'] = 'start'

        self.instanceForTest.processEvents()

        # called once for the initial
        self.assertEqual(1, self.instanceForTest.genHostsFileCallCount)

    def testStartEventExistingNoChange(self):
        events = self.client.events()[0]
        events['id'] = 'id4'
        events['status'] = 'start'

        self.instanceForTest.processEvents()

        # called once for the initial
        # since there is no change in id4, nothing should happen
        self.assertEqual(1, self.instanceForTest.genHostsFileCallCount)

    def testStartEventExistingWithChange(self):
        self.config4.env.remove("VIRTUAL_HOST=vh4")
        self.config4.addEnvVar("VIRTUAL_HOST=newVirtualHost")
        events = self.client.events()[0]
        events['id'] = 'id4'
        events['status'] = 'start'

        self.instanceForTest.processEvents()

        # called once for the initial, once for the new event
        self.assertEqual(2, self.instanceForTest.genHostsFileCallCount)

        with open("hostsDir/hosts", "r", encoding='utf8') as f:
            lines = f.readlines()

        self.assertEqual(3, len(lines))
        self.assertIn("va1\tvh1\n", lines)
        self.assertIn("va2\tvh2\n", lines)
        self.assertIn("va4\tnewVirtualHost\n", lines)

    def assertContainerIn(self, container, containers):
        found = False
        for c in containers.values():
            if compareContainers(container, c):
                found = True
                break

        self.assertTrue(found, f"Did not find {container.containerId} in containers")

def compareContainers(c1, c2):
    return (c1.containerId == c2.containerId and
        c1.virtualAlias == c2.virtualAlias and
        c1.virtualHost == c2.virtualHost and
        c1.virtualPort == c2.virtualPort and
        c1.hostName == c2.hostName)

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
