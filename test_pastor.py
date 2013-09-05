#!/usr/bin/env python
import random
from pprint import pprint
from logging import INFO, DEBUG
from execo import logger, configuration, Put, Remote, TaktukRemote, ChainPut, Host
from execo_g5k import *
from execo_g5k.vmutils import *
from execo.time_utils import sleep
from netaddr import IPNetwork


logger.setLevel(INFO)


env_file = '/home/lpouilloux/deploy_40_400/environment/kvm-1.5-nocompression.env'
oargrid_job_id = 46681 


wait_oargrid_job_start(oargrid_job_id)

logger.info('Retrieving the list of hosts ...')   
hosts = get_oargrid_job_nodes( oargrid_job_id )

n_vm = 10* len( hosts )

logger.info('Retrieving the KaVLAN')
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
    
    
logger.info('Generating the IP-MAC list')
vm_ip = []
all_ip = IPNetwork('10.'+str(3+(kavlan_id-10)*4)+'.216.0/18')
subnets = list(all_ip.subnet(21))
for subnet in subnets:
    if subnet.ip.words[2] >= 216:
        for ip in subnet.iter_hosts():
            vm_ip.append(ip)
network = str(min(vm_ip))+','+str(max(vm_ip[0:-1]))+','+str(all_ip.netmask)
dhcp_range = 'dhcp-range='+network+',12h\n'
dhcp_router = 'dhcp-option=option:router,'+str(max(vm_ip))+'\n'
dhcp_hosts ='' 
ip_mac = []
macs = []
dhcp_hosts =''
for ip in vm_ip[0:n_vm]:
    mac = [ 0x00, 0x020, 0x4e,
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff) ]
    while mac in macs:
        mac = [ 0x00, 0x020, 0x4e,
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff) ]
    macs.append(mac)
    dhcp_hosts += 'dhcp-host='+':'.join( map(lambda x: "%02x" % x, mac))+','+str(ip)+'\n'
    ip_mac.append( ( str(ip), ':'.join( map(lambda x: "%02x" % x, mac) ) ) )

    
    
    
network = str(min(vm_ip))+','+str(max(vm_ip[0:-1]))+','+str(all_ip.netmask)
dhcp_range = 'dhcp-range='+network+',12h\n'
dhcp_router = 'dhcp-option=option:router,'+str(max(vm_ip))+'\n'

setup = Virsh_Deployment( hosts, kavlan = kavlan_id, env_file = env_file, outdir = 'debug_vm5k')

setup.ip_mac = ip_mac 
setup.deploy_hosts()
ssh_key = '~/.ssh/id_rsa'
Put(setup.hosts, [ssh_key, ssh_key+'.pub'], remote_location='.ssh/', connexion_params = {'user': 'root'} ).run()

setup.configure_apt()
setup.upgrade_hosts()
#NO ERROR MESSAGE BUT THE PACKETS ARE NOT INSTALLED
# for get.ip.pl scripts
#setup.install_packages("libxml-xpath-perl libsys-virt-perl")
setup.install_packages('libxml-xpath-perl libsys-virt-perl')
setup.reboot_nodes()
setup.configure_libvirt(n_vm)
setup.create_disk_image()
setup.ssh_keys_on_vmbase()
setup.configure_service_node(dhcp_range, dhcp_router, dhcp_hosts)

vms = define_vms(n_vm, setup.ip_mac, mem_size = 1024)

i_vm = 0
for host in setup.hosts:
    for i in range(10):
        vms[i_vm]['host'] = host.address
        i_vm += 1

logger.info('Destroying existing VMs')
destroy_vms(setup.hosts)

logger.info('Creating the VMs disks on all hosts')
create = create_disks_on_hosts(vms, setup.hosts).run()

logger.info('Installing the VMs')
install = install_vms(vms).run()

logger.info('Starting the VMs')
start = start_vms(vms).run()
logger.info('Waiting for all VMs to have started')
wait_vms_have_started(vms)
sleep(3)
# For the moment there is a bug in the write_placement method
#setup.vms = vms
#setup.write_placement_file()



vms_ip = [ Host(vm['ip']) for vm in vms] 
files =  'tools.tgz'  
putfiles = ChainPut(vms_ip, files, connexion_params = {'user': 'root'}).run()
#puttries = 1
#while (not putfiles.ok()) and puttries < 5:
#    puttries += 1
#    sleep(5)            
#    files = [ 'tools.tgz' ] 
#    putfiles = Put(vms, files).run()
if not putfiles.ok():
    print 'ERROR'
    exit()
logger.info('Compile')
TaktukRemote('tar xzf tools.tgz ; cd ./tools ; ./build.sh ; cp ./bin/* /bin/.', vms_ip, connexion_params = {'user': 'root'} ).run()


logger.info('push get-ip.pl')
files =  'get-ip.pl'  
putfiles = ChainPut(setup.hosts, files, '/bin/.', connexion_params = {'user': 'root'} ).run()
#puttries = 1
#while (not putfiles.ok()) and puttries < 5:
#    puttries += 1
#    sleep(5)            
#    files = [ 'get-ip.pl' ] 
#    putfiles = Put(hosts, files, '/bin/.').run()
#if not putfiles.ok():
#    return 'ERROR'
#    exit()

logger.info('FINISHED')
exit()

## EXEMPLE POUR LANCER LE memtouch
#
#size = 2048 * 0.9
#speed = 95
#calibration = TaktukRemote('./memtouch-with-busyloop3 --cmd-calibrate '+str(size), [vms_ip[0]] ).run()
#args = ''
#for p in calibration.processes():
#    for line in p.stdout().split('\n'):
#        if '--cpu-speed' in line:
#            args = line
#logger.debug('%s', args)
#return TaktukRemote('./memtouch-with-busyloop3 --cmd-makeload '+args+' '+str(size)+' '+str(speed), vms)
