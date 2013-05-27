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
import time as T, xml.etree.ElementTree as ET
import execo as EX, execo_g5k as EX5
from execo import logger
from execo.log import set_style
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
        self.default_packages = ' command-not-found bash-completion nmap qemu-kvm  virtinst libvirt-bin taktuk '
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
        self.hosts = Hosts[0]
        logger.info('%s deployed',' '.join([node.address for node in self.hosts]))
        self.state.append('deployed')

    def upgrade_hosts(self):
        """ Perform apt-get update && apt-get dist-upgrade in noninteractive mode """
        logger.info('Upgrading hosts')
        cmd = " echo 'debconf debconf/frontend select noninteractive' | debconf-set-selections; \
                echo 'debconf debconf/priority select critical' | debconf-set-selections ;      \
                apt-get update ; export DEBIAN_MASTER=noninteractive ; apt-get dist-upgrade -y;"
        logger.debug(' Upgrade command:\n%s', cmd)
        upgrade = EX.Remote(cmd, self.hosts).run()
        if upgrade.ok():
            logger.debug('Upgrade finished')
        else:
            logger.error('Unable to perform dist-upgrade on the nodes ..')
        
    def install_packages(self, packages_list = None):
        """ Installation of packages on the nodes """
        logger.info('Installing packages')
        if packages_list is None:
            packages_list = self.default_packages
        cmd = 'apt-get update && apt-get install  -y --force-yes '+packages_list
        install = EX.Remote(cmd, self.hosts).run()
        if install.ok():
            logger.debug('Packages installed')
        else:
            logger.error('Unable to install packages on the nodes ..')

    def reboot(self):
        """ Reboot the nodes """
        logger.info('Rebooting nodes ...')
        reboot=EX.Remote('reboot',self.hosts).run()
        if reboot.ok():
            while True:
                T.sleep(5)
                ping=[]
                for host in self.hosts:
                    logger.info('Waiting for node %s',host.address)
                    ping.append(EX.Remote('ping -c 4 '+host.address,[self.frontend],connexion_params={'user':'lpouilloux'}, log_exit_code=False))
                all_ping=EX.ParallelActions(ping).run()

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
                part_host = host.address.partition('.')
                host.address = part_host[0]+'-kavlan-'+str(self.kavlan)+part_host[1]+ part_host[2]
            logger.debug('Hosts name have been changed :\n %s',pformat(self.hosts))
            self.state.append('renamed')

    def create_disk_image(self, disk_image = '/grid5000/images/KVM/squeeze-x64-base.qcow2', clean = False):
        """Create a base image in RAW format for  using qemu-img """
        
        if clean:
            logger.info('Removing existing disks')
            EX.Remote('rm -f/tmp/*.img; rm -f /tmp/*.qcow2', self.hosts).run()
        
        logger.info("Creating disk image on /tmp/vm-base.img")
        cmd = 'qemu-img convert -O raw '+disk_image+' /tmp/vm-base.img'
        EX.Remote(cmd, self.hosts).run()
        self.state.append('disk_created')

    def copy_ssh_keys(self, ssh_key = None):
        """Copying your ssh_keys on hosts and vms for automatic connexion"""
        logger.info('Copying ssh key on hosts ...')
        ssh_key = '~/.ssh/id_rsa' if ssh_key is None else ssh_key
        EX.Put(self.hosts,[ssh_key, ssh_key+'.pub'],remote_location='.ssh/').run()
        EX.Remote('cat '+ssh_key+'.pub >> .ssh/authorized_keys; '+ \
                          'echo "Host * \n StrictHostKeyChecking no" >> .ssh/config; ', self.hosts).run()

        if 'disk_created' not in self.state:
            self.create_disk_image()

        logger.info('Copying ssh key on vm-base ...')


        cmd = 'modprobe nbd max_part=1; '+ \
                'qemu-nbd --connect=/dev/nbd0 /tmp/vm-base.img; sleep 5; '+ \
                'mount /dev/nbd0p1 /mnt; mkdir /mnt/root/.ssh; '+ \
                'cat '+ssh_key+'.pub >> /mnt/root/.ssh/authorized_keys; '+ \
                'echo "Host * \n StrictHostKeyChecking no" >> /mnt/root/.ssh/config; '+ \
                'umount /mnt'
        logger.debug(cmd)
        copy_on_vm_base = EX.Remote(cmd, self.hosts).run()
        logger.debug('%s', copy_on_vm_base.ok())
        self.state.append('ssh_keys')


    def configure_libvirt(self, network_xml = None, bridge = 'br0'):
        """Configure libvirt: make host unique, configure and restart the network """
        
        logger.info('Making libvirt host unique ...')
        cmd = 'uuid=`uuidgen` && sed -i "s/00000000-0000-0000-0000-000000000000/${uuid}/g" /etc/libvirt/libvirtd.conf '\
                +'&& sed -i "s/#host_uuid/host_uuid/g" /etc/libvirt/libvirtd.conf && service libvirt-bin restart'
        EX.Remote(cmd, self.hosts).run()
        
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
        EX.Remote('virsh net-destroy default; virsh net-undefine default', self.hosts).run()
        EX.Put(self.hosts, 'default.xml', remote_location = '/etc/libvirt/qemu/networks/').run()
        EX.Remote('virsh net-define /etc/libvirt/qemu/networks/default.xml ; virsh net-start default; virsh net-autostart default; ', self.hosts).run()
        self.state.append('virsh_network')
        
        logger.info('Restarting libvirt ...')        
        EX.Remote('service libvirt-bin restart', self.hosts).run()


    def get_fastest_nodes(self):
        """ Use the G5K api to have the fastest node"""


    
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
