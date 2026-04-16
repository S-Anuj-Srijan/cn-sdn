from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.topology import event
from ryu.topology.api import get_switch, get_link

class PathTracer(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(PathTracer, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.topology_api_app = self
        self.network = {} # dpid -> {neighbor_dpid: out_port}
        self.switches = {} # dpid -> datapath
        self.mac_to_dpid = {} # mac -> (dpid, in_port)
        self.paths_printed = set()

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(event.EventSwitchEnter)
    @set_ev_cls(event.EventSwitchLeave)
    @set_ev_cls(event.EventLinkAdd)
    @set_ev_cls(event.EventLinkDelete)
    def update_topology(self, ev=None):
        switch_list = get_switch(self.topology_api_app, None)
        for switch in switch_list:
            self.switches[switch.dp.id] = switch.dp
            if switch.dp.id not in self.network:
                self.network[switch.dp.id] = {}

        links_list = get_link(self.topology_api_app, None)
        for link in links_list:
            src = link.src
            dst = link.dst
            # Update the network graph with the port connecting src to dst
            self.network[src.dpid][dst.dpid] = src.port_no

    def bfs_shortest_path(self, src_dpid, dst_dpid):
        """Find the shortest path between two switches using Breadth-First Search."""
        if src_dpid == dst_dpid:
            return [src_dpid]
        
        queue = [[src_dpid]]
        visited = set([src_dpid])
        
        while queue:
            path = queue.pop(0)
            node = path[-1]
            
            if node == dst_dpid:
                return path
            
            out_nodes = self.network.get(node, {}).keys()
            for neighbor in out_nodes:
                if neighbor not in visited:
                    new_path = list(path)
                    new_path.append(neighbor)
                    queue.append(new_path)
                    visited.add(neighbor)
        return None

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP or eth.ethertype == ether_types.ETH_TYPE_IPV6:
            # ignore LLDP and IPv6
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        # Make sure topology graph is fully up-to-date
        self.update_topology()

        # Learn the MAC address to avoid flooding next time
        if src not in self.mac_to_dpid:
            self.mac_to_dpid[src] = (dpid, in_port)

        path_found = False
        if dst in self.mac_to_dpid:
            dst_dpid, dst_port = self.mac_to_dpid[dst]
            
            # Compute shortest path from current switch to destination switch
            path = self.bfs_shortest_path(dpid, dst_dpid)

            if path:
                path_found = True
                # Display route: only print when packet is at the source switch to avoid printing multiple times
                src_dpid, src_port = self.mac_to_dpid[src]
                if dpid == src_dpid:
                    path_str = f"({src}) "
                    for p in path:
                        path_str += f"-> S{p} "
                    path_str += f"-> ({dst})"
                    
                    path_key = f"{src}-{dst}"
                    if path_key not in self.paths_printed:
                        self.logger.info("====================================")
                        self.logger.info("ROUTE DISCOVERED")
                        self.logger.info("Flow: %s -> %s", src, dst)
                        self.logger.info("Path: %s", path_str)
                        self.logger.info("====================================")
                        self.paths_printed.add(path_key)

                # Determine out_port on the current switch toward the next hop
                if len(path) > 1:
                    next_dpid = path[1]
                    out_port = self.network[dpid][next_dpid]
                else:
                    # Switch is the destination switch
                    out_port = dst_port

                # Install the flow rule
                actions = [parser.OFPActionOutput(out_port)]
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
                
                # Verify if we have a valid buffer_id, if yes avoid to send both
                # flow_mod & packet_out
                if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                    self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                    return
                else:
                    self.add_flow(datapath, 1, match, actions)

        if not path_found:
            # If path not found or destination MAC unknown, flood
            out_port = ofproto.OFPP_FLOOD
            actions = [parser.OFPActionOutput(out_port)]

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
