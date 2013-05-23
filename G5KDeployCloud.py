#!/usr/bin/env python
#-*- coding: utf-8 -*-

import time as T, datetime as DT, execo.time_utils as EXT
import argparse, time, random
from json import loads
from pprint import pprint, pformat
from netaddr import IPNetwork
import xml.etree.ElementTree as ET
from execo import configuration, logger, Remote, Put, Get, Host
from execo.log import set_style
from execo_g5k import get_oargrid_job_nodes, get_oargrid_job_info, wait_oargrid_job_start, get_oargrid_job_oar_jobs, get_oar_job_kavlan, oargridsub
from execo_g5k.oar import format_oar_date, oar_duration_to_seconds, OarSubmission       
from execo_g5k.config import g5k_configuration, default_frontend_connexion_params
from execo_g5k.api_utils import  get_host_attributes, get_g5k_sites, get_site_clusters, get_cluster_attributes
from execo_g5k.planning import Planning

from setup_cluster import Virsh_Deployment, get_clusters
from state import *


# Constants
max_vms = 10230
oargridsub_opts = '-t deploy'

# Defining the options 
parser = argparse.ArgumentParser(
        prog = set_style('G5KDeployCloud.py', 'log_header'),
        description = 'A tool to deploy and configure nodes and virtual machines '
        +'with '+set_style('Debian', 'object_repr')+' and '+set_style('libvirt', 'object_repr')+\
        '\non the '+set_style('Grid5000', 'log_header')+' platform in a global '+set_style('KaVLAN','object_repr')+\
        '.\n\nRequire '+set_style('execo-2.2', 'log_header')+'.',
        epilog = """Example : G5KCloudDeploy -n 100 will install 100 VM with the default 
        environnements for 3h """,
        formatter_class=argparse.RawTextHelpFormatter
        )

resources = parser.add_argument_group('Ressources',
                set_style('n_vm + walltime', 'user3')+'\nperform a G5K reservation that has enough RAM for the virtual machine'+\
                '\n'+set_style('n_vm + oargrid_job_id', 'user3')+'\nuse an existing reservation and create the virtual machine on the hosts'+\
                '\n'+set_style('infile + walltime', 'user3')+'\ndeploy virtual machines and hosts according to a placement XML file for a given walltime'+\
                '\n'+set_style('infile + oargrid_job_id', 'user3')+'\nusing a existing reservation to deploy virtual machines and hosts according to a placement XML file'
                )                                      
g1 = resources.add_mutually_exclusive_group()
g1.add_argument('-n', '--n_vm',
                    dest = 'n_vm',
                    type = int,
                    help = 'number of virtual machines'
                    )
g1.add_argument('-i', '--infile',
                    dest = "infile",
                    help = 'XML file describing the placement of VM on G5K sites and clusters' )
g2 = resources.add_mutually_exclusive_group()
g2.add_argument('-j', '--oargrid_job_id',
                    dest = 'oargrid_job_id',
                    help = 'use the hosts from a oargrid_job' )
g2.add_argument('-w', '--walltime',
                    dest = 'walltime',
                    default = '3:00:00',
                    help = 'duration of your reservation')

hosts = parser.add_argument_group('Physical hosts')
host_env = hosts.add_mutually_exclusive_group()
host_env.add_argument('-h_env', '--host_env_name', 
                    dest = 'env_name',
                    default = 'squeeze-x64-prod',
                    help = 'Kadeploy environment NAME for the physical host')
host_env.add_argument('-h_enf', '--host_env_file', 
                    dest = 'env_file',
                    help = 'Kadeploy environment FILE for the physical host')
elements = hosts.add_mutually_exclusive_group()
elements.add_argument('-c', '--clusters', 
                    dest = 'clusters',
                    nargs = '*',
                    help = 'list of clusters')
elements.add_argument('-s', '--sites', 
                    dest = 'sites',
                    nargs = '*',
                    help = 'list of sites')
vms = parser.add_argument_group('Virtual machines')
vms.add_argument('-v_f', '--vm_file', 
                    dest = 'vm_env_file',
                    default = 'squeeze-x64-base.qcow2',
                    help = 'backing file for your virtual machines')
