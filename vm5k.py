#!/usr/bin/env python
#-*- coding: utf-8 -*-
import time as T, datetime as DT, execo.time_utils as EXT
#import argparse, time, random, os, sys
import optparse, time, random, os, sys
from logging import INFO, DEBUG, WARN
from json import loads
from itertools import cycle
from pprint import pprint, pformat
from netaddr import IPNetwork
from operator import itemgetter
from execo import *
from execo_g5k import *
from execo_g5k.config import g5k_configuration, default_frontend_connexion_params
from execo_g5k.vmutils import *
from execo_g5k.api_utils import *
from execo_g5k.planning import *
import xml.etree.ElementTree as ET

# Constants
deployment_tries = 2
max_vms = 10000               # Limitations due to the number of IP address 
oargridsub_opts = '-t deploy'   

# Defining the options 
## using argparse is delayed by the frontend wheezy migration 
parser = optparse.OptionParser(
            prog = set_style( sys.argv[0], 'log_header'),
            description = 'A tool to deploy and configure nodes and virtual machines '
            +'with '+set_style('Debian', 'object_repr')+' and '+set_style('libvirt', 'object_repr')+\
            '\non the '+set_style('Grid5000', 'log_header')+' platform in a global '+set_style('KaVLAN','object_repr')+\
            '.\n\nRequire '+set_style('execo-2.2', 'log_header')+'.',
            epilog = 'Example : '+sys.argv[0]+' -n 100 will install 100 VM with the default environnements for 3h '
            )
    
resources = optparse.OptionGroup(parser, set_style('Ressources', 'log_header'),
                set_style('n_vm + walltime', 'emph')+'\nperform a G5K reservation that has enough RAM for the virtual machine ;'+\
                '\n'+set_style('n_vm + oargrid_job_id', 'emph')+'\nuse an existing reservation and create the virtual machine on the hosts'+\
                '\n'+set_style('infile + walltime', 'emph')+'\ndeploy virtual machines and hosts according to a placement XML file for a given walltime'+\
                '\n'+set_style('infile + oargrid_job_id', 'emph')+'\nusing a existing reservation to deploy virtual machines and hosts according to a placement XML file'
                )                                      
resources.add_option('-n', '--n_vm',
                    dest = 'n_vm',
                    type = int,
                    help = 'number of virtual machines'
                    )
resources.add_option('-i', '--infile',
                    dest = "infile",
                    help = 'topology file describing the placement of VM on G5K sites and clusters' )

resources.add_option('-j', '--oargrid_job_id',
                    dest = 'oargrid_job_id',
                    type = int,
                    help = 'use the hosts from a oargrid_job' )
resources.add_option('-w', '--walltime',
                    dest = 'walltime',
                    default = '3:00:00',
                    help = 'duration of your reservation')
parser.add_option_group(resources)

hosts = optparse.OptionGroup(parser,set_style('Physical hosts', 'log_header'))
hosts.add_option('-e', '--env_name', 
                    dest = 'env_name',
                    help = 'Kadeploy environment NAME for the physical host')
hosts.add_option('-a', '--env_file', 
                    dest = 'env_file',
                    help = 'Kadeploy environment FILE for the physical host')
hosts.add_option('-c', '--clusters', 
                    dest = 'clusters',
                    help = 'list of clusters')
hosts.add_option('-s', '--sites', 
                    dest = 'sites',
                    help = 'list of sites')
parser.add_option_group(hosts)


vms = optparse.OptionGroup(parser, set_style('Virtual machines', 'log_header'))
vms.add_option('-f', '--vm_backing_file', 
                    dest = 'vm_backing_file',
                    help = 'backing file for your virtual machines')
vms.add_option('-t', '--vm_template', 
                    dest = 'vm_template',
                    help = 'XML string describing the virtual machine',
                    default = '<vm mem="1024" hdd="2" cpu="1" cpuset="auto"/>')
parser.add_option_group(vms)

