#!/usr/bin/env python
#-*- coding: utf-8 -*-
from os import path, mkdir
from time import time
import random
import xml.etree.ElementTree as XML
from netaddr import IPNetwork, cidr_merge
from pprint import pformat, pprint
from execo import configuration, Put, Get, Remote, SequentialActions, ParallelActions, Host
from execo_g5k.oar import format_oar_date
from execo_g5k import OarSubmission, oargridsub, oargriddel, get_oargrid_job_oar_jobs, wait_oargrid_job_start, get_oargrid_job_nodes, get_oar_job_subnets, get_oar_job_info,get_oar_job_kavlan
from execo_g5k.vmutils import *
from execo_g5k.planning import *
from execo_g5k.config import default_frontend_connexion_params
from execo_g5k.api_utils import get_site_clusters
from execo_engine import Engine, ParamSweeper, sweep, slugify, logger


def split_vm( vms_params, n = 2 ):
    split_vms = [0] * n
    for i_params in range(n):
        split_vms[i_params] = vms_params[i_params::n]
    return split_vms

def setup_kavlan_global_dhcp_server( host, kavlan_id):
    """ Return a list of tuples containing the authorized ip and the corresponding ip """
    vm_ip = []
    all_ip = IPNetwork('10.'+str(3+(kavlan_id-10)*4)+'.216.0/18')
    
    subnets = list(all_ip.subnet(21))
    for subnet in subnets:
        if subnet.ip.words[2] >= 216:
            for ip in subnet.iter_hosts():
                vm_ip.append(ip)
    
    dhcp_range = 'dhcp-range='+str(min(vm_ip))+','+str(max(vm_ip[0:-1]))+','+str(all_ip.netmask)+',12h\n'
    dhcp_router = 'dhcp-option=option:router,'+str(max(vm_ip))+'\n'
    dhcp_hosts ='' 
    
    ip_mac = []    
    i_vm = 0
    for ip in vm_ip:
        mac = [ 0x00, 0x16, 0x3e,
        random.randint(0x00, 0x7f),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff) ]
        dhcp_hosts += 'dhcp-host='+':'.join( map(lambda x: "%02x" % x, mac))+','+str(ip)+',vm-'+str(i_vm)+'\n'
        ip_mac.append( ( str(ip), ':'.join( map(lambda x: "%02x" % x, mac) ) ) )
        i_vm += 1
    
    
    logger.info('Installing dnsmasq on host %s', host.address)
    Remote('export DEBIAN_MASTER=noninteractive ; apt-get install dnsmasq', [host]).run()
    
    
    f = open('dnsmasq.conf', 'w')
    f.write(dhcp_range+dhcp_router+dhcp_hosts)
    f.close()
    
    logger.info('Putting dnsmasq.conf ...')
    Put([host], 'dnsmasq.conf', remote_location='/etc/').run()
    
    logger.info('Adding the VM in /etc/hosts ...')
    
    logger.info('Restarting service ...')
    Remote('service dnsmasq restart', [host]).run()
    return ip_mac



logger.setLevel('DEBUG')

n_nodes = 3
n_vm = 20

walltime ='2:00:00'
oargridsub_opts = '-t deploy'
    
logger.info('Getting all clusters with virtualization and KaVLAN')
sites = get_kavlan_sites()
clusters = get_virt_clusters(sites)

sites = [ 'toulouse', 'luxembourg', 'rennes', 'grenoble' ]
clusters = [ 'pastel', 'granduc', 'paradent', 'genepi' ]
logger.info('%s', ', '.join([cluster for cluster in clusters]))
resources = { cluster: n_nodes for cluster in clusters }


logger.info('Finding a slot for your experiment')
starttime = T.time()
endtime = starttime + ET.timedelta_to_seconds(DT.timedelta(days=5))

planning = Planning(clusters, starttime, endtime)
planning.find_slots('free', walltime, resources)
planning.draw_gantt(save = True)

start_time = 10**20

for slot in planning.slots_ok.iteritems():
    if slot[0][0] < start_time:
        start_time = slot[0][0] 
start_date = format_oar_date(start_time+100)

logger.info('Job is scheduled for %s', start_date)
subs = []
getkavlan = True
for site in sites:
    sub_resources=''
    if site == 'luxembourg':
        sub_resources="{type=\\'kavlan-global\\'}/vlan=1+"
        getkavlan = False
    for cluster in get_site_clusters(site):
        if resources.has_key(cluster):
            sub_resources += "{cluster=\\'"+cluster+"\\'}/nodes="+str(resources[cluster])+'+'
    subs.append((OarSubmission(resources=sub_resources[:-1]),site))