vms.add_argument('-v_t', '--vm_template', 
                    dest = 'vm_template',
                    help = 'XML file describing the virtual machine')

log_level = parser.add_mutually_exclusive_group()
log_level.add_argument("-v", "--verbose", 
                       action = "store_true", 
                       help = 'print debug messages')
log_level.add_argument("-q", "--quiet", 
                       action = "store_true",
                       help = 'print only warning and error messages')
args = parser.parse_args()

# Setting log level
if args.verbose:
    logger.setLevel('DEBUG')
elif args.quiet:
    logger.setLevel('WARN')
else:
    logger.setLevel('INFO')
logger.info('\n\n    Starting %s for the creation of virtual machines on Grid5000\n', set_style('G5KCloudDeploy.py', 'log_header'))
logger.info(set_style('Initialization ... ', 'log_header'))

# Analyzing the options
n_vm = 0
vm_template = None
vm_ram_size = 0
required_ram = 0
placement = None
clusters = []
sites = []
if args.infile is None:
    if args.n_vm is None:
        logger.error('Must specify the number of virtual machines or give a placement file, use -h for help')
        exit()
    else:
        n_vm = args.n_vm 
        if args.vm_template is None:
            vm_template = ET.fromstring('<vm mem="1024" hdd="2" cpu="1" cpuset="auto" />')
        else:
            vm_template = ET.parse( args.vm_template ).getroot()
        vm_ram_size = int(vm_template.get('mem'))
        required_ram = n_vm * vm_ram_size
    
    if args.sites is None:
        if args.clusters is not None:
            clusters = args.clusters
        else: 
            logger.info('Getting clusters with virtualization technology and kavlan')
            clusters = get_clusters(virt = True, kavlan = True)
        
        for cluster in clusters:
            site_cluster = get_cluster_site(cluster)
            if site_cluster not in sites :
                sites.append(site_cluster)
    else: 
        sites = args.sites
        clusters = get_clusters(sites, virt = True, kavlan = True)
    
else:
    logger.info('Using an input file for the placement: %s', set_style(args.infile, 'emph'))
    placement = ET.parse(args.infile)
    for vm in placement.findall('.//vm'):
        n_vm += 1
        required_ram += int(vm.get('mem'))
    for site in placement.findall('.//site'):
        sites.append(site.get('id'))
    for cluster in placement.findall('.//cluster'):
        clusters.append(cluster.get('id'))

## MANUAL CORRECTION DUE TO G5K BUGS
error_clusters = ['stremi']#, 'chinqchint', 'chimint', 'chirloute']
for cluster in error_clusters:
    if cluster in clusters:
        clusters.remove(cluster)
        logger.warn('DUE TO G5K BUGS, %s HAS BEEN REMOVED ', cluster)
if len(clusters) == 0:
    logger.error('No cluster defined, aborting')
    exit()
error_sites = [ 'reims', 'bordeaux', 'grenoble' ]#, 'lille' ]
for site in error_sites:
    if site in sites:
        sites.remove(site)
        logger.warn('DUE TO KAVLAN-GLOBAL PROBLEMS, %s HAS BEEN REMOVED ', site)
if len(sites) == 0:
    logger.error('No sites defined, aborting')
    exit()



# Displaying options
logger.info('Number of virtual machines: %s', set_style(n_vm, 'emph'))
logger.info('Sites: %s', set_style(', '.join([site for site in sites]), 'emph') )
clusters_ram = { cluster: get_host_attributes(cluster+'-1')['main_memory']['ram_size']/2**20 for cluster in clusters  }
logger.info('Clusters: %s', set_style(', '.join( [ cluster+' ('+str(ram)+'MB)' for cluster, ram in clusters_ram.iteritems()]), 'emph') )
if vm_template is not None:
    logger.info('VM template: %s', set_style(ET.tostring(vm_template), 'emph'))
else:
    logger.info('Using specific template for each VM template')
if placement is None:
    logger.info('Total RAM required %s MB', set_style(required_ram, 'emph'))
