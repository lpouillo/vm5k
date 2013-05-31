# Copyright 2009-2012 INRIA Rhone-Alpes, Service Experimentation et
# Developpement
#
# This file is part of Execo.
#
# Execo is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Execo is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
# License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Execo.  If not, see <http://www.gnu.org/licenses/>

"""Some classes to configure a cluster with libvirt on Grid5000 and various virtualization
technology
"""
from pprint import pprint, pformat
import time as T, xml.etree.ElementTree as ET, re
import execo as EX, execo_g5k as EX5
from execo import logger
from execo.log import set_style
from execo_g5k.config import g5k_configuration, default_frontend_connexion_params
from execo_g5k.api_utils import get_g5k_sites, get_site_clusters, get_cluster_attributes, get_host_attributes, get_resource_attributes, get_host_site
    

class Virsh_Deployment(object):
    """Base class to deploy and configure hosts with virtualization """
    def __init__(self, hosts = None, env_name = None, env_file = None, kavlan = None, deployment_file = None, oargrid_job_id = None,):
        """ Initalization of the object """
        logger.info('Initializing Virsh_Deployment ')
        if deployment_file is not None:
            self.setup_from_file(deployment_file)
        else:
            self.hosts = hosts
            if env_file is None:
                self.env_name = 'squeeze-x64-prod' if env_name is None else env_name
            else:
                self.env_file = env_file
                self.env_name = None
            self.kavlan = kavlan
            self.vms = []
        self.hosts_attr = None
        self.default_packages = ' uuid-runtime command-not-found bash-completion nmap qemu-kvm  virtinst libvirt-bin taktuk '
        self.state =['initialized']
       
        #self.packages_list = ' command-not-found bash-completion nmap qemu-kvm  virtinst libvirt-bin'
        #self.bridge = 'br0'
        #self.hack_cmd = "source /etc/profile; "

    def run(self):
        """Sequentially execute deploy_hosts, rename_hosts, upgrade_packages, install_packages,
        configure_libvirt, create_disk_image, copy_ssh_keys"""
        self.deploy_hosts()
        if self.kavlan is not None:
            self.rename_hosts()
            self.setup_service_node()
        self.upgrade_hosts()
        self.install_packages('command-not-found bash-completion nmap qemu-kvm  virtinst libvirt-bin')
        self.configure_libvirt()
        self.create_disk_image()
        self.copy_ssh_keys()

  
    def deploy_hosts(self, out = False, num_tries = 3):
        """ Perform the deployment of all hosts simultaneously """
        if self.env_name is not None:
            logger.info('Deploying environment %s ...',set_style( self.env_name, '') )
            deployment = EX5.Deployment(
                                                    hosts = self.hosts,
                                                    env_name = self.env_name,
                                                    vlan = self.kavlan)
        elif self.env_file is not None:
            logger.info('Deploying environment %s ...', self.env_file)
            sites = []
            for host in self.hosts:
                host_site = get_host_site(host)
                if host_site not in sites:
                    sites.append(host_site)
                    
            deployment = EX5.Deployment(
                                                    hosts = self.hosts,
                                                    env_file = self.env_file,
                                                    vlan = self.kavlan)
        Hosts = EX5.deploy(deployment, out = out, num_tries = num_tries)
        
        self.hosts = list(Hosts[0])
  


        
        logger.info('%s deployed',' '.join([node.address for node in self.hosts]))
        self.state.append('deployed')

    def enable_taktuk(self, ssh_key = None):
        """Copying your ssh_keys on hosts for automatic connexion"""
        logger.info('Copying ssh key to prepare hosts for taktuk execution and file transfer ...')
        ssh_key = '~/.ssh/id_rsa' if ssh_key is None else ssh_key
        
        for hosts_slice in [self.hosts[i:i+5] for i in range(0, len(self.hosts), 5)]:
            EX.Put(hosts_slice,[ssh_key, ssh_key+'.pub'],remote_location='.ssh/').run()
        
        
        EX.SequentialActions( [EX.Remote('cat '+ssh_key+'.pub >> .ssh/authorized_keys; '+ \
                          'echo "Host * \n StrictHostKeyChecking no" >> .ssh/config; ', [host]) 
                               for host in self.hosts]).run()
        
        EX.Remote('export DEBIAN_MASTER=noninteractive ; apt-get install -y  --force-yes taktuk', [self.hosts[0]]).run()
        self.taktuk_params = {     'user': 'root',
                'host_rewrite_func': lambda host: re.sub("\.g5k$", ".grid5000.fr", host),        
                'taktuk_gateway': self.hosts[0].address,}
        

    def upgrade_hosts(self):
        """ Perform apt-get update && apt-get dist-upgrade in noninteractive mode """
        logger.info('Upgrading hosts')
        cmd = " echo 'debconf debconf/frontend select noninteractive' | debconf-set-selections; \
                echo 'debconf debconf/priority select critical' | debconf-set-selections ;      \
                apt-get update ; export DEBIAN_MASTER=noninteractive ; apt-get dist-upgrade -y --force-yes;"
        logger.debug(' Upgrade command:\n%s', cmd)
        upgrade = EX.TaktukRemote(cmd, self.hosts, connexion_params = self.taktuk_params).run()
        if upgrade.ok():
            logger.debug('Upgrade finished')
        else:
            logger.error('Unable to perform dist-upgrade on the nodes ..')
                    
            
        
    def install_packages(self, packages_list = None):
        """ Installation of packages on the nodes """
        logger.info('Installing packages')
        
        cmd='echo deb http://backports.debian.org/debian-backports/ squeeze-backports main contrib non-free >> /etc/apt/sources.list'    
        EX.TaktukRemote(cmd, self.hosts, connexion_params = self.taktuk_params).run()        
        if packages_list is None:
            packages_list = self.default_packages
        cmd = 'export DEBIAN_MASTER=noninteractive ; apt-get update && apt-get install -t squeeze-backports -y --force-yes '+packages_list
        install = EX.TaktukRemote(cmd, self.hosts, connexion_params = self.taktuk_params).run()
        if install.ok():
            logger.debug('Packages installed')
        else:
            logger.error('Unable to install packages on the nodes ..')

    def create_bridge(self, bridge_name = 'br0'):
        """ Creation of a bridge to be used for the virtual network """
        logger.info('Configuring the bridge')
        bridge_exists = EX.TaktukRemote('brctl show |grep '+bridge_name, self.hosts,
                         connexion_params = self.taktuk_params, log_exit_code = False).run()
        nobr_hosts = []
        for p in bridge_exists.processes():
            if len(p.stdout()) == 0:
                nobr_hosts.append(p.host())
        
        cmd = 'echo "auto br0 \niface br0 inet dhcp \n bridge_ports eth0 \n bridge_stp off \n '+\
            'bridge_maxwait 0 \n bridge_fd 0" >> /etc/network/interfaces ; ifup br0'
        create_br = EX.TaktukRemote(cmd, nobr_hosts, connexion_params = self.taktuk_params).run()
        
        
        
    def reboot(self):
        """ Reboot the nodes """
        logger.info('Rebooting nodes ...')
        reboot=EX.TaktukRemote('reboot', self.hosts , connexion_params = self.taktuk_params).run()
        if reboot.ok():
            while True:
                T.sleep(5)
                ping=[]
                for host in self.hosts:
                    logger.info('Waiting for node %s',host.address)
                    ping.append(EX.Remote('ping -c 4 '+host.address, [self.frontend],
                                connexion_params={'user':'lpouilloux'}, log_exit_code=False))
                all_ping = EX.ParallelActions(ping).run()

                if all_ping.ok():
                    break;
                logger.info('Nodes down, sleeping for 5 seconds ...')
            logger.info('All hosts have been rebooted !')
        else:
            logger.error('Not able to connect to the hosts ...')
        self.state.append('rebooted')

    def rename_hosts(self):
        """Rename hosts with the kavlan suffix """
        if self.kavlan is not None:
            logger.info('Using KaVLAN, renaming hosts')
            for host in self.hosts:
                host.address = EX5.get_kavlan_host_name(host, self.kavlan)
            logger.debug('Hosts name have been changed :\n %s',pformat(self.hosts))
            self.state.append('renamed')
            
    def create_disk_image(self, disk_image = None, clean = False):
        """Create a base image in RAW format for  using qemu-img """
        
        if disk_image is None:
            disk_image = '/grid5000/images/KVM/squeeze-x64-base.qcow2'
        
        EX.TaktukRemote( 'scp '+default_frontend_connexion_params['user']+'@'+g5k_configuration['default_frontend']+'.grid5000.fr:'+disk_image+' .',
                         self.hosts, connexion_params = self.taktuk_params).run()
        if clean:
            logger.info('Removing existing disks')
            EX.TaktukRemote('rm -f /tmp/*.img; rm -f /tmp/*.qcow2', self.hosts, 
                            connexion_params = self.taktuk_params).run()
        
        logger.info("Creating disk image on /tmp/vm-base.img")
        cmd = 'qemu-img convert -O raw /root/'+disk_image.split('/')[-1]+' /tmp/vm-base.img'
        EX.TaktukRemote(cmd, self.hosts, connexion_params = self.taktuk_params).run()
        self.state.append('disk_created')


    
