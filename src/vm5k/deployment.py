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

from os import fdopen
from pprint import pformat
from random import randint
from xml.etree.ElementTree import Element, SubElement, tostring, parse
from xml.dom import minidom
from itertools import cycle
from time import localtime, strftime
from tempfile import mkstemp
from execo import logger, SshProcess, SequentialActions, Host, Local, sleep, default_connection_params
from execo.action import ActionFactory
from execo.log import style
from execo.config import SSH, SCP
from execo_g5k import get_oar_job_nodes, get_oargrid_job_oar_jobs, get_oar_job_subnets, \
    get_oar_job_kavlan, deploy, Deployment, wait_oar_job_start, wait_oargrid_job_start, \
    distribute_hosts
from execo_g5k.config import g5k_configuration, default_frontend_connection_params
from execo_g5k.api_utils import get_host_cluster, get_g5k_sites, get_g5k_clusters, get_cluster_site, \
    get_host_attributes, get_resource_attributes, get_host_site, canonical_host_name
from execo_g5k.utils import get_kavlan_host_name
from vm5k.config import default_vm
from vm5k.actions import create_disks, install_vms, start_vms, wait_vms_have_started, destroy_vms, create_disks_on_hosts
from vm5k.services import dnsmasq_server
from vm5k.plots import init_live_plot





def get_oar_job_vm5k_resources(oar_job_id, site):
    """Retrieve the hosts list and (ip, mac) list from an oar_job_id and
    return the resources dict needed by vm5k_deployment """
    logger.debug('Waiting job start')
    wait_oar_job_start(oar_job_id, site)
    logger.debug('Retrieving hosts')
    hosts = get_oar_job_nodes(oar_job_id, site)
    logger.debug('Retrieving subnet')
    ip_mac, _ = get_oar_job_subnets( oar_job_id, site )
    kavlan = None
    if len(ip_mac) == 0:
        logger.debug('Retrieving kavlan')
        kavlan = get_oar_job_kavlan(oar_job_id, site)
        if kavlan is not None:
            ip_mac = get_kavlan_ip_mac(kavlan, site)

    return {site: {'hosts': hosts,'ip_mac': ip_mac, 'kavlan': kavlan}}

def get_oargrid_job_vm5k_resources(oargrid_job_id):
    """Retrieve the hosts list and (ip, mac) list by sites from an oargrid_job_id and
    return the resources dict needed by vm5k_deployment, with kavlan-global if used in
    the oargrid job """
    logger.debug('Waiting job start')
    wait_oargrid_job_start(oargrid_job_id)
    logger.debug('Retrieving hosts')
    resources = {}
    for oar_job_id, site in get_oargrid_job_oar_jobs(oargrid_job_id):
        logger.debug('%s: %s', site, oar_job_id)
        resources.update(get_oar_job_vm5k_resources(oar_job_id, site))
    kavlan_global = None
    for site, res in resources.iteritems():
        if res['kavlan'] >= 10:
            kavlan_global = {'kavlan': res['kavlan'], 'ip_mac': resources[site]['ip_mac'], 'site': site }
            break
    if kavlan_global is not None:
        resources['global'] = kavlan_global

    return resources


def get_kavlan_network(kavlan, site):
    """Retrieve the network parameters for a given kavlan from the API"""
    network, mask_size = None, None
    equips = get_resource_attributes('/sites/'+site+'/network_equipments/')
    for equip in equips['items']:
        if equip.has_key('vlans') and len(equip['vlans']) >2:
            all_vlans = equip['vlans']
    for info in all_vlans.itervalues():
        if type(info) == type({}) and info.has_key('name') and info['name'] == 'kavlan-'+str(kavlan):
            network, _, mask_size = info['addresses'][0].partition('/',)
    logger.debug('network=%s, mask_size=%s', network, mask_size)
    return network, mask_size

def get_kavlan_ip_mac(kavlan, site):
    """Retrieve the network parameters for a given kavlan from the API"""
    network, mask_size = get_kavlan_network(kavlan, site)
    min_2 = (kavlan-4)*64 + 2 if kavlan < 8 else (kavlan-8)*64 + 2 if kavlan < 10 else 216
    ips = [ ".".join( [ str(part) for part in ip ]) for ip in [ ip for ip in get_ipv4_range(tuple([ int(part) for part in network.split('.') ]), int(mask_size))
           if ip[3] not in [ 0, 254, 255 ] and ip[2] >= min_2] ]
    macs = []
    for i in range(len(ips)):
        mac = ':'.join( map(lambda x: "%02x" % x, [ 0x00, 0x020, 0x4e,
            randint(0x00, 0xff),
            randint(0x00, 0xff),
            randint(0x00, 0xff) ] ))
        while mac in macs:
            mac = ':'.join( map(lambda x: "%02x" % x, [ 0x00, 0x020, 0x4e,
                randint(0x00, 0xff),
                randint(0x00, 0xff),
                randint(0x00, 0xff) ] ))
        macs.append(mac)
    return zip(ips, macs)


