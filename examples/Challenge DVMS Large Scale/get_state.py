#!/usr/bin/env python
from pprint import pformat
from xml.etree.ElementTree import Element, dump, SubElement
from execo import logger, default_connection_params, sleep
from execo_g5k import get_host_site, get_host_cluster, get_cluster_site
from vm5k import list_vm
from vm5k.utils import prettify

default_connection_params['user'] = 'root'
logger.setLevel('INFO')
hosts = []
with open('hosts.list') as fp:
    for line in fp:
        hosts.append(line.strip())

sites = list(set(map(get_host_site, hosts)))
clusters =list(set(map(get_host_cluster, hosts)))

state = Element('vm5k')
for site in sites:
    SubElement(state, 'site', attrib={'id': site})
for cluster in clusters:
    el_site = state.find("./site[@id='" + get_cluster_site(cluster) \
                          + "']")
    SubElement(el_site, 'cluster', attrib={'id': cluster})
for host in hosts:
    el_cluster = state.find(".//cluster/[@id='" + get_host_cluster(host) + "']")
    SubElement(el_cluster, 'host', attrib={'id': host})                                               



while True:
    logger.info('Listing VMS on %s', ','.join(map(lambda x: x.split('.')[0], hosts)))
    hosts_vms = list_vm(hosts)
    for host, vms in hosts_vms.iteritems():
        el_host = state.find(".//host/[@id='" + host + "']")
        for vm in vms: 
            SubElement(el_host, 'vm', attrib={'id': vm['id']})
    
    f = open('topo.xml', 'w')
    f.write(prettify(state))
    f.close()
    for el_host in state.findall('.//host'):
        for vm in el_host.findall('./vm'):
            el_host.remove(vm)
        
