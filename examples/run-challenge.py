#!/usr/bin/env python
#-*- coding: utf-8 -*-
from os import path, mkdir
from time import time
from pprint import pformat, pprint
from execo import configuration, Put, Get, Remote, SequentialActions, ParallelActions, Host
from execo_g5k.oar import format_oar_date
from execo_g5k import OarSubmission, oargridsub, oargriddel, wait_oargrid_job_start, get_oargrid_job_nodes, get_oar_job_subnets, get_oar_job_info
from execo_g5k.vmutils import *
from execo_g5k.planning import *
from execo_g5k.config import default_frontend_connexion_params
from execo_g5k.api_utils import get_site_clusters
from execo_engine import Engine, ParamSweeper, sweep, slugify, logger


logger.setLevel('INFO')

n_nodes = 1
n_vm = 4 
walltime ='1:00:00'
oargridsub_opts = '-t deploy'
    
logger.info('Getting all clusters with virtualization and KaVLAN')
sites = get_kavlan_sites()


clusters = get_virt_clusters(sites)
logger.info('%s', ', '.join([cluster for cluster in clusters]))
resources = { cluster: n_nodes for cluster in clusters }
# TO BE REMOVED
sites.remove('toulouse')
sites.remove('nancy')
del resources['pastel']
del resources['graphene']
del resources['griffon']
del resources['orion']
del resources['chirloute']
del resources['taurus']
#

logger.info('Finding a slot for the challenge and making the reservation')
starttime = T.time()
endtime = starttime + ET.timedelta_to_seconds(DT.timedelta(days=1))

planning = Planning(clusters, starttime, endtime)
planning.find_slots('free', walltime, resources)

start_time = 10**20
for slot in planning.slots_ok.iteritems():
    if slot[0][0] < start_time:
        start_time = slot[0][0] 
start_date = format_oar_date(start_time)

logger.info('Job is scheduled for %s', start_date)
subs = []
getkavlan = True
for site in sites:
    sub_resources=''
    if getkavlan:
        sub_resources="{type=\\'kavlan-global\\'}/vlan=1+slash_22=1+"
        getkavlan = False
    for cluster in get_site_clusters(site):
        if resources.has_key(cluster):
            sub_resources += "{cluster=\\'"+cluster+"\\'}/nodes="+str(resources[cluster])+'+'
    subs.append((OarSubmission(resources=sub_resources[:-1]),site))
    
#pprint (subs)
(oargrid_job_id, _) = oargridsub(subs, walltime = walltime, additional_options = oargridsub_opts, 
                                                            reservation_date = start_date)

hosts = get_oargrid_job_nodes( oargrid_job_id )
logger.info('Reservation done, hosts: %s', ", ".join( [host.address for host in hosts] ))


wait_oargrid_job_start( oargrid_job_id )
oargriddel( [oargrid_job_id] )

exit()

logger.info('Resa %s', oargrid_job_id)
subjobs = EX5.get_oargrid_job_oar_jobs(oargrid_job_id)

logger.info('Subjobs: \n%s', PP.pformat(subjobs))

for subjob in subjobs:
    logger.info('Looking for KaVLAN on site: %s ', subjob[1])
    test_vlan = EX5.get_oar_job_kavlan(subjob[0], subjob[1])
    if test_vlan is not None: 
        kavlan_id = test_vlan
        kavlan_frontend = subjob[1]+'.grid5000.fr'
        kavlan_job = subjob[0]
        logger.info('KaVLAN found on site: %s with id %s',kavlan_frontend,kavlan_id)
        break

hosts = EX5.get_oargrid_job_nodes([oargrid_job_id])



      

#
#
#
#
SetupHosts = VM.SetupKVMHosts( hosts, kavlan_id)
SetupHosts.deploy_hosts()
SetupHosts.rename_hosts()
hosts = SetupHosts.hosts
SetupHosts.setup_packages()
SetupHosts.create_disk_image()

[ip_mac, params] = EX5.get_oar_job_subnets(kavlan_job, kavlan_frontend)

root = ET.Element('network')
name = ET.SubElement(root,'name')
name.text = 'default'
ET.SubElement(root, 'bridge', attrib = {'name': 'virbr0'})
ET.SubElement(root, 'forward', attrib = {'mode':'nat'})
ip = ET.SubElement(root, 'ip', attrib = {'address': ip_mac[0][0], 'netmask': params['netmask']})
dhcp = ET.SubElement(ip, 'dhcp')
ET.SubElement(dhcp, 'range',  attrib={'start': ip_mac[1][0],'end': ip_mac[n_vm*len(hosts)][0]})  
for i_vm in range(n_vm*len(hosts)):
        ET.SubElement(dhcp,'host', attrib = {
                                           'ip':           ip_mac[i_vm+1][0], 
                                           'mac':       ip_mac[i_vm+1][1],
                                           'name':    'vm-'+str(i_vm)})
ET.dump(root, pretty_print = True)

SetupHosts.libvirt_network(root)
SetupHosts.copy_ssh_keys()


i_vm = 0
i_host =0
vms_params ={}

for host in hosts:
    vms_params[host]=[]
    for i in range(n_vm):
        vms_params[host].append({
                                'hdd_size': 2, 
                                'vm_id': 'vm-'+str(i_vm+n_vm*i_host), 
                                'ip': ip_mac[i_vm+n_vm*i_host][0], 
                                'mac': ip_mac[i_vm+n_vm*i_host][1], 
                                'mem_size': 256, 
                                'vcpu': 1 })
        i_vm +=1
    i_host+=1
        
#PP.pprint(vms_params)

VM_install=[]
for host, vms in vms_params.iteritems():
    hosts_actions=[]
    for vm in vms:
        cmd = 'virsh destroy '+vm['vm_id']+'; virsh undefine '+vm['vm_id']+'; rm /tmp/'+vm['vm_id']+'.img'
        logger.info('Cleaning VM on host '+host.address)
        EX.Remote(cmd, [host]).run()
        
        VM_test = VM.VM(vm,[ host])
        hosts_actions.append(VM_test.install())
    VM_install.append(EX.SequentialActions(hosts_actions))
        
#PP.pprint(VM_install)

logger.info('Creating all VM on ALL hosts '+host.address)
EX.ParallelActions(VM_install).run()

SetupHosts.list_vm()
#VM_test = VM.VM(vm_params,hosts)



