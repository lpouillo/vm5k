#!/usr/bin/env python
#-*- coding: utf-8 -*-

import time as T, datetime as DT, execo.time_utils as EXT
import argparse, time, random, os

from json import loads
from copy import copy
from pprint import pprint, pformat
from netaddr import IPNetwork
from operator import itemgetter
try:
    import lxml.etree as ET
    with_lxml = True
except ImportError:
    pass
    print 'No lxml python module found, XML file will not be indented'
    with_lxml = False
    import xml.etree.ElementTree as ET


from execo import configuration, logger, Remote, Put, Get, Host, Timer
from execo.log import set_style
from execo_g5k import get_oargrid_job_nodes, get_oargrid_job_info, wait_oargrid_job_start, get_oargrid_job_oar_jobs, get_oar_job_kavlan, oargridsub
from execo_g5k.oar import format_oar_date, oar_duration_to_seconds, OarSubmission       
from execo_g5k.config import g5k_configuration, default_frontend_connexion_params
from execo_g5k.api_utils import  get_host_attributes, get_g5k_sites, get_site_clusters, get_cluster_attributes, get_cluster_site, get_host_site
from execo_g5k.planning import Planning
from execo_g5k.oargrid import get_oargridsub_commandline

from deployment import Virsh_Deployment, get_clusters
from state import *


# Constants
max_vms = 10230 # Limitations due to the number of IP address 
oargridsub_opts = '-t deploy'
default_vm_template = '<vm mem="1024" hdd="2" cpu="1" cpuset="auto" />'

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
                    help = 'topology file describing the placement of VM on G5K sites and clusters' )
