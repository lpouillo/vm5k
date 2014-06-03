#!/usr/bin/env python
import threading
from pprint import pprint
import xml.etree.ElementTree as ET
from execo import Process, SshProcess, TaktukPut, TaktukRemote, logger, Remote, default_connection_params
from execo.time_utils import sleep, Timer


logger.setLevel('INFO')

default_connection_params['user'] = 'root'

vms = {}
f = open('vms.list')
for line in f:
    ip, vm = line.strip().split('\t')
    vms[vm] = ip
f.close()
 
logger.info('Installing cpulimit on all VMs')
apt = TaktukRemote('apt-get install -y cpulimit', vms.values()).run()
 
logger.info('Copying memtouch on all vms')
copy_stress = TaktukPut(vms.values(), ['memtouch-with-busyloop3']).run()

logger.info('Killing all memtouch processes') 
kill_stress = TaktukRemote('killall memtouch-with-busyloop3', vms.values())
for p in kill_stress.processes:
    p.shell = True
    p.nolog_exit_code = ignore_exit_code = True
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

logger.info('Retrieving memtouch process id') 
cmd = 'ps aux | grep "memtouch-with-busyloop3" | grep -v "grep" | awk \'{print $2}\''
get_stress = TaktukRemote(cmd, vms.values()).run()

logger.info('Limiting memtouch to 1% cpu via cpulimit')
tmp_vms = []
processes = []
vms_proc = {}
for p in get_stress.processes:
    tmp_vms.append(p.host.address)
    processes.append(p.stdout.strip())
    vms_proc[p.host.address] = p.stdout.strip()
init_limit = TaktukRemote('cpulimit -p {{processes}} -l 1', tmp_vms)
for p in init_limit.processes:
    p.nolog_exit_code = ignore_exit_code = True
init_limit.start()

logger.info('Configuring events generator')
n_host = 0
f = open('hosts.list')
for line in f:
    n_host += 1
f.close()
sed_time = Process('sed -i "s/simulator.duration.*/simulator.duration = ' + str(1000) + '/g"' + 
      ' load_events_generator/config/simulator.properties').run()
sed_nodes = Process('sed -i "s/nodes.number.*/nodes.number = ' + str(n_host) + '/g"' + 
      ' load_events_generator/config/simulator.properties').run()
sed_vms = Process('sed -i "s/vm.number.*/vm.number = ' + str(len(vms)) + '/g"' + 
      ' load_events_generator/config/simulator.properties').run()

logger.info('Generating events list')
gen_events = Process('cd load_events_generator ; ' +
      'java -jar load_events_generator.jar vms.list > ../events_load.xml')
gen_events.shell = True
gen_events.run()

tree = ET.parse('events_load.xml') 
root = tree.getroot()
events = {}
for event in root.findall('./event'):
    events[int(round(float(event.get('time'))))] = {'vm': event.get('target'),
                                'load': event.get('value')}

 
def set_cpu_load(load, vm_ip, pid):
    """Use cpulimit to change process intensity on vm"""
    logger.info('kill cpu_limit on %s and set it to %s', vm_ip, load)
    kill_cpu_limit = SshProcess('ps aux| grep "cpulimit" | grep -v "grep" | awk \'{print $2}\' | xargs -r kill -9',
                                vm_ip).run()
    start_cpu_limit = SshProcess('cpulimit -p ' + str(pid) + ' -l ' + str(load), vm_ip)
    start_cpu_limit.nolog_exit_code = start_cpu_limit.ignore_exit_code = True
    start_cpu_limit.start()
 
 
logger.setLevel('INFO')

 
timer = Timer()
for e_time in sorted(events):
    logger.info('sleeping %ss before setting load=%s on %s',
        str(round(e_time-timer.elapsed())), events[e_time]['load'], events[e_time]['vm'])
    sleep(e_time-timer.elapsed())
    set_cpu_load(events[e_time]['load'], vms[events[e_time]['vm']], 
                 vms_proc[vms[events[e_time]['vm']]]) 