#    def create_disk_image(self, disk_image = '/grid5000/images/KVM/squeeze-x64-base.qcow2', clean = False):
#        """Create a base image in RAW format for  using qemu-img """
#        
#        if clean:
#            logger.info('Removing existing disks')
#            EX.TaktukRemote('rm -f /tmp/*.img; rm -f /tmp/*.qcow2', self.hosts, 
#                            connexion_params = self.taktuk_params).run()
#        
#        logger.info("Creating disk image on /tmp/vm-base.img")
#        cmd = 'qemu-img convert -O raw '+disk_image+' /tmp/vm-base.img'
#        EX.TaktukRemote(cmd, self.hosts, connexion_params = self.taktuk_params).run()
#        self.state.append('disk_created')


    def ssh_keys_on_vmbase(self, ssh_key = None):
        logger.info('Copying ssh key on vm-base ...')
        if 'disk_created' not in self.state:
            self.create_disk_image()

        cmd = 'modprobe nbd max_part=1; '+ \
                'qemu-nbd --connect=/dev/nbd0 /tmp/vm-base.img; sleep 5; '+ \
                'mount /dev/nbd0p1 /mnt; mkdir /mnt/root/.ssh; '+ \
                'cat '+ssh_key+'.pub >> /mnt/root/.ssh/authorized_keys; '+ \
                'echo "Host * \n StrictHostKeyChecking no" >> /mnt/root/.ssh/config; '+ \
                'umount /mnt'
        logger.debug(cmd)
        copy_on_vm_base = EX.TaktukRemote(cmd, self.hosts, connexion_params = self.taktuk_params).run()
        logger.debug('%s', copy_on_vm_base.ok())
        self.state.append('ssh_keys')


    def configure_libvirt(self, network_xml = None, bridge = 'br0'):
        """Configure libvirt: make host unique, configure and restart the network """
        
        logger.info('Making libvirt host unique ...')
        cmd = 'uuid=`uuidgen` && sed -i "s/00000000-0000-0000-0000-000000000000/${uuid}/g" /etc/libvirt/libvirtd.conf '\
                +'&& sed -i "s/#host_uuid/host_uuid/g" /etc/libvirt/libvirtd.conf && service libvirt-bin restart'
        EX.TaktukRemote(cmd, self.hosts, connexion_params = self.taktuk_params).run()
        
        logger.info('Configuring libvirt network ...')
        if network_xml is None:
            root = ET.Element('network')
            name = ET.SubElement(root,'name')
            name.text = 'default'
            ET.SubElement(root, 'forward', attrib={'mode':'bridge'})
            ET.SubElement(root, 'bridge', attrib={'name': bridge})
        else:
            logger.info('Using custom file for network... \n%s', network_xml)
            root = ET.fromstring( network_xml )
            
        self.tree = ET.ElementTree(element=root)

        self.tree.write('default.xml')
        
        EX.TaktukRemote('virsh net-destroy default; virsh net-undefine default', self.hosts,
                    connexion_params = self.taktuk_params, log_exit_code = False).run()
        
        EX.Put([self.hosts[0]], 'default.xml').run()
        EX.TaktukPut(self.hosts, '/root/default.xml', remote_location = '/etc/libvirt/qemu/networks/',
                      connexion_params = self.taktuk_params).run()
              
        EX.TaktukRemote('virsh net-define /etc/libvirt/qemu/networks/default.xml ; virsh net-start default; virsh net-autostart default; ', 
                        self.hosts, connexion_params = self.taktuk_params).run()
        self.state.append('virsh_network')
        
        logger.info('Restarting libvirt ...')        
        EX.TaktukRemote('service libvirt-bin restart', self.hosts, connexion_params = self.taktuk_params).run()

    def get_hosts_attr(self):
        """ Get the node_flops, ram_size and smt_size from g5k API"""
        self.hosts_attr = {}
        self.hosts_attr['total'] = {'ram_size': 0, 'n_cpu': 0}
        for host in self.hosts:
            attr = get_host_attributes(host)
            self.hosts_attr[host.address] = {'node_flops': attr['performance']['node_flops'] if attr.has_key('performance') else 0, 
                                       'ram_size': attr['main_memory']['ram_size'],
                                       'n_cpu': attr['architecture']['smt_size'] }
            self.hosts_attr['total']['ram_size'] += attr['main_memory']['ram_size']
            self.hosts_attr['total']['n_cpu'] += attr['architecture']['smt_size']


    def get_fastest_host(self):
        """ Use the G5K api to have the fastest node"""
        if self.hosts_attr is None:
            self.get_hosts_attr()
        max_flops = 0
        for host, attr in self.hosts_attr.iteritems():
            if attr['node_flops'] > max_flops:
                max_flops = attr['node_flops']
                fastest_host = host
        return fastest_host

    def setup_service_node(self, host = None, ip_mac = None):
        """ Use dnsmasq to setup a DNS/DHCP server for the VM """
        if host is None:
            self.service_node = self.get_fastest_host()
        
        if self.kavlan is not None:
            """ """
        
        
        

    
