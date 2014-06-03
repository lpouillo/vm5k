#!/usr/bin/env python
from pprint import pprint
from execo import TaktukRemote
from execo.time_utils import sleep
from execo_g5k import get_host_site, get_host_cluster, get_kavlan_host_name, \
    get_g5k_sites
from vm5k import list_vm, get_oargrid_job_vm5k_resources
from vm5k.plots import topology_plot
from xml.etree.ElementTree import Element, SubElement, dump


state = Element('vm5k')

resources = get_oargrid_job_vm5k_resources(49509)
sites = sorted([site for site in resources.keys() if site != 'global'])
kavlan = resources['global']['kavlan']
hosts = []
for site in sites:
    hosts += map(lambda host: get_kavlan_host_name(host,
                    kavlan), resources[site]['hosts'])


for host in hosts:
    site = get_host_site(host)
    if state.find("./site[@id='" + site+ "']"):
        el_site = state.find("./site[@id='" + site+ "']")
    else:
        el_site = SubElement(state, 'site', attrib={'id': site})
    cluster = get_host_cluster(host)
    if el_site.find("./cluster[@id='" + cluster + "']"):
        el_cluster = el_site.find("./cluster[@id='" + cluster+ "']")
    else: 
        el_cluster =  SubElement(el_site, 'cluster', attrib={'id': cluster})
    SubElement(el_cluster, 'host', attrib={'id': host})



while True:
    for host, vms in list_vm(hosts).iteritems():
        el_host = state.find(".//host/[@id='" + host + "']")
        for vm in vms:
            SubElement(el_host, 'vm', attrib={'id': vm['id']})
    topology_plot(state, show=True)
    for vm in state.findall('vm'):
        root.remove(vm)
        





