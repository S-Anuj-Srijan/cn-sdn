from mininet.topo import Topo

class PathTopo(Topo):
    "Custom Topology with multiple paths to demonstrate path tracing."

    def build(self):
        # Add hosts
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')

        # Add switches
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')

        # Connect hosts to switches
        self.addLink(h1, s1)
        self.addLink(h2, s2)
        self.addLink(h3, s3)
        self.addLink(h4, s4)

        # Connect switches to form a topology with alternative paths
        # s1 has two paths to s4: via s2 or via s3
        self.addLink(s1, s2)
        self.addLink(s2, s4)
        
        self.addLink(s1, s3)
        self.addLink(s3, s4)

topos = {'pathtopo': (lambda: PathTopo())}