def get_ipv4_range(network, mask_size):
    net = ( network[0] << 24
            | network[1] << 16
            | network[2] << 8
            | network[3] )
    mask = ~(2**(32-mask_size)-1)
    ip_start = net & mask
    ip_end = net | ~mask
    return [ ((ip & 0xff000000) >> 24,
              (ip & 0xff0000) >> 16,
              (ip & 0xff00) >> 8,
              ip & 0xff)
             for ip in xrange(ip_start, ip_end + 1) ]

class vm5k_deployment(object):
    """ Base class to control a deployment of hosts on Grid'5000
    The base behavior is to deploy a wheezy-x64-base environment and
    to install and configure libvirt from unstable repository.

    The base run() method allows to setup automatically the hosts and
    virtual machines, using the value of the object state.

    """

    def __init__(self, infile = None, resources = None,
                 env_name = 'wheezy-x64-base', env_file = None,
                 vms = None, distribution = 'round-robin',
                 live_plot = False):
        """:params infile: an XML file that describe the topology of the deployment

        :param resources: a dict whose keys are Grid'5000 sites and values are
        dict, whose keys are hosts and ip_mac, where hosts is a list of
        execo.Host and ip_mac is a list of tuple (ip, mac).

        :param env_name: name of the Kadeploy environment

        :param env_file: path to the Kadeploy environment file

        :params vms: dict defining the virtual machines

        :params distribution: how to distribute the vms on the hosts
        (``round-robin`` , ``concentrated``, ``random``)

        :params live_plot: create a figure at the script beginning and add
        """
        print_step('STARTING vm5k_deployment')
        self.state = Element('vm5k')
        self.fact = ActionFactory(remote_tool = SSH,
                                fileput_tool = SCP,
                                fileget_tool = SCP)
        self.distribution = distribution
        self.kavlan = None

        if infile is None:
            self._init_state(resources, vms, infile)
        else:
            self.state = parse(infile)
            self._get_xml_elements()
            self._get_xml_vms()
            self._set_vms_ip_mac()
            self._add_xml_vms()

        if env_file is not None:
            self.env_file = env_file
            self.env_name = None
        else:
            self.env_file = None
            self.env_name = env_name

        logger.info('%s %s %s %s %s %s %s %s',
                    len(self.sites), style.emph('sites'),
                    len(self.clusters), style.user1('clusters'),
                    len(self.hosts), style.host('hosts'),
                    len(self.vms), style.vm('vms'))
        if live_plot:
            self.live_plot = True
            init_live_plot(self.state)
        exit()


    def run(self):
        """Launch the deployment and configuration of hosts and virtual machines"""
        try:
            print_step('HOSTS DEPLOYMENT')
            self.hosts_deployment()

            print_step('MANAGING PACKAGES')
            self.packages_management()

            print_step('CONFIGURING LIBVIRT')
            self.configure_libvirt()

            print_step('CONFIGURING SERVICE NODE')
            self.configure_service_node()

            print_step('VIRTUAL MACHINES')
            self.deploy_vms()
        finally:
            self.get_state()


    def configure_service_node(self):
        if self.kavlan:
            service = 'DNS/DHCP'
            dhcp = True
        else:
            service = 'DNS'
            dhcp = False

        service_node = get_fastest_host(self.hosts)
        logger.info('Setting up %s on %s', style.emph(service), style.host(service_node.address.split('.')[0]))
        clients = list(self.hosts)
        clients.remove(service_node)
        dnsmasq_server(service_node, clients, self.vms, dhcp)

    # VMS deployment
    def deploy_vms(self, disk_location = 'one'):
        """Destroy the existing VMS, create the virtual disks, install the vms, start them and
        wait for boot"""
        logger.info('Destroying existing virtual machines')
        destroy_vms(self.hosts)
        logger.info('Creating the virtual disks ')
        self._remove_existing_disks()
        self._create_backing_file('/grid5000/images/KVM/squeeze-x64-base.qcow2')
        if disk_location == 'one':
            create_disks(self.vms).run()
        elif disk_location == 'all':
            create_disks_on_hosts(self.vms, self.hosts).run()
        logger.info('Installing the virtual machines')
        install_vms(self.vms).run()
        logger.info('Starting the virtual machines')
        start_vms(self.vms).run()
        wait_vms_have_started(self.vms)



    def _create_backing_file(self, from_disk = '/grid5000/images/KVM/squeeze-x64-base.qcow2', to_disk = '/tmp/vm-base.img'):
        """ """
        logger.debug("Copying backing file from frontends")
        copy_file = self.fact.get_fileput(self.hosts, [from_disk], remote_location='/tmp/').run()
        self._actions_hosts(copy_file)

        logger.debug('Creating disk image on '+to_disk)
        cmd = 'qemu-img convert -O raw /tmp/'+from_disk.split('/')[-1]+' '+to_disk
        convert = self.fact.get_remote(cmd, self.hosts).run()
        self._actions_hosts(convert)

        if default_connection_params['user'] == 'root':
            logger.debug('Copying ssh key on '+to_disk+' ...')
            cmd = 'modprobe nbd max_part=1; '+ \
                    'qemu-nbd --connect=/dev/nbd0 '+to_disk+' ; sleep 3 ; '+ \
                    'mount /dev/nbd0p1 /mnt; mkdir /mnt/root/.ssh ; '+ \
                    'cp /root/.ssh/authorized_keys  /mnt/root/.ssh/authorized_keys ; '+\
                    'cp -r /root/.ssh/id_rsa* /mnt/root/.ssh/ ;'+ \
                    'umount /mnt; qemu-nbd -d /dev/nbd0'
            copy_on_vm_base = self.fact.get_remote(cmd, self.hosts).run()
            self._actions_hosts(copy_on_vm_base)

    def _remove_existing_disks(self, hosts = None):
        """Remove all img and qcow2 file from /tmp directory """
        logger.debug('Removing existing disks')
        if hosts is None:
            hosts = self.hosts
        remove = self.fact.get_remote('rm -f /tmp/*.img; rm -f /tmp/*.qcow2', self.hosts).run()
        self._actions_hosts(remove)

    # libvirt configuration
    def configure_libvirt(self, bridge = 'br0'):
        """ """
        self.enable_bridge()
        self._libvirt_uniquify()
        self._libvirt_bridged_network(bridge)
        logger.info('Restarting %s', style.emph('libvirt') )
        self.fact.get_remote('service libvirt-bin restart', self.hosts).run()


    def _libvirt_uniquify(self):
        logger.info('Making libvirt host unique')
        cmd = 'uuid=`uuidgen` && sed -i "s/00000000-0000-0000-0000-000000000000/${uuid}/g" /etc/libvirt/libvirtd.conf '+\
            '&& sed -i "s/#host_uuid/host_uuid/g" /etc/libvirt/libvirtd.conf && service libvirt-bin restart'
        self.fact.get_remote(cmd, self.hosts).run()

    def _libvirt_bridged_network(self, bridge):
        logger.debug('Configuring libvirt network ...')
        # Creating an XML file describing the network
        root = Element('network')
        name = SubElement(root,'name')
        name.text = 'default'
        SubElement(root, 'forward', attrib={'mode':'bridge'})
        SubElement(root, 'bridge', attrib={'name': bridge})
        fd, network_xml = mkstemp(dir = '/tmp/', prefix='create_br_')
        f = fdopen(fd, 'w')
        f.write(prettify(root))
        f.close()
        logger.debug('Destroying existing network')
        destroy = self.fact.get_remote('virsh net-destroy default; virsh net-undefine default', self.hosts)
        destroy.nolog_exit_code = True
        put = self.fact.get_fileput(self.hosts, [network_xml], remote_location = '/etc/libvirt/qemu/networks/')
        start = self.fact.get_remote('virsh net-define /etc/libvirt/qemu/networks/'+network_xml.split('/')[-1]+' ; '+\
                                     'virsh net-start default; virsh net-autostart default;', self.hosts)
        netconf = SequentialActions( [destroy, put, start] ).run()
        self._actions_hosts(netconf)


    # Hosts configuration
    def hosts_deployment(self, max_tries = 1, check_deploy = True):
        """Create the execo_g5k.Deployment"""

        logger.info('Deploying %s hosts \n%s', len(self.hosts),
            ' '.join([ style.host(host.address.split('.')[0]) for host in sorted(self.hosts) ]))
        deployment = Deployment( hosts = [ canonical_host_name(host) for host in self.hosts],
            env_file = self.env_file, env_name = self.env_name,
            vlan = self.kavlan)

        out = True if logger.getEffectiveLevel() <= 10 else False

        deployed_hosts, undeployed_hosts = deploy(deployment, out = out,
                                num_tries = max_tries,
                                check_deployed_command = check_deploy)
        logger.info('Deployed %s hosts \n%s', len(deployed_hosts),
            ' '.join([ style.host(host.address.split('.')[0]) for host in sorted(deployed_hosts)]))
        self._update_hosts_state(deployed_hosts, undeployed_hosts)

        # Renaming hosts if a kavlan is used
        if self.kavlan is not None:
            self.hosts = [ Host(get_kavlan_host_name(host, self.kavlan)) for host in self.hosts]

        # Configuring SSH with precopy of id_rsa and id_rsa.pub keys on all hosts to allow TakTuk connection
        if self.fact.remote_tool == 2:
            taktuk_conf = ('-s', '-S', '$HOME/.ssh/id_rsa:$HOME/.ssh/id_rsa,$HOME/.ssh/id_rsa.pub:$HOME/.ssh')
        else:
            taktuk_conf = ('-s', )
        conf_ssh = self.fact.get_remote(' echo "Host *" >> /root/.ssh/config ;'+
                'echo " StrictHostKeyChecking no" >> /root/.ssh/config; ',
                self.hosts, connection_params = {'taktuk_options': taktuk_conf}).run()
        self._actions_hosts(conf_ssh)


    def enable_bridge(self, name = 'br0'):
        """We need a bridge to have automatic DHCP configuration for the VM."""
        logger.info('Configuring the bridge')
        hosts_br = self._get_bridge(self.hosts)
        nobr_hosts = []
        for host, br in hosts_br.iteritems():
            if br is None:
                logger.debug('No bridge on host %s', style.host(host))
                nobr_hosts.append( host)
            elif br != name:
                logger.debug('Wrong bridge on host %s, destroying it', style.host(host))
                SshProcess('ip link set '+br+' down ; brctl delbr '+br, host).run()
                nobr_hosts.append( host)
            else:
                logger.debug('Bridge %s is present on host %s', style.emph('name'), style.host(host) )

        if len(nobr_hosts) > 0:
            script = 'export br_if=`ip route |grep default |cut -f 5 -d " "`; \n'+\
                'ifdown $br_if ; \n'+\
                'sed -i "s/$br_if inet dhcp/$br_if inet manual/g" /etc/network/interfaces ; \n'+\
                'sed -i "s/auto $br_if//g" /etc/network/interfaces ; \n'+\
                'echo " " >> /etc/network/interfaces ; \n'+\
                'echo "auto '+name+'" >> /etc/network/interfaces ; \n'+\
                'echo "iface '+name+' inet dhcp" >> /etc/network/interfaces ; \n'+\
                'echo "  bridge_ports $br_if" >> /etc/network/interfaces ; \n'+\
                'echo "  bridge_stp off" >> /etc/network/interfaces ; \n'+\
                'echo "  bridge_maxwait 0" >> /etc/network/interfaces ; \n'+\
                'echo "  bridge_fd 0" >> /etc/network/interfaces ; \n'+\
                'ifup '+name
            fd, br_script = mkstemp(dir = '/tmp/', prefix='create_br_')
            f = fdopen(fd, 'w')
            f.write(script)
            f.close()

            self.fact.get_fileput(nobr_hosts, [br_script]).run()
            self.fact.get_remote( 'nohup sh '+br_script.split('/')[-1], nobr_hosts).run()

            logger.debug('Waiting for network restart')
            if_up = False
            nmap_tries = 0
            while (not if_up) and nmap_tries < 20:
                sleep(20)
                nmap_tries += 1
                nmap = SshProcess('nmap '+' '.join( [host.address for host in nobr_hosts ])+' -p 22',
                                  Host(g5k_configuration['default_frontend']),
                                  connection_params = default_frontend_connection_params ).run()
                for line in nmap.stdout.split('\n'):
                    if 'Nmap done' in line:
                        if_up = line.split()[2] == line.split()[5].replace('(','')
            logger.debug('Network has restarted')
        logger.info('All hosts have the bridge %s', style.emph(name) )

    def _get_bridge(self, hosts):
        """ """
        logger.debug('Retrieving bridge on hosts %s', ", ".join( [host.address for host in hosts ]))
        cmd = "brctl show |grep -v 'bridge name' | awk '{ print $1 }' |head -1"
        bridge_exists = self.fact.get_remote(cmd, hosts)
        bridge_exists.nolog_exit_code = True
        bridge_exists.run()
        hosts_br = {}
        for p in bridge_exists.processes:
            stdout = p.stdout.strip()
            if len(stdout) == 0:
                hosts_br[p.host] = None
            else:
                hosts_br[p.host] = stdout
        return hosts_br

    def packages_management(self, upgrade = True, other_packages = None):
        """This method allow to configure APT to use testing and unstable repository, perform """
        self._configure_apt()
        if upgrade:
            self._upgrade_hosts()
        self._install_packages()
        # Post configuration to avoid reboot
        self.fact.get_remote('modprobe kvm; modprobe kvm-intel; modprobe kvm-amd ; chown root:kvm /dev/kvm ;',
                             self.hosts).run()

    def _configure_apt(self):
        """ """
        logger.info('Configuring APT')
        # Create sources.list file
        fd, tmpsource = mkstemp(dir = '/tmp/', prefix='sources.list_')
        f = fdopen(fd, 'w')
        f.write('deb http://ftp.debian.org/debian stable main contrib non-free\n'+\
                'deb http://ftp.debian.org/debian testing main \n'+\
                'deb http://ftp.debian.org/debian unstable main \n')
        f.close()
        # Create preferences file
        fd, tmppref = mkstemp(dir = '/tmp/', prefix='preferences_')
        f = fdopen(fd, 'w')
        f.write('Package: * \nPin: release a=stable \nPin-Priority: 900\n\n'+\
                'Package: * \nPin: release a=testing \nPin-Priority: 850\n\n'+\
                'Package: * \nPin: release a=unstable \nPin-Priority: 800\n\n')
        f.close()
        # Create apt.conf file
        fd, tmpaptconf = mkstemp(dir = '/tmp/', prefix='apt.conf_')
        f = fdopen(fd, 'w')
        f.write('APT::Acquire::Retries=20;\n')
        f.close()

        self.fact.get_fileput(self.hosts, [tmpsource, tmppref, tmpaptconf],
                remote_location = '/etc/apt/').run()
        apt_conf = self.fact.get_remote('cd /etc/apt && '+\
                        'mv '+tmpsource.split('/')[-1]+' sources.list &&'+\
                        'mv '+tmppref.split('/')[-1]+' preferences &&'+\
                        'mv '+tmpaptconf.split('/')[-1]+' apt.conf',
                        self.hosts).run()
        self._actions_hosts(apt_conf)
        Local('rm '+tmpsource+' '+tmppref+' '+tmpaptconf).run()

    def _upgrade_hosts(self):
        """Dist upgrade performed on all hosts"""
        logger.info('Upgrading packages')
        cmd = "echo 'debconf debconf/frontend select noninteractive' | debconf-set-selections ; "+\
              "echo 'debconf debconf/priority select critical' | debconf-set-selections ;      "+\
              "export DEBIAN_MASTER=noninteractive ; apt-get update ; "+\
              "apt-get dist-upgrade -y --force-yes -o Dpkg::Options::='--force-confdef' "+\
              "-o Dpkg::Options::='--force-confold' "
        upgrade = self.fact.get_remote( cmd, self.hosts).run()
        self._actions_hosts(upgrade)

    def _install_packages(self, other_packages = None):
        """Installation of required packages on the hosts"""
        base_packages = 'uuid-runtime bash-completion taktuk locate htop init-system-helpers'
        logger.info('Installing base packages \n%s', style.emph(base_packages))
        cmd = 'export DEBIAN_MASTER=noninteractive ; apt-get update && apt-get install -y --force-yes '+ base_packages
        install_base = self.fact.get_remote(cmd, self.hosts).run()
        self._actions_hosts(install_base)

        libvirt_packages = 'libvirt-bin virtinst python2.7 python-pycurl python-libxml2 qemu-kvm nmap'
        logger.info('Installing libvirt packages \n%s', style.emph(libvirt_packages))
        cmd = 'export DEBIAN_MASTER=noninteractive ; apt-get update && apt-get install -y --force-yes '+\
            '-o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" -t unstable '+\
            libvirt_packages
        install_libvirt = self.fact.get_remote(cmd, self.hosts).run()
        self._actions_hosts(install_libvirt)

        if other_packages is not None:
            logger.info('Installing extra packages \n%s', style.emph(other_packages))
            cmd = 'export DEBIAN_MASTER=noninteractive ; apt-get update && '+\
                'apt-get install -y --force-yes '+other_packages
            install_extra = self.fact.get_remote(cmd, self.hosts).run()
            self._actions_hosts(install_extra)


    # State related methods
    def _init_state(self, resources = None, vms = None, distribution = None, infile = None):
        """Create the topology XML structure describing the vm5k initial state"""
        logger.debug('ELEMENTS')
        self.sites = [ site for site in resources.keys() if site != 'global']

        logger.debug('IP MAC')
        if not resources.has_key('global'):
            if len(self.sites) == 1:
                self.ip_mac = resources[self.sites[0]]['ip_mac']
                if resources[site]['kavlan'] is not None:
                    self.kavlan = resources[site]['kavlan']
            else:
                self.ip_mac = { site: resources[site]['ip_mac'] for site in self.sites}
        else:
            self.ip_mac = resources['global']['ip_mac']
            self.kavlan = resources['global']['kavlan']
            self.kavlan_site = resources['global']['site']


        logger.debug('KaVLAN: %s', self.kavlan)


        logger.debug('ELEMENTS')
        self.sites = []
        self.clusters = []
        self.hosts = []
        for site, elements in resources.iteritems():
            if site not in self.sites and site in get_g5k_sites():
                self.sites.append(site)
            if site != 'global':
                self.hosts += elements['hosts']

        self.sites.sort()
        self.hosts.sort( key = lambda host: (host.address.split('.',1)[0].split('-')[0],
                                        int( host.address.split('.',1)[0].split('-')[1] )))
        self.clusters = list(set([ get_host_cluster(host) for host in self.hosts ]))
        self.clusters.sort()
        self._add_xml_elements()


        logger.debug('Virtual Machines')
        max_vms = get_max_vms(self.hosts)
        if vms is not None:
            self.vms = vms if len(vms) <= max_vms else vms[0:max_vms]
            distribute_vms(vms, self.hosts, self.distribution)
            self._set_vms_ip_mac()
            self._add_xml_vms()
        else:
            self.vms = []





    def _set_vms_ip_mac(self):
        """Not finished """
        if isinstance(self.ip_mac, dict):
            i_vm = {site: 0 for site in self.sites }
            for vm in self.vms:
                vm_site = get_host_site(vm['host'])
                vm['ip'], vm['mac'] = self.ip_mac[vm_site][i_vm[vm_site]]
                i_vm[vm_site] += 1
        else:
            i_vm = 0
            for vm in self.vms:
                vm['ip'], vm['mac'] = self.ip_mac[i_vm]
                i_vm += 1


    def _get_xml_elements(self):
        """Get sites, clusters and host from self.state """
        self.sites = [ site.id for site in self.state.findall('./site') ]
        self.clusters = [ cluster.id for cluster in self.state.findall('.//cluster') ]
        self.hosts = [ host.id for host in self.state.findall('.//host') ]

    def _get_xml_vms(self):
        """Define the list of VMs from the infile """
        self.vms = []

        def _default_xml_value(key):
            return default_vm[key] if key not in vm.attrib else vm.get(key)

        for vm in self.state.findall('.//vm'):
            self.vms.append( {'id': vm.get('id'),
                    'n_cpu': _default_xml_value['n_cpu'],
                    'cpuset': _default_xml_value['cpuset'],
                    'mem': _default_xml_value['mem'],
                    'hdd': _default_xml_value['hdd'],
                    'backing_file': _default_xml_value['backing_file'],
                    'host': _default_xml_value['host'] } )

    def _add_xml_elements(self):
        """Add sites, clusters, hosts to self.state """
        _state = self.state
        logger.debug('Initial state \n %s', prettify(_state))
        for site in self.sites:
            SubElement(_state, 'site', attrib = {'id': site})
        logger.debug('Sites added \n %s', prettify(_state))
        for cluster in self.clusters:
            el_site = _state.find("./site[@id='"+get_cluster_site(cluster)+"']")
            SubElement(el_site, 'cluster', attrib = {'id': cluster})
        logger.debug('Clusters added \n %s', prettify(_state))
        for host in self.hosts:
            el_cluster = _state.find(".//cluster/[@id='"+get_host_cluster(host)+"']")
            SubElement(el_cluster, 'host', attrib = {'id': host.address,
                                                        'state': 'Undeployed'})
        logger.debug('Hosts added \n %s', prettify(_state))

    def _add_xml_vms(self):
        """Add vms distributed on hosts to self.state """
        for vm in self.vms:
            host = self.state.find(".//host/[@id='"+vm['host'].address+"']")
            SubElement(host, 'vm', attrib = {'id': vm['id'],
                                             'ip': vm['ip'],
                                             'mac': vm['mac'],
                                             'mem': str(vm['mem']),
                                             'n_cpu': str(vm['n_cpu']),
                                             'cpuset': vm['cpuset'],
                                             'hdd': str(vm['hdd']),
                                             'backing_file': vm['backing_file'],
                                             'state': vm['state'] })

    def get_state(self, output = True, mode = 'compact', plot = False):
        """ """

        if output:
            output = 'vm5k_'+strftime('%Y%m%d_%H%M%S',localtime())+'.xml'
            f = open(output, 'w')
            f.write(prettify(self.state))
            f.close()

        if mode == 'compact':
            log = self._print_state_compact()

        if plot == True:
            print 'plot'

        logger.info('State %s', log)

    def _print_state_compact(self):
        dist = {}
        max_len_host = 0
        for vm in self.vms:
            host = vm['host'].address.split('.')[0]
            if len(host) > max_len_host:
                max_len_host = len(host)
            if host not in dist.keys():
                dist[host] = { vm['id']: vm['state'] }
            else:
                dist[host][vm['id']] = vm['state']
        log = ''
        for host, vms in dist.iteritems():
            log += '\n'+style.host(host)+': '.ljust(max_len_host+2-len(host))
            for vm in sorted(vms.keys()):
                if vms[vm] == 'OK':
                    log += style.OK(vm)
                elif vms[vm] == 'KO':
                    log += style.KO(vm)
                else:
                    log += style.Unknown(vm)
                log += ' '
        return log

    def _update_hosts_state(self, hosts_ok, hosts_ko):
        """ """
        for host in hosts_ok:
            if host is not None:
                if self.kavlan is None:
                    address = host.address
                else:
                    address = kavname_to_basename(host).address
                self.state.find(".//host/[@id='"+address+"']").set('state', 'OK')
        for host in hosts_ko:
            if self.kavlan is None:
                address = host.address
            else:
                address = kavname_to_basename(host).address
            self.state.find(".//host/[@id='"+address+"']").set('state', 'KO')
            self.hosts.remove(host)
            if len(self.vms) > 0:
                distribute_vms(self.vms, self.hosts, self.distribution)

        if len(self.hosts) == 0:
            logger.error('Not enough hosts available, because %s are KO',
                         [ style.host(host.address) for host in hosts_ok])



    def _actions_hosts(self, action):
        hosts_ok, hosts_ko = [], []
        for p in action.processes:
            if p.ok:
                hosts_ok.append(p.host)
            else:
                logger.warn('%s is KO', p.host)
                hosts_ko.append(p.host)
        hosts_ok, hosts_ko = list(set(hosts_ok)), list(set(hosts_ko))
        self._update_hosts_state(hosts_ok, hosts_ko)


