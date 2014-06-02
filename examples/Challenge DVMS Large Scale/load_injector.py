#!/usr/bin/env python
import threading
from pprint import pprint
import xml.etree.ElementTree as ET
from execo import TaktukPut, TaktukRemote, logger, Remote
from execo.time_utils import sleep, Timer

logger.setLevel('INFO')

vms = {}
f = open('test_100/vms.list')
for line in f:
    ip, vm = line.strip().split('\t')
    vms[vm] = ip
f.close()

logger.info('Installing cpulimit on all VMs')
apt = TaktukRemote('apt-get install -y cpulimit', vms.values()).run()

logger.info('Copying memtouch on all vms')
TaktukPut(vms.values(), ['memtouch-with-busyloop3']).run()

kill_stress = TaktukRemote('killall memtouch-with-busyloop3', vms.values())
for p in kill_stress.processes:
    p.shell = True
kill_stress.run()

logger.info('Starting memtouch process')
cmd = './memtouch-with-busyloop3 --cmd-makeload ' +\
    '--cpu-speed 304408.621872 --mem-speed 63235516.087661 128 128'
stress = TaktukRemote(cmd, vms.values()).start()

all_started = False
while not all_started:
    all_started = True
    for p in stress.processes:
        if not p.started:
            all_started = False
            sleep(1)
            break 

cmd = 'ps aux | grep "memtouch-with-busyloop3" | grep -v "grep" | awk \'{print $2}\''
get_stress = TaktukRemote(cmd, vms.values()).run()
processes = {}
for p in get_stress.processes:
    vm = [vm for vm, ip in vms.items() if ip == p.host.address][0]
    processes[vm] = int(p.stdout)


tree = ET.parse('events_load.xml')
root = tree.getroot()
events_t = {}
for event in root.findall('./event'):
    events[int(event.get('time'))] = {'vm': event.get('target'),
                                'load': event.get('value')}

def set_cpu_load(load, vm_ip, pid, ):
    """Use cpulimit to change process intensity on vm"""
    kill_cpu_limit = SshProcess('ps aux| grep "cpulimit" | grep -v "grep" | awk \'{print $2}\' | xarg    s -r kill -9',
                                vm_ip).run()
    start_cpu_limit = SshProcess('cpu')