log_level = optparse.OptionGroup(parser, set_style('Execution output', 'log_header'))
log_level.add_option("-v", "--verbose", 
                       action = "store_true", 
                       help = 'print debug messages')
log_level.add_option("-q", "--quiet", 
                       action = "store_true",
                       help = 'print only warning and error messages')
log_level.add_option("-o", "--outdir", 
                    dest = "outdir", 
                    default = 'vm5k_'+ time.strftime("%Y%m%d_%H%M%S_%z"),
                    help = 'where to store the vm5k files')
parser.add_option_group(log_level)
(options, args) = parser.parse_args()
args = options

if options.n_vm and options.infile:
    parser.error("options -n n_vm and -i placement file are mutually exclusive, see -h for help")
if options.env_name and options.env_file:
    parser.error("options -e env_name and -a env_file are mutually exclusive, see -h for help")
if options.sites and options.clusters:
    parser.error("options -c clusters and -s sites are mutually exclusive, see -h for help")
#parser = argparse.ArgumentParser(
#            prog = set_style( sys.argv[0], 'log_header'),
#            description = 'A tool to deploy and configure nodes and virtual machines '
#            +'with '+set_style('Debian', 'object_repr')+' and '+set_style('libvirt', 'object_repr')+\
#            '\non the '+set_style('Grid5000', 'log_header')+' platform in a global '+set_style('KaVLAN','object_repr')+\
#            '.\n\nRequire '+set_style('execo-2.2', 'log_header')+'.',
#            epilog = 'Example : '+sys.argv[0]+' -n 100 will install 100 VM with the default environnements for 3h ',
#            formatter_class = argparse.RawTextHelpFormatter
#            )
#    
#resources = parser.add_argument_group('Ressources',
#                set_style('n_vm + walltime', 'user3')+'\nperform a G5K reservation that has enough RAM for the virtual machine'+\
#                '\n'+set_style('n_vm + oargrid_job_id', 'user3')+'\nuse an existing reservation and create the virtual machine on the hosts'+\
#                '\n'+set_style('infile + walltime', 'user3')+'\ndeploy virtual machines and hosts according to a placement XML file for a given walltime'+\
#                '\n'+set_style('infile + oargrid_job_id', 'user3')+'\nusing a existing reservation to deploy virtual machines and hosts according to a placement XML file'
#                )                                      
#
#g1 = resources.add_mutually_exclusive_group()
#g1.add_argument('-n', '--n_vm',
#                    dest = 'n_vm',
#                    type = int,
#                    help = 'number of virtual machines'
#                    )
#g1.add_argument('-i', '--infile',
#                    dest = "infile",
#                    help = 'topology file describing the placement of VM on G5K sites and clusters' )
#g2 = resources.add_mutually_exclusive_group()
#g2.add_argument('-j', '--oargrid_job_id',
#                    dest = 'oargrid_job_id',
#                    type = int,
#                    help = 'use the hosts from a oargrid_job' )
#g2.add_argument('-w', '--walltime',
#                    dest = 'walltime',
#                    default = '3:00:00',
#                    help = 'duration of your reservation')
#
#hosts = parser.add_argument_group('Physical hosts')
#host_env = hosts.add_mutually_exclusive_group()
#host_env.add_argument('-h_env', '--host_env_name', 
#                    dest = 'env_name',
#                    default = 'wheezy-x64-base',
#                    help = 'Kadeploy environment NAME for the physical host')
#host_env.add_argument('-h_enf', '--host_env_file', 
#                    dest = 'env_file',
#                    help = 'Kadeploy environment FILE for the physical host')
#elements = hosts.add_mutually_exclusive_group()
#elements.add_argument('-c', '--clusters', 
#                    dest = 'clusters',
#                    nargs = '*',
#                    help = 'list of clusters')
#elements.add_argument('-s', '--sites', 
#                    dest = 'sites',
#                    nargs = '*',
#                    help = 'list of sites')
#vms = parser.add_argument_group('Virtual machines')
#vms.add_argument('-v_f', '--vm_backing_file', 
#                    dest = 'vm_backing_file',
#                    help = 'backing file for your virtual machines')
#vms.add_argument('-v_t', '--vm_template', 
#                    dest = 'vm_template',
#                    help = 'XML string describing the virtual machine',
#                    default = '<vm mem="2048" hdd="2" cpu="1" cpuset="auto"/>')
#
#log_level = parser.add_mutually_exclusive_group()
#log_level.add_argument("-v", "--verbose", 
#                       action = "store_true", 
#                       help = 'print debug messages')
#log_level.add_argument("-q", "--quiet", 
#                       action = "store_true",
#                       help = 'print only warning and error messages')
#other = parser.add_argument_group('Other options')
#other.add_argument("-o", "--outdir", 
#                    dest = "outdir", 
#                    default = 'wm5k'+ time.strftime("%Y%m%d_%H%M%S_%z"),
#                    help = 'where to store the vm5k files')
#args = parser.parse_args()