def distribute_vms(vms, hosts, distribution = 'round-robin'):
    """ """
    logger.debug('Initial virtual machines distribution \n%s',
        "\n".join( [ vm['id']+": "+str(vm['host']) for vm in vms] ))
    if distribution in ['round-robin', 'concentrated']:
        attr = get_CPU_RAM_FLOPS(hosts)
        dist_hosts = hosts[:]
        iter_hosts = cycle(dist_hosts)
        host = iter_hosts.next()
        for vm in vms:
            remaining = attr[host.address].copy()
            while remaining['RAM'] - vm['mem'] <= 0 \
                or remaining['CPU'] - vm['n_cpu']/3 <= 0:

                dist_hosts.remove(host)

                if len(dist_hosts) == 0:
                    req_mem = sum( [ vm['mem'] for vm in vms])
                    req_cpu = sum( [ vm['n_cpu'] for vm in vms])/3
                    logger.error('Not enough ressources ! \n'+'RAM'.rjust(20)+'CPU'.rjust(10)+'\n'+\
                                 'Available'.ljust(15)+'%s Mb'.ljust(15)+'%s \n'+\
                                 'Needed'.ljust(15)+'%s Mb'.ljust(15)+\
                                 '%s \n', attr['TOTAL']['RAM'], attr['TOTAL']['CPU'],req_mem, req_cpu)

                iter_hosts = cycle(dist_hosts)
                host = iter_hosts.next()
                remaining = attr[host.address].copy()


            vm['host'] = host
            remaining['RAM'] -= vm['mem']
            remaining['CPU'] -= vm['n_cpu']/3
            attr[host.address] = remaining.copy()
            if distribution == 'round-robin':
                host = iter_hosts.next()
                remaining = attr[host.address].copy()
            if distribution ==  'random':
                for i in range(randint(0, len(dist_hosts))):
                    host = iter_hosts.next()

    elif distribution == 'n_by_hosts':
        vms_by_host = len(vms)/len(hosts)

    logger.debug('Final virtual machines distribution \n%s',
        "\n".join( [ vm['id']+": "+str(vm['host']) for vm in vms ] ) )