else:
    logger.info('Validating RAM amount on each host')
    for cluster in placement.findall('.//cluster'):
        host_ram = clusters_ram[cluster.get('id')]
        for host in cluster.findall('./host'):                
            host_vms_ram = 0
            for vm in host.findall('./vm'):
                host_vms_ram += int(vm.get('mem'))
            if host_vms_ram > host_ram:
                logger.error('Not enough ram on %s for the VM you define', host.get('id'))
                exit()
logger.info(set_style('Done\n', 'log_header'))

# Managing reservation
logger.info(set_style('Checking the reservation parameters ...', 'log_header'))

if args.oargrid_job_id is None:
    walltime = args.walltime
    logger.info('No oargrid_job_id given, finding a slot and performing a reservation')
    starttime = T.time()
    endtime = starttime + EXT.timedelta_to_seconds(DT.timedelta(days = 2))
    planning = Planning( clusters, starttime, endtime )
    planning.compute_slots()
    slots_ok = []
    for slot, resources in planning.slots.iteritems():
        slot_ram = 0
        slot_node = 0 
        for resource, n_node in resources.iteritems():
            if resource in clusters:
                slot_ram += n_node * clusters_ram[resource]
                slot_node += n_node    
        if required_ram < slot_ram and slot[1]-slot[0] > oar_duration_to_seconds(walltime):
            slots_ok.append(slot)
    
    slots_ok.sort()
    slot = {}
    tmp_slot = planning.slots[slots_ok[0]]
    for res, n_nodes in tmp_slot.iteritems():
        if res in clusters and n_nodes > 0:
            slot[res] = n_nodes
    cluster_nodes = { cluster:0 for cluster in slot.iterkeys()}    
    iter_cluster = cycle(slot.iterkeys())
    cluster = iter_cluster.next()
    node_ram = 0
    for i_vm in range(n_vm):
        node_ram += vm_ram_size
    
        if node_ram + vm_ram_size > clusters_ram[cluster]:            
            node_ram = 0
            cluster_nodes[cluster] += 1
            cluster = iter_cluster.next()
            while cluster_nodes[cluster] >= slot[cluster]:
                cluster = iter_cluster.next()
    cluster_nodes[cluster] += 1
    slot_ram = 0
    for cluster, n_nodes in cluster_nodes.iteritems():
        slot_ram += n_nodes * clusters_ram[cluster]
    
    logger.info('Finding the kavlan_site')
    get_jobs = Remote('oarstat -J -f', [ Host(site+'.grid5000.fr') for site in sites], 
                      connexion_params = default_frontend_connexion_params ).run()
    for p in get_jobs.processes():
        site_jobs = loads(p.stdout())
        site_free = True
        for job_id, info in site_jobs.iteritems():
            if 'kavlan-global' in info['wanted_resources']:
                site_free = False 
        if site_free:
            kavlan_site = p.host().address.split('.')[0]
    logger.info('kavlan_site %s', set_style(str(kavlan_site), 'emph'))
    
    
    subs = []
    for site in sites:
        sub_resources=''
        if site == kavlan_site:
            sub_resources="{type=\\'kavlan-global\\'}/vlan=1+"
            getkavlan = False
        for cluster in get_site_clusters(site):
            if cluster_nodes.has_key(cluster) and cluster_nodes[cluster]:
                sub_resources += "{cluster=\\'"+cluster+"\\'}/nodes="+str(cluster_nodes[cluster])+'+'
        subs.append((OarSubmission(resources=sub_resources[:-1]),site))
    logger.info('Performing the reservation')
    (oargrid_job_id, _) = oargridsub(subs, walltime = walltime, additional_options = oargridsub_opts,
                                     reservation_date = format_oar_date(slots_ok[0][0]))
else:
    logger.info('Using '+set_style(str(args.oargrid_job_id), 'emph')+' job')
    oargrid_job_id = args.oargrid_job_id
    

jobinfo = get_oargrid_job_info(oargrid_job_id)
logger.info('jobinfo \n%s', pformat(jobinfo))

if jobinfo['start_date'] > time.time():
    logger.info('Job %s is scheduled for %s, waiting ... ', set_style(oargrid_job_id, 'emph'), 
            set_style(format_oar_date(jobinfo['start_date']), 'emph') )
    wait_oargrid_job_start(oargrid_job_id)
    if time.time() > jobinfo['start_date'] + jobinfo['walltime']:
        logger.error('Job %s is already finished, aborting', set_style(oargrid_job_id, 'emph'))
        exit()