timer = Timer()
execution_time = {}
if args.verbose:
    logger.setLevel(DEBUG)
elif args.quiet:
    logger.setLevel(WARN)
else:
    logger.setLevel(INFO)
logger.info('\n\n    Starting %s for the creation of virtual machines on Grid5000\n', set_style(sys.argv[0], 'log_header'))

n_vm = args.n_vm
sites = [] if args.sites is None else [ site for site in args.sites.split(',') ]
clusters = [] if args.clusters is None else [ cluster for cluster in args.clusters.split(',') ]
kavlan_site = None
placement = None
outdir = args.outdir


def error_elements(sites, clusters):
    """ Define the sites and clusters to be excluded from the deployment """
    
    error_sites = [ 'reims', 'bordeaux' ] 
    error_clusters = [item for sublist in map(lambda site: get_site_clusters(site), error_sites) 
                           for item in sublist]+[ 'chirloute' ]
    removed_sites = []
    for site in error_sites:
        if site in sites:
            sites.remove(site)
            removed_sites.append(site)
    removed_clusters = []
    
    for cluster in error_clusters:
        if cluster in clusters:
            clusters.remove(cluster)
            removed_clusters.append(cluster)
    if len(removed_sites) > 0:
        logger.warn('DUE TO G5K BUGS, %s %s BEEN REMOVED ', ', '.join([ set_style(site, 'emph') for site in removed_sites]),
                    'HAVE' if len(removed_sites) > 1 else 'HAS')
    if len(removed_clusters) > 0:
        logger.warn('DUE TO G5K BUGS, %s %s BEEN REMOVED ', ', '.join([ set_style(cluster, 'emph') for cluster in removed_clusters]), 
                                                                      'HAVE' if len(removed_clusters) > 1 else 'HAS')
        
    if len(sites) == 0 or len(clusters) == 0:
        logger.error('No site or cluster given can support vm5k') 
        exit()

try:
    os.mkdir(outdir)
except os.error:
    pass



logger.info(set_style('DEPLOYMENT TOPOLOGY', 'log_header'))
log = ''
if args.infile is not None:
    n_vm = 0
    logger.info( 'Using an input file for the placement: '+ set_style(args.infile, 'emph'))
    
    placement = ET.parse(args.infile)
    for site in placement.findall('./site'):
        sites.append(site.get('id'))
        log += '\n'+site.get('id')+': '
        for cluster in site.findall('./cluster'):
            clusters.append(cluster.get('id'))
            log += cluster.get('id')+' ('+str(len(cluster.findall('.//host')))+' hosts - '+str(len(cluster.findall('.//vm')))+' vms) '
            n_vm += len(cluster.findall('.//vm'))        
    if args.oargrid_job_id is not None:
        log += '\nConcordance between deployment file and grid reservation will be checked'
    