logger.info('Performing the reservation')    
(oargrid_job_id, _) = oargridsub(subs, walltime = walltime, additional_options = oargridsub_opts, 
                                                            reservation_date = start_date)

logger.info( set_style('RESERVATION ID: '+str(oargrid_job_id), 'emph'))

if oargrid_job_id is not None:
    
    try:
        logger.info('Waiting the job to start')
        wait_oargrid_job_start( oargrid_job_id )
        
        logger.info('Getting the network parameters')
        subjobs = get_oargrid_job_oar_jobs(oargrid_job_id)
        for subjob in subjobs:
            logger.info('Looking for KaVLAN on site: %s ', subjob[1])
            test_vlan = get_oar_job_kavlan(subjob[0], subjob[1])
            if test_vlan is not None: 
                kavlan_id = test_vlan
                kavlan_frontend = subjob[1]+'.grid5000.fr'
                kavlan_job = subjob[0]
                logger.info('KaVLAN found on site: %s with id %s',kavlan_frontend,kavlan_id)
                break
       
        
        logger.info('Getting the list of hosts')
        hosts = get_oargrid_job_nodes( oargrid_job_id )
        logger.info(' %s', ", ".join( [set_style(host.address, 'host') for host in hosts] ))
        
        
        
        logger.info('Deploying the nodes')
        setup_hosts = VirshCluster(hosts, kavlan = kavlan_id)
        setup_hosts.deploy_hosts()
        setup_hosts.rename_hosts()
        setup_hosts.setup_packages()
        setup_hosts.configure_libvirt()
        setup_hosts.create_disk_image()
        setup_hosts.copy_ssh_keys()
    
        hosts = list( setup_hosts.hosts )
        
        logger.info('Deployment successfull, hosts have been rebooted into the KaVLAN and are now \n%s', 
                    pformat(hosts))
        
        ip_mac = setup_kavlan_global_dhcp_server(hosts[0], kavlan_id) 
        
        logger.info('Defining the parameters of the VM')
        n_sites = len(sites)
        vms = define_vms_params( n_sites * n_vm * n_nodes, ip_mac )
        ip_range = vms[0]['ip'].rsplit('.', 1)[0]+'.'+','.join([vm_param['ip'].split('.')[3] for vm_param in vms])
        logger.info('Creating the disks')
        create_disks(hosts, vms)
        
        print len(vms)
        
        vms = split_vm(vms, len(hosts))
        i_host = 0
        for host in hosts:
            install(vms[i_host], host)
            i_host += 1


        ssh_open = False
        while (not ssh_open) and nmap_tries < 30:
            logger.debug('nmap_tries %s', nmap_tries)
            nmap_tries += 1            
            nmap = SshProcess('nmap '+ip_range+' -p 22', host)
            nmap.run()
            logger.debug('%s', nmap.cmd())
            stdout = nmap.stdout().split('\n')
            for line in stdout:
                if 'Nmap done' in line:
                    logger.debug(line)
                    ssh_open = line.split()[2] == line.split()[5].replace('(','')
    
    finally:        
        for host in hosts:
            print list_vm(host)
        logger.info('Deleting job ...'+str(oargrid_job_id))
        oargriddel( [oargrid_job_id] )




exit()
"""  OUTDATED BELOW """


#def network_xml( ip_mac, n_vm, params ):
#    root = XML.Element('network')
#    name = XML.SubElement(root, 'name')
#    name.text = 'default'
#    XML.SubElement(root, 'bridge', attrib = {'name': 'virbr0'})
#    XML.SubElement(root, 'forward', attrib = {'mode':'route'})
#    ip = XML.SubElement(root, 'ip', attrib = {'address': ip_mac[0][0], 'netmask': params['netmask']})
#    dhcp = XML.SubElement(ip, 'dhcp')
#    XML.SubElement(dhcp, 'range',  attrib={'start': ip_mac[1][0],'end': ip_mac[n_vm][0]})  
#    for i_vm in range(n_vm):
#            XML.SubElement(dhcp, 'host', attrib = {
#                                               'ip':           ip_mac[i_vm+1][0], 
#                                               'mac':       ip_mac[i_vm+1][1],
#                                               'name':    'vm-'+str(i_vm)})
#    
##    tree = XML.ElementTree(element=root)     
##    print tree       
#    return XML.tostring(root)
subjobs = get_oargrid_job_oar_jobs(oargrid_job_id)




logger.info('Resa %s', oargrid_job_id)


logger.info('Subjobs: \n%s', pformat(subjobs))

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



            
            
#, pretty_print = True)

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