logger.info('Job has started !')    

logger.info('Getting the list of hosts')
hosts = get_oargrid_job_nodes( oargrid_job_id )
hosts.sort()
logger.info('%s', ", ".join( [set_style(host.address.split('.')[0], 'host') for host in hosts] ))

max_flops = 0
fastest_host = ''
for host in hosts:
    try:
        host_flops = get_host_attributes(host)['performance']['node_flops']
        if host_flops > max_flops:
            max_flops = host_flops
            fastest_host = host
    except:
        logger.warning('No performance entry in API for host %s', set_style(host.address, 'host'))
        pass 

logger.info('Checking the number of VMs')

total_attr = {'ram_size': 0, 'n_cpu': 0}
hosts_attr = {}
for host in hosts:
    attr = get_host_attributes(host)
    hosts_attr[host.address] = {'node_flops': attr['performance']['node_flops'] if attr.has_key('performance') else None, 
                               'ram_size': attr['main_memory']['ram_size'],
                               'n_cpu': attr['architecture']['smt_size'] }
    total_attr['ram_size'] += attr['main_memory']['ram_size']
    total_attr['n_cpu'] += attr['architecture']['smt_size']

if n_vm > max_vms:
    logger.warning('Reducing the number of virtual machines to %s, due to the'+\
                 ' number of available IP in the KaVLAN global', set_style(max_vms, 'report_error') )
    n_vm = max_vms

max_vms = min (max_vms, total_attr['ram_size']/2**10/vm_ram_size)

if n_vm > max_vms:
    logger.warning('Reducing the number of virtual machines to %s, due to the'+\
                 ' total amount of RAM available (%s) and the ram size of the VM (%s)', 
                 set_style(str(max_vms), 'report_error'), set_style(str(total_attr['ram_size']/10**6)+'MB', 'emph'),
                 set_style(str(vm_ram_size)+'MB', 'emph'))
    n_vm = max_vms 
logger.info('You can run %s VM on the hosts you have', max_vms)


logger.info(set_style('Reservation is OK and parameters have been checked !\n', 'report_error'))




    

logger.info(set_style('Network configuration', 'log_header'))

logger.info('Looking for a KaVLAN network')
subjobs = get_oargrid_job_oar_jobs(oargrid_job_id)
for subjob in subjobs:
    vlan = get_oar_job_kavlan(subjob[0], subjob[1])
    if vlan is not None: 
        kavlan_id = vlan
        logger.info('found on site %s with id %s', set_style(subjob[1], 'emph'), 
                    set_style(kavlan_id, 'emph') )
        break
    else:
        logger.info('%s, not found', subjob[1])
if kavlan_id is None:
    logger.error('No KaVLAN found, aborting ...')
    exit()

logger.info('Obtaining IP and MAC for the virtual machine')
vm_ip = []
all_ip = IPNetwork('10.'+str(3+(kavlan_id-10)*4)+'.216.0/18')
subnets = list(all_ip.subnet(21))
for subnet in subnets:
    if subnet.ip.words[2] >= 216:
        for ip in subnet.iter_hosts():
            vm_ip.append(ip)

network = str(min(vm_ip))+','+str(max(vm_ip[0:-1]))+','+str(all_ip.netmask)
logger.info(set_style(network, 'emph') )
dhcp_range = 'dhcp-range='+network+',12h\n'
dhcp_router = 'dhcp-option=option:router,'+str(max(vm_ip))+'\n'
dhcp_hosts ='' 
ip_mac = []    
for ip in vm_ip[0:n_vm]:
    mac = [ 0x00, 0x16, 0x3e,
    random.randint(0x00, 0x7f),
    random.randint(0x00, 0xff),
    random.randint(0x00, 0xff) ]
    ip_mac.append( ( str(ip), ':'.join( map(lambda x: "%02x" % x, mac) ) ) )
    dhcp_hosts += 'dhcp-host='+':'.join( map(lambda x: "%02x" % x, mac))+','+str(ip)+'\n'