else:
    logger.info('No topology file given, will create %s vms using \ntemplate %s', set_style(str(args.n_vm), 'emph'),
             set_style(args.vm_template, 'emph'))
    if n_vm is None:
        logger.error('Must specify the number of virtual machines or give a placement file, use -h for help')
        exit()
    else:
        if args.oargrid_job_id is not None:
            logger.info('Will use the existing reservation for sites and clusters')
        else:
            logger.info('No reservation given, gathering sites and clusters ...')
            if len(sites) > 0:
                logger.info('Getting clusters for sites %s', set_style(', '.join([site for site in sites]), 'emph'))
                clusters = get_clusters(virt = True, kavlan = True, sites = sites)
            else:
                if len(clusters) == 0:
                    logger.info('Getting clusters with virtualization technology and kavlan')
                    clusters = get_clusters(virt = True, kavlan = True)
                    
                for cluster in clusters:
                    site_cluster = get_cluster_site(cluster)
                    if site_cluster not in sites :
                        sites.append(site_cluster)

if args.oargrid_job_id is None:
    error_elements(sites, clusters)
    logger.info('sites: %s', set_style(', '.join([site for site in sites]), 'emph') )
    logger.info('clusters: %s', set_style(', '.join( [ cluster for cluster in clusters]), 'emph') )