def get_CPU_RAM_FLOPS(hosts):
    """Return the number of CPU and amount RAM for a host list """
    hosts_attr = {'TOTAL': {'CPU': 0 ,'RAM': 0}}
    cluster_attr = {}
    for host in hosts:
        cluster = get_host_cluster(host)
        if not cluster_attr.has_key(cluster):
            attr = get_host_attributes(host)
            cluster_attr[cluster] = {'CPU': attr['architecture']['smt_size'],
                                     'RAM': int(attr['main_memory']['ram_size']/10**6),
                                     'flops': attr['performance']['node_flops'] }
        hosts_attr[host.address] = cluster_attr[cluster]
        hosts_attr['TOTAL']['CPU'] += attr['architecture']['smt_size']
        hosts_attr['TOTAL']['RAM'] += int(attr['main_memory']['ram_size']/10**6)

    logger.debug(pformat(hosts_attr))
    return hosts_attr

def get_fastest_host(hosts):
        """ Use the G5K api to have the fastest node"""
        attr = get_CPU_RAM_FLOPS(hosts)
        max_flops = 0
        for host in hosts:
            flops = attr[host.address]['flops']
            if  flops > max_flops:
                max_flops = flops
                fastest_host = host
        return fastest_host

def get_max_vms(hosts, n_cpu = 1, mem = 512):
    """Return the maximum number of virtual machines that can be created on the host"""
    total = get_CPU_RAM_FLOPS(hosts)['TOTAL']
    return min(int(3*total['CPU']/n_cpu), int(total['RAM']/mem-1))