part_host = fastest_host.address.partition('.')
service_node = part_host[0]+'-kavlan-'+str(kavlan_id)+part_host[1]+ part_host[2]

get_ip = SshProcess('host '+service_node+' |cut -d \' \' -f 4', g5k_configuration['default_frontend'], 
        connexion_params = default_frontend_connexion_params).run()



logger.info('Writing configurations files')
f = open('resolv.conf', 'w')
f.write('domain grid5000.fr\nsearch '+' '.join( [ site+'.grid5000.fr' for site in get_g5k_sites() ])+'\nnameserver '+get_ip.stdout().strip())
f.close()
f = open('dnsmasq.conf', 'w')
f.write(dhcp_range+dhcp_router+dhcp_hosts)
f.close()
f = open('vms.list', 'w')
for idx, val in enumerate(ip_mac):
    f.write(val[0]+'     vm-'+str(idx)+'\n')
f.close()



logger.info(set_style('Network has been configured !\n', 'report_error'))



logger.info(set_style('Physical hosts configuration', 'log_header'))
    




setup_hosts = Virsh_Deployment( hosts, kavlan = kavlan_id)
if args.env_file is not None:
    setup_hosts.env_file = args.env_file 
else:
    setup_hosts.env_name = args.env_name
setup_hosts.deploy_hosts( num_tries = 1)
setup_hosts.rename_hosts()

hosts = list(setup_hosts.hosts)

logger.info('%s', ", ".join( [set_style(host.address.split('.')[0], 'host') for host in hosts] ))
setup_hosts.upgrade_hosts()
setup_hosts.install_packages()
setup_hosts.configure_libvirt()
setup_hosts.create_disk_image(clean = True)
setup_hosts.copy_ssh_keys()

f = open('hosts.list', 'w')
for host in hosts:
    f.write(host.address+'\n')
f.close()


logger.info('Configuring %s as a %s server for the virtual machines', 
            set_style(service_node.split('.')[0], 'host'), set_style('DNS/DCHP', 'emph'))

Remote('export DEBIAN_MASTER=noninteractive ; apt-get install -y dnsmasq taktuk', [service_node]).run()
Put([service_node], 'dnsmasq.conf', remote_location='/etc/').run()

logger.info('Adding the VM in /etc/hosts ...')
Put([service_node], 'vms.list', remote_location= '/root/').run()
Remote('cat /root/vms.list >> /etc/hosts', [service_node]).run()

logger.info('Restarting service ...')
Remote('service dnsmasq restart', [service_node]).run()

logger.info('Configuring resolv.conf on all hosts')
clients = hosts[:]
clients.remove(Host(service_node))
Put(clients, 'resolv.conf', remote_location = '/etc/').run()

#logger.info('Copying the % s images on % s')
#Remote('scp /grid5000/images/KVM/squeeze-x64-base.qcow2 root@'+service_node+':', [Host('lyon.g5k')],
#       connexion_params = {'user': 'lpouilloux'}).run()
#
#Remote('taktuk -m '+' -m'.join([host.address for host in hosts] )+' put squeeze-x64-base.qcow2 /tmp/', service_node)

logger.info(set_style('Hosts configuration complete !\n', 'report_error'))


logger.info(set_style('Virtual machines configuration', 'log_header'))    
logger.info('Defining the virtual machines')
vms = define_vms(n_vm, ip_mac, mem_size = vm_ram_size)


logger.info('Distributing the virtual machines on all physical hosts')
vms = distribute_vms_on_hosts(vms, hosts)

logger.info('Creating the qcow2 disks on hosts')
disk_creation = create_disks_hosts(vms).run()


logger.info('Destroying existing virtual machines')
destroy_all(hosts)


logger.info('Installing the virtual machines')
install_vms(vms).run()

logger.info('Starting the virtual machines')
start_vms(vms).run()
wait_vms_have_started(vms, service_node)

listing = ''
for host in hosts:
    host_vm = list_vm(host)
    listing += '\n'+host.address+': '+', '.join( [ vm['vm_id'] for vm in host_vm ])
logger.info('Listing VM %s', listing)

