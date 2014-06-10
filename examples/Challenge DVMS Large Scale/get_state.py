#!/usr/bin/env python
from pprint import pformat
from xml.etree.ElementTree import Element, dump, SubElement, parse
from execo import logger, default_connection_params, sleep, TaktukPut, TaktukRemote
from execo_g5k import get_host_site, get_host_cluster, get_cluster_site
from vm5k import default_vm
from vm5k.utils import prettify

logger.setLevel('INFO')

default_connection_params['user'] = 'root'

def _default_xml_value(key):
    return default_vm[key] if key not in vm.attrib else vm.get(key)


logger.info('Reading initial topo')
tree = parse('final_topo.xml')
state = tree.getroot()

hosts = sorted([host.get('id') for host in state.findall('.//host') if host.get('state') == 'OK'],
                       key=lambda host: (host.split('.', 1)[0].split('-')[0],
                                    int(host.split('.', 1)[0].split('-')[1])))
# logger.info('Pushing get_cpu_consumptions.rb on hosts')
# TaktukPut(hosts, ['get_cpu_consumptions.rb']).run()

vms = []
for host in state.findall('.//host'):
    for vm in host.findall('.//vm'):
        vms.append({'id': vm.get('id'),
            'n_cpu': int(_default_xml_value('n_cpu')),
            'cpuset': _default_xml_value('cpuset'),
            'mem': int(_default_xml_value('mem')),
            'hdd': int(_default_xml_value('hdd')),
            'backing_file': _default_xml_value('backing_file'),
            'ip': _default_xml_value('ip'),
            'mac': _default_xml_value('mac'),
            'host': host.get('id')})

while True:
    logger.detail('Cleaning all VMS from XML file')
    for el_host in state.findall('.//host'):
        for vm in el_host.findall('./vm'):
            el_host.remove(vm)
    logger.info('Retrieving VMS position and load')
    get_vms_load = TaktukRemote("get_cpu_consumptions.sh",
       hosts).run()
    vms_loads = {}
    hosts_vms = {host: [] for host in hosts}    
    for p in get_vms_load.processes:
        for line in p.stdout.strip().split('\n'):
            logger.detail(p.host.address)
            tmp_load = line.split(' ')
            logger.detail(tmp_load)
            vms_loads[tmp_load[0]] = float(tmp_load[1]) + float(tmp_load[2]) + float(tmp_load[-1])
            hosts_vms[p.host.address].append(tmp_load[0])
    logger.detail(hosts_vms)

    for host, vms_list in hosts_vms.iteritems():
        el_host = state.find(".//host/[@id='" + host + "']")
        for vm in vms_list: 
            attrib = filter(lambda x: x['id'] == vm, vms)[0]
            attrib = dict(attrib.items() + {'load': str(vms_loads[vm])}.items())
            attrib = {k: str(v) for k, v in attrib.items()}
            del attrib['backing_file']
            del attrib['host']
            logger.detail('Adding %s to %s', vm, host)
            SubElement(el_host, 'vm', attrib=attrib)

    f = open('state.xml', 'w')
    f.write(prettify(state))
    f.close()
         
