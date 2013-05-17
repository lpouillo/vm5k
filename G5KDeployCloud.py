#!/usr/bin/env python
#-*- coding: utf-8 -*-

import argparse, time, random
from pprint import pprint, pformat
from netaddr import IPNetwork
from execo import configuration, logger, Remote, Put, Get, Host
from execo.log import set_style
from execo_g5k import get_oargrid_job_nodes, get_oargrid_job_info, wait_oargrid_job_start, get_oargrid_job_oar_jobs, get_oar_job_kavlan, get_host_attributes
from execo_g5k.oar import format_oar_date        

from setup_cluster import Virsh_Deployment
from state import *


# Limits
max_vms = 10230
vm_ram_size = 1024

# Defining the options 
parser = argparse.ArgumentParser(
        prog = set_style('G5KCloudDeploy', 'log_header'),
        description = 'A tool to deploy and configure nodes and virtual machines '
        +'with '+set_style('Debian', 'object_repr')+' and '+set_style('libvirt', 'object_repr')+\
        ' on the '+set_style('Grid5000', 'log_header')+' platform.'+\
        ' Based on '+set_style('execo-2.2', 'object_repr'),
        epilog = """Example : G5KCloudDeploy 100 -c stremi,suno,granduc will install 100 VM with the default 
        environnements on the cited clusters in a given KaVLAN """
        
        )
parser.add_argument('n_vm', 
                    default = 100,
                    help = 'number of virtual machines')
hosts_groups = parser.add_mutually_exclusive_group()
hosts_groups.add_argument('-n', '--nodes', type = int, 
                    dest = "n_nodes",
                    default = 10,  
                    help = 'number of hosts')
hosts_groups.add_argument('-j', '--job_id', type = int, 
                    dest = "oargrid_job_id",
                    default = None,  
                    help = 'use the host from a oargrid_job')
host_env = parser.add_mutually_exclusive_group()
host_env.add_argument('-h_env', '--host_env_name', 
                    dest = 'host_env_name',
                    #default = 'wheezy-x64-nfs',
                    default = 'squeeze-x64-prod',
                    help = 'Kadeploy environment NAME for the physical host')
host_env.add_argument('-h_enf', '--host_env_file', 
                    dest = 'host_env_file',
                    #default = 'wheezy-x64-nfs',
                    default = None,
                    help = 'Kadeploy environment FILE for the physical host')
parser.add_argument('-vf', '--vm_file', 
                    dest = 'vm_env_file',
                    default = 'squeeze-x64-base.qcow2',
                    help = 'backing file for your virtual machines')
parser.add_argument('-c', '--clusters', 
                    dest = 'clusters',
                    default = None,
                    help = 'comma separated list of clusters')
parser.add_argument('-s', '--sites', 
                    dest = 'sites',
                    default = None,
                    help = 'comma separated list of sites')
log_level = parser.add_mutually_exclusive_group()
log_level.add_argument("-v", "--verbose", action="store_true")
log_level.add_argument("-q", "--quiet", action="store_true")
args = parser.parse_args()

#for key, value in args.__dict__.items():
#    print key+' = '+str(value)
#exit()



if args.verbose:
    logger.setLevel('DEBUG')
elif args.quiet:
    logger.setLevel('WARN')
else:
    logger.setLevel('INFO')



logger.info('\n\n    Starting %s for the creation of virtual machines\n', set_style('G5KCloudDeploy', 'log_header'))
logger.info(set_style('Initializing ... ', 'log_header'))


if args.oargrid_job_id is None:
    logger.info('No oargrid_job_id given, performing a Grid reservation')
    logger.error('NOT YET IMPLEMENTED')
    exit()
else:
    logger.info('Using '+set_style(str(args.oargrid_job_id), 'emph')+' job')
    oargrid_job_id = args.oargrid_job_id

    
logger.info('Checking the reservation parameters')
jobinfo = get_oargrid_job_info(oargrid_job_id)
logger.debug('jobinfo \n%s', pformat(jobinfo))

logger.info('Getting the list of hosts')
hosts = get_oargrid_job_nodes( args.oargrid_job_id )
hosts.sort()
logger.info('%s', ", ".join( [set_style(host.address.split('.')[0], 'host') for host in hosts] ))

logger.info('Checking the number of VMs')
n_vm = int(args.n_vm)
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

max_vms = min (max_vms, total_attr['ram_size']/10**6/vm_ram_size)

if n_vm > max_vms:
    logger.warning('Reducing the number of virtual machines to %s, due to the'+\
                 ' total amount of RAM available (%s) and the ram size of the VM (%s MB)', 
                 set_style(str(max_vms), 'report_error'), set_style(str(total_attr['ram_size']/10**6)+'MB', 'emph'),
                 set_style(str(vm_ram_size)+'MB', 'emph'))
    n_vm = max_vms 
logger.info('You can run %s VM on the hosts you have')



if jobinfo['start_date'] > time.time():
    logger.info('Job %s is scheduled for %s, waiting ... ', set_style(oargrid_job_id, 'emph'), 
            set_style(format_oar_date(jobinfo['start_date']), 'emph') )
    wait_oargrid_job_start(oargrid_job_id)
logger.info(set_style('Job has started !\n', 'report_error'))    

    

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

logger.info('Writing configurations files for the DNS/DHCP server')
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
if args.host_env_file is not None:
    setup_hosts.env_file = args.host_env_file 
else:
    setup_hosts.env_name = args.host_env_name
setup_hosts.deploy_hosts( num_tries = 1)
setup_hosts.rename_hosts()

hosts = list(setup_hosts.hosts)

logger.info('%s', ", ".join( [set_style(host.address.split('.')[0], 'host') for host in hosts] ))
setup_hosts.setup_packages()
setup_hosts.configure_libvirt()
setup_hosts.create_disk_image(clean = True)
setup_hosts.copy_ssh_keys()

f = open('hosts.list', 'w')
for host in hosts:
    f.write(host.address+'\n')
f.close()


max_flops = 0
fastest_host = ''
for host in hosts:
    try:
        host_flops = get_host_attributes(kavname_to_shortname(host))['performance']['node_flops']
        if host_flops > max_flops:
            max_flops = host_flops
            fastest_host = host
    except:
        logger.warning('No performance entry in API for host %s', set_style(host.address, 'host'))
        pass 
part_host = fastest_host.address.partition('.')
service_node = part_host[0]+'-kavlan-'+str(kavlan_id)+part_host[1]+ part_host[2]
logger.info('Configuring %s as a %s server for the virtual machines', 
            set_style(service_node.split('.')[0], 'host'), set_style('DNS/DCHP', 'emph'))


Remote('export DEBIAN_MASTER=noninteractive ; apt-get install -y dnsmasq taktuk', [service_node]).run()
Put([service_node], 'dnsmasq.conf', remote_location='/etc/').run()

logger.info('Adding the VM in /etc/hosts ...')
Put([service_node], 'vms.list', remote_location= '/root/').run()
Remote('cat /root/vms.list >> /etc/hosts', [service_node]).run()

logger.info('Restarting service ...')
Remote('service dnsmasq restart', [service_node]).run()

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
    listing += '- '+host.address+', '.join( [ vm['vm_id'] for vm in host_vm ])
logger.info('Listing VM\n %s', listing)