def get_vms_slot(vms, elements, slots, excluded_elements = None):
    """Return a slot with enough RAM and CPU """
    chosen_slot = None


    req_ram = sum( [ vm['mem'] for vm in vms] )
    req_cpu = sum( [ vm['n_cpu'] for vm in vms] ) /3
    logger.debug('RAM %s CPU %s', req_ram, req_cpu)


    for slot in slots:
        hosts = []
        for element in elements:
            n_hosts = slot[2][element]
            if element in get_g5k_clusters():
                for i in range(n_hosts):
                    hosts.append(Host(str(element+'-1.'+get_cluster_site(element)+'.grid5000.fr')))
        attr = get_CPU_RAM_FLOPS(hosts)['TOTAL']
        if attr['CPU'] > req_cpu and attr['RAM'] > req_ram:
            chosen_slot = slot
            break

        del hosts[:]

    if chosen_slot is None:
        return None, None

    resources = {}
    for host in hosts:
        if req_ram < 0 and req_cpu < 0:
            break
        attr = get_CPU_RAM_FLOPS([host])
        req_ram -= attr[host.address]['RAM']
        req_cpu -= attr[host.address]['CPU']
        cluster = get_host_cluster(host)
        if not resources.has_key(cluster):
            resources[element] = 1
        else:
            resources[element] += 1

    return chosen_slot[0], distribute_hosts(chosen_slot[2], resources, excluded_elements)


def print_step(step_desc = None):
    """ """
    logger.info(style.step(' '+step_desc+' ').center(50) )


def prettify(elem):
    """Return a pretty-printed XML string for the Element.  """
    rough_string = tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ").replace('<?xml version="1.0" ?>\n', '')

def kavname_to_basename( host):
    """ """
    if 'kavlan' in host.address:
        return Host(host.address.split('kavlan')[0][0:-1]+'.'+'.'.join(host.address.split('.')[1:]))
    else:
        return host