g2 = resources.add_mutually_exclusive_group()
g2.add_argument('-j', '--oargrid_job_id',
                    dest = 'oargrid_job_id',
                    type = int,
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
vms.add_argument('-v_f', '--vm_backing_file', 
                    dest = 'vm_backing_file',
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


timer = Timer()
execution_time = {}
if args.verbose:
    logger.setLevel('DEBUG')
elif args.quiet:
    logger.setLevel('WARN')
else:
    logger.setLevel('INFO')
logger.info('\n\n    Starting %s for the creation of virtual machines on Grid5000\n', set_style('G5KCloudDeploy.py', 'log_header'))
n_vm = 0
sites = []
clusters = []
kavlan_site = None
placement = None
outdir = 'deploycloud_'+ time.strftime("%Y%m%d_%H%M%S_%z")
try:
    os.mkdir(outdir)
except os.error:
    pass

logger.info(set_style('DEPLOYMENT TOPOLOGY', 'log_header'))
if args.infile is None:
    if args.n_vm is None:
        logger.error('Must specify the number of virtual machines or give a placement file, use -h for help')
        exit()
    else:
        n_vm = args.n_vm 
        if args.vm_template is None:
            vm_template = ET.fromstring(default_vm_template)
        else:
            vm_template = ET.parse( args.vm_template ).getroot()
        logger.info('No topology file given, will create %s vms using \ntemplate %s', set_style(str(n_vm), 'emph'),
                     set_style(ET.tostring(vm_template), 'emph'))
        vm_ram_size = int(vm_template.get('mem'))
        if args.oargrid_job_id is not None:
            logger.info('Will use the existing reservation for sites and clusters')
        else:
            logger.info('No reservation given, gathering sites and clusters ...')
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
            logger.info('sites: %s', set_style(', '.join([site for site in sites]), 'emph') )
            logger.info('clusters: %s', set_style(', '.join( [ cluster for cluster in clusters]), 'emph') )

else:
    n_vm = 0
    placement = ET.parse(args.infile)
    log = 'Using an input file for the placement: '+ set_style(args.infile, 'emph')
    for site in placement.findall('./site'):
        sites.append(site.get('id'))
        log += '\n'+site.get('id')+': '
        for cluster in site.findall('./cluster'):
            clusters.append(cluster.get('id'))
            log += cluster.get('id')+' ('+str(len(cluster.findall('.//host')))+' hosts - '+str(len(cluster.findall('.//vm')))+' vms) '
            n_vm += len(cluster.findall('.//vm'))
            
    logger.info(log)                       
    

## MANUAL CORRECTION DUE TO G5K BUGS
error_sites = [ 'rennes', 'reims', 'bordeaux', 'grenoble', 'sophia' ]#, 'lille' ]
for site in error_sites:
    if site in sites:
        sites.remove(site)
        logger.warn('DUE TO KAVLAN-GLOBAL PROBLEMS, %s HAS BEEN REMOVED ', site)
if len(sites) == 0 and args.oargrid_job_id is None:
    logger.error('No sites defined, aborting')
    exit()
    
    
error_clusters = map(lambda site: get_site_clusters(site), error_sites)

for cluster in error_clusters:
    if cluster in clusters:
        clusters.remove(cluster)
        logger.warn('DUE TO G5K BUGS, %s HAS BEEN REMOVED ', cluster)
if len(clusters) == 0 and args.oargrid_job_id is None:
    logger.error('No cluster defined, aborting')
    exit()

       
execution_time['1-topology'] = timer.elapsed()
logger.info(set_style('Done in '+str(round(execution_time['1-topology'],2))+' s\n', 'log_header'))
    
    
    
    
logger.info(set_style('GRID RESERVATION', 'log_header'))
if args.oargrid_job_id is not None:
    logger.info('Using '+set_style(str(args.oargrid_job_id), 'emph')+' job')
    oargrid_job_id = args.oargrid_job_id
else:
    logger.info('No oargrid_job_id given, finding a slot that suit your need')
    walltime = args.walltime
    starttime = T.time()
    endtime = starttime + EXT.timedelta_to_seconds(DT.timedelta(days = 2))
    planning = Planning( clusters, starttime, endtime )
    planning.compute_slots()
    
    if placement is not None:
        logger.info('Checking that the hosts have enough RAM')
        clusters_ram = { cluster.get('id'): get_host_attributes(cluster.get('id')+'-1')['main_memory']['ram_size']/2**20 for cluster in placement.findall('.//cluster')  }
        required_ram = sum([ int(vm.get('mem')) for vm in placement.findall('.//vm')])
        
        for host in placement.findall('.//host'):
            if clusters_ram[host.get('id').split('-')[0]] < sum([ int(vm.get('mem')) for vm in host.findall('./vm')]):
                logger.warning('Host '+host.get('id')+' has not enough RAM')  
        
        cluster_nodes ={ cluster.get('id'):len(cluster.findall('./host')) for cluster in placement.findall('.//cluster')}
        
        
        for slot in planning.slots:
            for cluster, n_nodes in cluster_nodes.iteritems():
                slot_ok = True
                if slot[2][cluster] < cluster_nodes[cluster]:
                    slot_ok = False    
        
            if slot_ok:
                chosen_slot = slot
                break

              
    
    else:        
        vm_ram_size = int(vm_template.get('mem'))
        required_ram = n_vm * vm_ram_size
        clusters_ram = { cluster: get_host_attributes(cluster+'-1')['main_memory']['ram_size']/2**20 for cluster in clusters  }
        slots_ok = []
        for slot in planning.slots:
            slot_ram = 0
            slot_node = 0 
            for resource, n_node in slot[2].iteritems():
                if resource in clusters:
                    slot_ram += n_node * clusters_ram[resource]
                    slot_node += n_node    
        
            if required_ram < slot_ram:
                slots_ok.append(slot)

        
        slots_ok.sort(key = itemgetter(0))
        chosen_slot = slots_ok[0]
        
        tmp_res = chosen_slot[2].copy() 
        for res in tmp_res.iterkeys():
            if res not in clusters:
                del chosen_slot[2][res]
        cluster_nodes = { cluster:0 for cluster in chosen_slot[2].iterkeys()}
            
        iter_cluster = cycle(chosen_slot[2].iterkeys())
        cluster = iter_cluster.next()
        node_ram = 0
        for i_vm in range(n_vm):
            node_ram += vm_ram_size
            if node_ram + vm_ram_size > clusters_ram[cluster]:            
                node_ram = 0
                if cluster_nodes[cluster] + 1 > chosen_slot[2][cluster]:
                    cluster = iter_cluster.next()
                cluster_nodes[cluster] += 1
                cluster = iter_cluster.next()
                while cluster_nodes[cluster] >= chosen_slot[2][cluster]:
                    cluster = iter_cluster.next()
        cluster_nodes[cluster] += 1
    
    logger.info('Finding a free kavlan global')
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
        if sub_resources != '':
            subs.append((OarSubmission(resources=sub_resources[:-1]),site))
    logger.info('Performing reservation \n%s ', 
                ", ".join([set_style(cluster, 'emph')+': '+ str(n_nodes) for cluster, n_nodes in cluster_nodes.iteritems() ]))
    
    
    logger.info( get_oargridsub_commandline(subs, walltime = walltime, additional_options = oargridsub_opts,
                                 reservation_date = format_oar_date(chosen_slot[0])) )
    
    (oargrid_job_id, _) = oargridsub(subs, walltime = walltime, additional_options = oargridsub_opts,
                                     reservation_date = format_oar_date(chosen_slot[0]))

jobinfo = get_oargrid_job_info(oargrid_job_id)

if jobinfo['start_date'] > time.time():
    logger.info('Job %s is scheduled for %s, waiting', set_style(oargrid_job_id, 'emph'), 
            set_style(format_oar_date(jobinfo['start_date']), 'emph') )
    if time.time() > jobinfo['start_date'] + jobinfo['walltime']:
        logger.error('Job %s is already finished, aborting', set_style(oargrid_job_id, 'emph'))
        exit()
else:
    logger.info('Start date = %s', format_oar_date(jobinfo['start_date']))
wait_oargrid_job_start(oargrid_job_id)
logger.info('Job '+set_style(str(oargrid_job_id), 'emph')+' has started, retrieving the list of hosts ...')    
        
hosts = get_oargrid_job_nodes( oargrid_job_id )
hosts.sort()
logger.info('Getting the attributes of \n%s', ", ".join( [set_style(host.address.split('.')[0], 'host') for host in hosts] ))
hosts_attr = {}
total_attr = {'ram_size': 0, 'n_cpu': 0}
for host in hosts:
    attr = get_host_attributes(host)
    hosts_attr[host.address] = {'node_flops': attr['performance']['node_flops'] if attr.has_key('performance') else 0, 
                               'ram_size': attr['main_memory']['ram_size'],
                               'n_cpu': attr['architecture']['smt_size'] }
    total_attr['ram_size'] += attr['main_memory']['ram_size']
    total_attr['n_cpu'] += attr['architecture']['smt_size']


if placement is not None:
    logger.info('Checking the correspondance between topology and reservation')
    tmp_hosts = map( lambda host: host.address.split('.')[0], hosts)
    
    for host_el in placement.findall('.//host'):
        
        if host_el.get('id') not in tmp_hosts:
            tmp = [h for h in tmp_hosts if host_el.get('id').split('-')[0] in h]
            host_el.attrib['id'] = tmp[0]
            tmp_hosts.remove(tmp[0])   
    
    
else:
    logger.info('No topology given, VMs will be distributed')
    if n_vm > max_vms:
        logger.warning('Reducing the number of virtual machines to %s, due to the'+\
                     ' number of available IP in the KaVLAN global', set_style(max_vms, 'report_error') )
        n_vm = max_vms
    
    max_vms = min (max_vms, total_attr['ram_size']/2**20/vm_ram_size)
    
    if n_vm > max_vms:
        logger.warning('Reducing the number of virtual machines to %s, due to the'+\
                     ' total amount of RAM available (%s) and the ram size of the VM (%s)', 
                     set_style(str(max_vms), 'report_error'), set_style(str(total_attr['ram_size']/10**6)+'MB', 'emph'),
                     set_style(str(vm_ram_size)+'MB', 'emph'))
        n_vm = max_vms 
    logger.info('You can run %s VM on the hosts you have', max_vms)


execution_time['2-reservation'] = timer.elapsed() - sum(execution_time.values())
logger.info(set_style('Done in '+str(round(execution_time['2-reservation'],2))+' s\n', 'log_header'))

logger.info(set_style('NETWORK', 'log_header'))
logger.info('Retrieving the KaVLAN id')
subjobs = get_oargrid_job_oar_jobs(oargrid_job_id)
if kavlan_site is None:
    for subjob in subjobs:
        vlan = get_oar_job_kavlan(subjob[0], subjob[1])
        if vlan is not None: 
            kavlan_id = vlan
            kavlan_site = subjob[1]
            
            break
        else:
            logger.info('%s, not found', subjob[1])
    if kavlan_id is None:
        logger.error('No KaVLAN found, aborting ...')
        exit()
else:
    for subjob in subjobs:
        if subjob[1] == kavlan_site:
            kavlan_id = get_oar_job_kavlan(subjob[0], subjob[1])

logger.info('id: %s, site: %s ', set_style(kavlan_id, 'emph'), 
                        set_style(subjob[1], 'emph') )

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
    mac = [ 0x00, 0x020, 0x4e,
    random.randint(0x00, 0x7f),
    random.randint(0x00, 0xff),
    random.randint(0x00, 0xff) ]
    ip_mac.append( ( str(ip), ':'.join( map(lambda x: "%02x" % x, mac) ) ) )
    dhcp_hosts += 'dhcp-host='+':'.join( map(lambda x: "%02x" % x, mac))+','+str(ip)+'\n'

logger.info('Determining the fastest host to create the service node')
max_flops = 0
for host, attr in hosts_attr.iteritems():
    if attr['node_flops'] > max_flops:
        max_flops = attr['node_flops']
        fastest_host = host
part_host = fastest_host.partition('.')
service_node = part_host[0]+'-kavlan-'+str(kavlan_id)+part_host[1]+ part_host[2]
get_ip = SshProcess('host '+service_node+' |cut -d \' \' -f 4', g5k_configuration['default_frontend'], 
        connexion_params = default_frontend_connexion_params).run()
logger.info('%s', service_node)

logger.info('Writing configurations files in %s', set_style(outdir, 'emph'))
f = open(outdir+'/hosts.list', 'w')
for host in hosts:
    part_host = host.address.partition('.')
    f.write(part_host[0]+'-kavlan-'+str(kavlan_id)+part_host[1]+ part_host[2]+'\n')
f.close()
f = open(outdir+'/vms.list', 'w')
f.write('\n')
for idx, val in enumerate(ip_mac):
    f.write(val[0]+'     vm-'+str(idx)+'\n')
f.close()
f = open(outdir+'/resolv.conf', 'w')
f.write('domain grid5000.fr\nsearch '+' '.join( [ site+'.grid5000.fr' for site in get_g5k_sites() ])+'\nnameserver '+get_ip.stdout().strip())
f.close()
f = open(outdir+'/dnsmasq.conf', 'w')
f.write(dhcp_range+dhcp_router+dhcp_hosts)
f.close()



execution_time['3-network'] = timer.elapsed() - sum(execution_time.values())
logger.info(set_style('Done in '+str(round(execution_time['3-network'],2))+' s\n', 'log_header'))


logger.info(set_style('HOSTS CONFIGURATION', 'log_header'))
if args.env_file is not None:
    setup_hosts = Virsh_Deployment( hosts, kavlan = kavlan_id, env_file = args.env_file) 
else:
    setup_hosts = Virsh_Deployment( hosts, kavlan = kavlan_id, env_name = args.env_name)
setup_hosts.deploy_hosts( num_tries = 1 )
setup_hosts.rename_hosts()

hosts = list(setup_hosts.hosts)

logger.info('%s', ", ".join( [set_style(host.address.split('.')[0], 'host') for host in hosts] ))
setup_hosts.upgrade_hosts()
setup_hosts.install_packages()
setup_hosts.configure_libvirt()

if args.vm_backing_file is None:
    setup_hosts.create_disk_image(clean = True)
else:
    logger.info('Copying %s on hosts', args.vm_backing_file)
    copy_actions = []
    for host in hosts:
        copy_actions.append( Remote('scp '+args.vm_backing_file+' root@'+host.address+':',  [get_host_site(host)+'.grid5000.fr'],
                                     connexion_params = default_frontend_connexion_params))
    copy_backing_file = ParallelActions(copy_actions).run()
    
    setup_hosts.create_disk_image( disk_image = '/root/'+args.vm_backing_file.split('/')[-1], clean = True)
setup_hosts.copy_ssh_keys()

logger.info('Configuring %s as a %s server', 
            set_style(service_node.split('.')[0], 'host'), set_style('DNS/DCHP', 'emph'))

Remote('export DEBIAN_MASTER=noninteractive ; apt-get install -y dnsmasq taktuk', [service_node]).run()
Put([service_node], outdir+'/dnsmasq.conf', remote_location='/etc/').run()

logger.info('Adding the VM in /etc/hosts ...')
Put([service_node], outdir+'/vms.list', remote_location= '/root/').run()
Remote('cat /root/vms.list >> /etc/hosts', [service_node]).run()

logger.info('Restarting service ...')
Remote('service dnsmasq restart', [service_node]).run()

logger.info('Configuring resolv.conf on all hosts')
clients = hosts[:]
clients.remove(Host(service_node))
Put(clients, outdir+'/resolv.conf', remote_location = '/etc/').run()


execution_time['4-hosts'] = timer.elapsed() - sum(execution_time.values())
logger.info(set_style('Done in '+str(round(execution_time['4-hosts'],2))+' s\n', 'log_header'))

logger.info(set_style('VIRTUAL MACHINES', 'log_header'))


if placement is None:    
    logger.info('No topology given, defining and distributing the VM')
    vms = define_vms(n_vm, ip_mac, mem_size = vm_ram_size)
    vms = distribute_vms_on_hosts(vms, hosts)
else:
    logger.info('Distributing the virtual machines according to the topology file')
    for site in placement.findall('./site'):
        sites.append(site.get('id'))
        log += '\n'+site.get('id')+': '
        for cluster in site.findall('./cluster'):
            clusters.append(cluster.get('id'))
            log += cluster.get('id')+' ('+str(len(cluster.findall('.//host')))+' hosts - '+str(len(cluster.findall('.//vm')))+' vms) '
    logger.info(log)
    
    
    vms = []
    i_vm = 0
    for site in placement.findall('./site'):
        for host in site.findall('.//host'):
            for vm in host.findall('./vm'):
                vms.append({'vm_id': vm.get('vm_id') if vm.get('vm_id') is not None else 'vm-'+str(i_vm),
                            'host': Host(host.get('id')+'-kavlan-'+str(kavlan_id)+'.'+site.get('id')+'.grid5000.fr'), 
                            'hdd_size': vm.get('hdd') if vm.get('hdd') is not None else 2,
                            'mem_size': vm.get('mem') if vm.get('mem') is not None else 256, 
                            'vcpus': vm.get('cpu') if vm.get('cpu') is not None else 1,
                            'cpuset': vm.get('cpusets') if vm.get('cpusets') is not None else 'auto',
                            'ip': ip_mac[i_vm][0], 
                            'mac': ip_mac[i_vm][1] })
                i_vm += 1

log = ''   
logger.info('Creating the qcow2 disks on hosts')
disk_creation = create_disks_hosts(vms).run()


logger.info('Destroying existing VMs')
destroy_all(hosts)


logger.info('Installing the VMs')
install_vms(vms).run()

logger.info('Starting VMs and waiting for complete boot')
start_vms(vms).run()
wait_vms_have_started(vms, service_node)

log = ''
for host in hosts:
    host_vm = list_vm(host)
    log += '\n'+set_style(host.address.split('.')[0], 'host')+': '+\
                              ', '.join([set_style(vm['vm_id'], 'emph') for vm in host_vm])
logger.info('Deployed VMs %s', log)


execution_time['5-vms'] = timer.elapsed() - sum(execution_time.values())
logger.info(set_style('Done in '+str(round(execution_time['5-vms'],2))+' s\n', 'log_header'))

logger.info(set_style('FINALIZATION', 'log_header'))
deployment = ET.Element('deployment')  
for vm in vms:
    host_info = vm['host'].address.split('.')[0:-2]
    host_uid =   host_info[0].split('-')[0]+'-'+host_info[0].split('-')[1]
    cluster_uid = host_info[0].split('-')[0]
    site_uid = host_info[1]
    print host_uid, cluster_uid, site_uid
    if deployment.find("./site[@id='"+site_uid+"']") is None:
        site = ET.SubElement(deployment, 'site', attrib = {'id': site_uid})
    else:
        site = deployment.find("./site[@id='"+site_uid+"']")
    if site.find("./cluster/[@id='"+cluster_uid+"']") is None:
        cluster = ET.SubElement(site, 'cluster', attrib = {'id': cluster_uid})
    else:
        cluster = site.find("./cluster/[@id='"+cluster_uid+"']")
    if cluster.find("./host/[@id='"+host_uid+"']") is None:
        host = ET.SubElement(cluster, 'host', attrib = {'id': host_uid})
    else:
        host = cluster.find("./host/[@id='"+host_uid+"']")
    el_vm = ET.SubElement(host, 'vm', attrib = {'id': vm['vm_id'], 'ip': vm['ip'], 'mac': vm['mac'], 
                'mem': str(vm['mem_size']), 'cpu': str(vm['vcpus']), 'hdd': str(vm['hdd_size'])})
        


file = outdir+'/initial_state.xml'
tree = ET.ElementTree(deployment)
if with_lxml:
    tree.write(file, pretty_print=True)
else:
    tree.write(file)


execution_time['6-outfiles'] = timer.elapsed() - sum(execution_time.values())
logger.info(set_style('Done in '+str(round(execution_time['6-outfiles'],2))+' s\n', 'log_header'))

rows, columns = os.popen('stty size', 'r').read().split()
total_time = sum(execution_time.values())
total_space = 0
log = 'G5KCloudDeploy successfully executed:'
for step, exec_time in execution_time.iteritems():
    step_size = int(exec_time*int(columns)/total_time)

    log += '\n'+''.join([' ' for i in range(total_space)])+''.join(['X' for i in range(step_size)])
    total_space += int(exec_time*int(columns)/total_time)
logger.info(log)     