def get_clusters(sites = None, n_nodes = 1, node_flops = 10**1, virt = False, kavlan = False):
    """Function that returns the list of cluster with some filters"""
    if sites is None:
        sites = get_g5k_sites()
    
    big_clusters = []
    virt_clusters = []
    kavlan_clusters = []
    for site in sites:
        for cluster in get_site_clusters(site):
            if get_resource_attributes('grid5000/sites/'+site+'/clusters/'+cluster+'/nodes')['total'] >= n_nodes:
                big_clusters.append(cluster)
            if get_host_attributes(cluster+'-1.'+site+'.grid5000.fr')['supported_job_types']['virtual'] in [ 'ivt', 'amd-v']:
                virt_clusters.append(cluster)
            if get_cluster_attributes(cluster)['kavlan']:
                kavlan_clusters.append(cluster)
                
    logger.debug('Clusters with more than '+str(n_nodes)+' nodes \n%s',
                 ', '.join([cluster for cluster in big_clusters]))
    logger.debug('Clusters with virtualization capacities \n%s', 
                 ', '.join([cluster for cluster in virt_clusters]))
    logger.debug('Clusters with a kavlan activated \n%s',
                 ', '.join([cluster for cluster in kavlan_clusters] ))
    
    

    if virt and kavlan:
        return list(set(virt_clusters) & set(big_clusters)  & set(kavlan_clusters))
    elif virt:
        return list(set(virt_clusters) & set(big_clusters)  )
    elif kavlan:
        return list(set(kavlan_clusters) & set(big_clusters)  )
    else:
        return list(set(big_clusters) )
