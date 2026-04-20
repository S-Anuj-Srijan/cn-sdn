# SDN-Based Path Tracing Tool using Mininet & Ryu

This project implements a path tracing tool where an SDN controller (Ryu) computes the shortest path between hosts, installs OpenFlow rules along the path dynamically, and logs the chosen route. 

## Requirements
- **Kali Linux VM** (Environment already configured)
- **Mininet 2.3.1b4** (Installed from source)
- **Open vSwitch 3.7.1** (Configured for OpenFlow 1.3)
- **Ryu 4.34** (Successfully patched for Python 3.13 compatibility)

## High-Level Features
- **Topology Discovery:** The controller automatically learns links and switch locations using Ryu's topology API.
- **Shortest-Path Logic:** When a packet enters the network, BFS is used to compute the shortest path to the destination.
- **Dynamic Flows:** Flow rules (OpenFlow 1.3) are installed securely on each switch.
- **Route Tracking:** The computed path (e.g., `MacA -> S1 -> S2 -> S4 -> MacB`) is displayed cleanly in the controller terminal.

---

## 0. Environment Setup (Pre-configured)
This project has been specially configured to run on **Python 3.13** on Kali Linux. The following fixes were applied:
- **Ryu Source Patch**: `ryu/hooks.py` was patched to remove legacy `easy_install` dependencies.
- **Dependency Modernization**: `eventlet` (0.41.0) and `dnspython` (2.8.0) were force-upgraded to support modern built-ins like `TimeoutError`.
- **Global Path**: Services like `mn` and `ryu-manager` are installed and ready to use for the `root` user.

---

## 1. How to Run (Automated)

The easiest way to run the demo is using the provided `launch.sh` script. This script uses `tmux` to automatically split your terminal and start both the Ryu controller and Mininet concurrently.

```bash
# Make the script executable (if needed)
chmod +x launch.sh

# Run the automated demo
./launch.sh
```

---

## 2. Manual Verification

If you prefer to run the components manually in two separate terminal windows:

### Terminal 1: Start the Ryu Controller
```bash
# Clean previous mininet states
sudo mn -c

# Start the controller
cd ~/Desktop/cn-sdn
ryu-manager --observe-links path_tracer.py
```

### Terminal 2: Start Mininet
```bash
sudo mn --custom topo.py --topo pathtopo --mac --switch ovsk --controller remote
```

---

## 3. Verification & Demo Results

### Connectivity Check
Inside the Mininet terminal, running `pingall` results in **0% packet loss**, confirming that the controller has successfully installed all necessary flow rules.

```text
mininet> pingall
*** Ping: testing ping reachability
h1 -> h2 h3 h4 
h2 -> h1 h3 h4 
h3 -> h1 h2 h4 
h4 -> h1 h2 h3 
*** Results: 0% dropped (12/12 received)
```

### Path discovery Logs
The Ryu controller log demonstrates real-time path discovery. When traffic is initiated between `h1` and `h4`, the controller computes the shortest path using BFS and logs the route:

```text
====================================
ROUTE DISCOVERED
Flow: 00:00:00:00:00:01 -> 00:00:00:00:00:04
Path: (00:00:00:00:00:01) -> S1 -> S2 -> S4 -> (00:00:00:00:00:04)
====================================
```

---

## 4. Validating the Path (OVS Tracing)

As part of your project, you need to validate that the OpenFlow layer is doing exactly what Ryu instructed.

### Check Switch Flow Tables
To see the exact OpenFlow rules installed by Ryu on switch `s1`:
```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```
You will see rules explicitly matching `dl_src` (Source MAC) and `dl_dst` (Destination MAC) and an `actions=output:X`.

### Use OVS's OpenFlow Trace (Advanced Validation)
You can trace how `s1` handles an ICMP packet from `h1` (10.0.0.1) to `h4` (10.0.0.4) entering port 1.
Open a third terminal and run:
```bash
sudo ovs-appctl ofproto/trace s1 in_port=1,ip,nw_src=10.0.0.1,nw_dst=10.0.0.4,dl_src=00:00:00:00:00:01,dl_dst=00:00:00:00:00:04
```
At the bottom of the output, checking `Datapath actions`, you should see it outputting to the exact port going towards either `s2` or `s3` (depending on the shortest path Ryu computed).

---

## 4. Link Failure Testing

To demonstrate dynamic route re-calculation to your professor:
1. Ping from h1 to h4. Note the path (e.g., `S1 -> S2 -> S4`)
2. In Mininet, disable the link between `s1` and `s2`:
   ```bash
   mininet> link s1 s2 down
   ```
3. Run the ping again.
4. Ryu will detect the missing link and re-route packets via `s3`!