execution_time['1-topology'] = timer.elapsed()
logger.info(set_style('Done in '+str(round(execution_time['1-topology'],2))+' s\n', 'log_header'))



    
logger.info(set_style('GRID RESERVATION', 'log_header'))
clusters_ram = {}
for cluster in clusters:  
    clusters_ram[cluster] = get_host_attributes(cluster+'-1')['main_memory']['ram_size']/10**6
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
        required_ram = sum([ int(vm.get('mem')) for vm in placement.findall('.//vm')])
        
        for host in placement.findall('.//host'):
            if clusters_ram[host.get('id').split('-')[0]] < sum([ int(vm.get('mem')) for vm in host.findall('./vm')]):
                logger.warning('Host '+host.get('id')+' has not enough RAM')  
        
        cluster_nodes = {}
        for cluster in placement.findall('.//cluster'):
            cluster_nodes[cluster.get('id')] = len(cluster.findall('./host')) 
        
        for slot in planning.slots:
            for cluster, n_nodes in cluster_nodes.iteritems():
                slot_ok = True
                if slot[2][cluster] < cluster_nodes[cluster] and slot[1]-slot[0] > get_seconds(walltime):
                    slot_ok = False    
        
            if slot_ok:
                chosen_slot = slot
                break
        
    
    else:        
        vm_ram_size = int(ET.fromstring(args.vm_template).get('mem'))
        required_ram = n_vm * vm_ram_size
        
        slots_ok = []
        for slot in planning.slots:
            slot_ram = 0
            slot_node = 0 
            for resource, n_node in slot[2].iteritems():
                if resource in clusters:
                    slot_ram += n_node * clusters_ram[resource]
                    slot_node += n_node    
        
            if required_ram < slot_ram:# and slot[1]-slot[0] > get_seconds(walltime):
                chosen_slot = slot
                break
        
        tmp_res = chosen_slot[2].copy() 
        for res in tmp_res.iterkeys():
            if res not in clusters:
                del chosen_slot[2][res]
        
        cluster_nodes = {}
        for cluster in chosen_slot[2].iterkeys():
            cluster_nodes[cluster] = 0 
            
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
    get_jobs = Remote('oarstat -J -f', [ Host(site) for site in sites], 
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
            sub_resources = "{type=\\'kavlan-global\\'}/vlan=1+"
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

logger.info('Retrieving the KaVLAN of ')
kavlan_id = None
subjobs = get_oargrid_job_oar_jobs(oargrid_job_id)
for subjob in subjobs:
    vlan = get_oar_job_kavlan(subjob[0], subjob[1])
    if vlan is not None: 
        kavlan_id = vlan
        kavlan_site = subjob[1]
        logger.info('%s found !', subjob[1])        
        break
    else:
        logger.info('%s, not found', subjob[1])
if kavlan_id is None:
    logger.error('No KaVLAN found, aborting ...')
    oargriddel(oargrid_job_id)
    exit()

        
hosts = get_oargrid_job_nodes( oargrid_job_id )
hosts.sort()

logger.info('Getting the attributes of \n%s', ", ".join( [set_style(host.address.split('.')[0], 'host') for host in hosts] ))

clusters = []
for host in hosts:
    cluster = get_host_cluster(host)
    if cluster not in clusters:
        clusters.append(cluster)

clusters_attr = {}
for cluster in clusters:
    attr = get_host_attributes(cluster+'-1')
    clusters_attr[cluster] = {
                               'node_flops': attr['performance']['node_flops'] if attr.has_key('performance') else 0, 
                               'ram_size': attr['main_memory']['ram_size']/10**6,
                               'n_cpu': attr['architecture']['smt_size'] }
total_attr = {'ram_size': 0, 'n_cpu': 0}
for host in hosts:
    attr = clusters_attr[get_host_cluster(host)]
    
    total_attr['ram_size'] += attr['ram_size']
    total_attr['n_cpu'] += attr['n_cpu']


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
    vm_ram_size = int(ET.fromstring(args.vm_template).get('mem'))
    if n_vm > max_vms:
        logger.warning('Reducing the number of virtual machines to %s, due to the'+\
                     ' number of available IP in the KaVLAN global', set_style(max_vms, 'report_error') )
        n_vm = max_vms
    
    max_vms = min (max_vms, total_attr['ram_size']/vm_ram_size)
    
        
        
execution_time['2-reservation'] = timer.elapsed() - sum(execution_time.values())
logger.info(set_style('Done in '+str(round(execution_time['2-reservation'],2))+' s\n', 'log_header'))


logger.info(set_style('HOSTS CONFIGURATION', 'log_header'))
if args.env_file is not None:
    setup = Virsh_Deployment( hosts, kavlan = kavlan_id, env_file = args.env_file, outdir = outdir) 
else:
    setup = Virsh_Deployment( hosts, kavlan = kavlan_id, env_name = args.env_name,  outdir = outdir)
setup.deploy_hosts()
setup.get_hosts_attr()
max_vms = setup.get_max_vms(options.vm_template)
setup.enable_taktuk()
setup.configure_apt()
setup.upgrade_hosts()
setup.install_packages()
setup.reboot_nodes()
setup.configure_libvirt()
setup.create_disk_image(disk_image = args.vm_backing_file)
setup.ssh_keys_on_vmbase()

execution_time['4-hosts'] = timer.elapsed() - sum(execution_time.values())
logger.info(set_style('Done in '+str(round(execution_time['4-hosts'],2))+' s\n', 'log_header'))

logger.info(set_style('VIRTUAL MACHINES', 'log_header'))
logger.info('Destroying VMS')
destroy_vms(setup.hosts, setup.taktuk_params)

if placement is None:    
    logger.info('No topology given, defining and distributing the VM')
    vms = define_vms(n_vm, setup.ip_mac, mem_size = vm_ram_size)
    vms = setup.distribute_vms(vms)
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
                            'ip': setup.ip_mac[i_vm][0], 
                            'mac': setup.ip_mac[i_vm][1] })
                i_vm += 1
    setup.vms = vms

create = create_disks(setup.vms, setup.taktuk_params).run()
logger.info('Installing the VMs')
install = install_vms(setup.vms, setup.taktuk_params).run()
logger.info('Starting the VMs')
start = start_vms(setup.vms, setup.taktuk_params).run()
logger.info('Waiting for all VMs to have started')
wait_vms_have_started(setup.vms, setup.taktuk_params)

setup.write_placement_file()


rows, columns = os.popen('stty size', 'r').read().split()
total_time = sum(execution_time.values())
total_space = 0
log = 'vm5k successfully executed:'
for step, exec_time in execution_time.iteritems():
    step_size = int(exec_time*int(columns)/total_time)

    log += '\n'+''.join([' ' for i in range(total_space)])+''.join(['X' for i in range(step_size)])
    total_space += int(exec_time*int(columns)/total_time)
logger.info(log)     

