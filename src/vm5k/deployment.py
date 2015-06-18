# Copyright 2012-2014 INRIA Rhone-Alpes, Service Experimentation et
# Developpement
#
# This file is part of Vm5k.
#
# Vm5k is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Vm5k is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
# License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Vm5k.  If not, see <http://www.gnu.org/licenses/>
import sys
from os import fdopen
from xml.etree.ElementTree import Element, SubElement, parse
from time import localtime, strftime
from tempfile import mkstemp
from execo import logger, Process, SshProcess, SequentialActions, Host, \
    Local, sleep, TaktukPut, Timer
from execo.action import ActionFactory, ParallelActions
from execo.log import style
from execo.config import TAKTUK, CHAINPUT
from execo_g5k import deploy, Deployment
from execo_g5k.api_utils import get_host_cluster, \
    get_cluster_site, get_host_site, canonical_host_name
from execo_g5k.utils import get_kavlan_host_name
from vm5k.config import default_vm
from vm5k.actions import create_disks, install_vms, start_vms, \
    wait_vms_have_started, destroy_vms, create_disks_all_hosts, distribute_vms
from vm5k.utils import prettify, print_step, get_fastest_host, \
    hosts_list, get_CPU_RAM_FLOPS
from vm5k.services import dnsmasq_server, setup_aptcacher_server, configure_apt_proxy


class vm5k_deployment():
    """ Base class to control a deployment of hosts and virtual machines on
    Grid'5000. It helps to  deploy a wheezy-x64-base environment,
    to install and configure libvirt from testing repository, and to deploy
    virtual machines.

    The base run() method allows to setup automatically the hosts and
    virtual machines, using the value of the object.
    """

    def __init__(self, infile=None, resources=None, env_name=None,
                 env_file=None, vms=None, distribution=None,
                 outdir=None):
        """:param infile: an XML file that describe the topology of the
        deployment

        :param resources: a dict whose keys are Grid'5000 sites and values are
        dict, whose keys are hosts and ip_mac, where hosts is a list of
        execo.Host and ip_mac is a list of tuple (ip, mac).

        :param env_name: name of the Kadeploy environment

        :param env_file: path to the Kadeploy environment file

        :params vms: dict defining the virtual machines

        :params distribution: how to distribute the vms on the hosts
        (``round-robin`` , ``concentrated``, ``random``)

        :params outdir: directory to store the deployment files
        """
        print_step('Initializing vm5k_deployment')
        # set a factory for the deployment that use taktuk and chainput
        self.fact = ActionFactory(remote_tool=TAKTUK,
                                  fileput_tool=CHAINPUT,
                                  fileget_tool=TAKTUK)
        self.kavlan = None
        self.kavlan_site = None
        if env_name is not None:
            self.env_file = None
            if ':' not in env_name:
                self.env_name, self.env_user = env_name, None
            else:
                self.env_user, self.env_name = env_name.split(':')
        else:
            if env_file is not None:
                self.env_name = None
                self.env_user = None
                self.env_file = env_file
            else:
                self.env_name = 'vm5k'
                self.env_user = 'lpouilloux'
                self.env_file = None

        if outdir:
            self.outdir = outdir
        else:
            self.outdir = 'vm5k_' + strftime("%Y%m%d_%H%M%S_%z")

        self.copy_actions = None

        self.state = Element('vm5k')
        self._define_elements(infile, resources, vms, distribution)

        network = 'IP range from KaVLAN' if self.kavlan \
            else 'IP range from g5k-subnet'
        logger.info('%s\n%s %s \n%s %s \n%s %s \n%s %s',
                    network,
                    len(self.sites), style.emph('sites'),
                    len(self.clusters), style.user1('clusters'),
                    len(self.hosts), style.host('hosts'),
                    len(self.vms), style.vm('vms'))

    # PUBLIC METHODS
    def run(self):
        """Launch the deployment and configuration of hosts and virtual
        machines: hosts_deployment, packages_mamangement, configure_service_node
        configure_libvirt, deploy_vms"""
        try:
            print_step('HOSTS DEPLOYMENT')
            self.hosts_deployment()

            print_step('MANAGING PACKAGES')
            self.packages_management()

            print_step('CONFIGURING SERVICE NODE')
            self.configure_service_node()

            print_step('CONFIGURING LIBVIRT')
            self.configure_libvirt()

            print_step('VIRTUAL MACHINES')
            self.deploy_vms()
        finally:
            self.get_state()

    def hosts_deployment(self, max_tries=1, check_deploy=True,
                         conf_ssh=True):
        """Deploy the hosts using kadeploy, configure ssh for taktuk execution
        and launch backing file disk copy"""
        self._launch_kadeploy(max_tries, check_deploy)
        if conf_ssh:
            self._configure_ssh()

    def packages_management(self, upgrade=True, other_packages=None,
                            launch_disk_copy=True, apt_cacher=False):
        """Configure APT to use testing repository,
        perform upgrade and install required packages. Finally start
        kvm module"""
        self._configure_apt()
        if upgrade:
            self._upgrade_hosts()
        self._install_packages(other_packages=other_packages,
                               launch_disk_copy=launch_disk_copy)
        if apt_cacher:
            setup_aptcacher_server(self.hosts)
        # Post configuration to load KVM
        self.fact.get_remote(
            'modprobe kvm; modprobe kvm-intel; modprobe kvm-amd ; ' + \
            'chown root:kvm /dev/kvm ;', self.hosts).run()

    def configure_service_node(self):
        """Setup automatically a DNS server to access virtual machines by id
        and also install a DHCP server if kavlan is used"""
        if self.kavlan:
            service = 'DNS/DHCP'
            dhcp = True
        else:
            service = 'DNS'
            dhcp = False

        service_node = get_fastest_host(self.hosts)
        logger.info('Setting up %s on %s', style.emph(service),
                    style.host(service_node.split('.')[0]))
        clients = list(self.hosts)
        clients.remove(service_node)
        dnsmasq_server(service_node, clients, self.vms, dhcp)

    def configure_libvirt(self, bridge='br0', libvirt_conf=None):
        """Enable a bridge if needed on the remote hosts, configure libvirt
        with a bridged network for the virtual machines, and restart service.
        """
        self._enable_bridge()
        self._libvirt_check_service()
        self._libvirt_uniquify()
        self._libvirt_bridged_network(bridge)
        logger.info('Restarting %s', style.emph('libvirt'))
        self.fact.get_remote('service libvirtd restart', self.hosts).run()

    def deploy_vms(self, clean_disks=False, disk_location='one',
                   apt_cacher=False):
        """Destroy the existing VMS, create the virtual disks, install the vms
        start them and wait until they have rebooted"""
        logger.info('Destroying existing virtual machines')
        destroy_vms(self.hosts, undefine=True)
        if clean_disks:
            self._remove_existing_disks()
        logger.info('Creating the virtual disks ')
        self._create_backing_file()
        if disk_location == 'one':
            logger.info('Create disk on each nodes')
            create_disks(self.vms).run()
        elif disk_location == 'all':
            logger.info('Create all disks on all nodes')
            create_disks_all_hosts(self.vms, self.hosts).run()
        logger.info('Installing the virtual machines')
        install_vms(self.vms).run()
        logger.info('Starting the virtual machines')
        self.boot_time = Timer()
        start_vms(self.vms).run()
        logger.info('Waiting for VM to boot ...')
        wait_vms_have_started(self.vms, self.hosts[0])
        self._update_vms_xml()
        if apt_cacher:
            configure_apt_proxy(self.vms)

    def get_state(self, name=None, output=True, mode='compact', plot=False):
        """ """
        if not name:
            name = 'vm5k_' + strftime('%Y%m%d_%H%M%S', localtime())
        if output:
            output = self.outdir + '/' + name + '.xml'
            f = open(output, 'w')
            f.write(prettify(self.state))
            f.close()

        if mode == 'compact':
            log = self._print_state_compact()

        logger.info('State %s', log)

    # PRIVATE METHODS
    def _launch_kadeploy(self, max_tries=1, check_deploy=True):
        """Create a execo_g5k.Deployment object, launch the deployment and
        return a tuple (deployed_hosts, undeployed_hosts)
        """
        logger.info('Deploying %s hosts \n%s', len(self.hosts),
                    hosts_list(self.hosts))
        deployment = Deployment(hosts=[Host(canonical_host_name(host))
                                       for host in self.hosts],
                                env_file=self.env_file,
                                env_name=self.env_name,
                                user=self.env_user,
                                vlan=self.kavlan)
        # Activate kadeploy output log if log level is debug
        if logger.getEffectiveLevel() <= 10:
            stdout = [sys.stdout]
            stderr = [sys.stderr]
        else:
            stdout = None
            stderr = None

        deployed_hosts, undeployed_hosts = deploy(deployment,
                                                  stdout_handlers=stdout,
                                                  stderr_handlers=stderr,
                                                  num_tries=max_tries,
                                                  check_deployed_command=check_deploy)
        deployed_hosts = list(deployed_hosts)
        undeployed_hosts = list(undeployed_hosts)
        # Renaming hosts if a kavlan is used
        if self.kavlan:
            for i, host in enumerate(deployed_hosts):
                deployed_hosts[i] = get_kavlan_host_name(host, self.kavlan)
            for i, host in enumerate(undeployed_hosts):
                undeployed_hosts[i] = get_kavlan_host_name(host, self.kavlan)
        logger.info('Deployed %s hosts \n%s', len(deployed_hosts),
                    hosts_list(deployed_hosts))
        cr = '\n' if len(undeployed_hosts) > 0 else ''
        logger.info('Failed %s hosts %s%s', len(undeployed_hosts), cr,
                    hosts_list(undeployed_hosts))
        self._update_hosts_state(deployed_hosts, undeployed_hosts)
        return deployed_hosts, undeployed_hosts

    def _configure_ssh(self):
        if self.fact.remote_tool == 2:
            # Configuring SSH with precopy of id_rsa and id_rsa.pub keys on all
            # host to allow TakTuk connection
            taktuk_conf = ('-s', '-S',
                           '$HOME/.ssh/id_rsa:$HOME/.ssh/id_rsa,' +
                           '$HOME/.ssh/id_rsa.pub:$HOME/.ssh')
        else:
            taktuk_conf = ('-s', )
        conf_ssh = self.fact.get_remote('echo "Host *" >> /root/.ssh/config ;' +
                                        'echo " StrictHostKeyChecking no" >> /root/.ssh/config; ',
                                        self.hosts,
                                        connection_params={'taktuk_options': taktuk_conf}).run()
        self._actions_hosts(conf_ssh)

    def _start_disk_copy(self, disks=None):
        """ """
        disks_copy = []
        if not disks:
            disks = self.backing_files
        for bf in disks:
            logger.info('Treating ' + style.emph(bf))
            logger.debug("Checking frontend disk vs host disk")
            raw_disk = '/root/' + bf.split('/')[-1]
            f_disk = Process('md5sum -t ' + bf).run()
            disk_hash = f_disk.stdout.split(' ')[0]
            cmd = 'if [ -f ' + raw_disk + ' ]; ' + \
                'then md5sum  -t ' + raw_disk + '; fi'
            h_disk = self.fact.get_remote(cmd, self.hosts).run()
            disk_ok = True
            for p in h_disk.processes:

                if p.stdout.split(' ')[0] != disk_hash:
                    disk_ok = False
                    break
            if disk_ok:
                logger.info("Disk " + style.emph(bf) +
                            " is already present, skipping copy")
            else:
                disks_copy.append(self.fact.get_fileput(self.hosts, [bf]))
        if len(disks_copy) > 0:
            self.copy_actions = ParallelActions(disks_copy).start()
        else:
            self.copy_actions = Local('ls').run()

    def _create_backing_file(self, disks=None):
        """ """
        if not self.copy_actions:
            self._start_disk_copy(disks)
        if not self.copy_actions.ended:
            logger.info("Waiting for the end of the disks copy")
            self.copy_actions.wait()
        if not disks:
            disks = self.backing_files
        for bf in disks:
            raw_disk = '/root/' + bf.split('/')[-1]
            to_disk = '/tmp/' + bf.split('/')[-1]
            self.fact.get_remote('cp ' + raw_disk + ' ' + to_disk, self.hosts).run()
            logger.info('Copying ssh key on ' + to_disk + ' ...')
            cmd = 'modprobe nbd max_part=16; ' + \
                'qemu-nbd --connect=/dev/nbd0 ' + to_disk + \
                ' ; sleep 3 ; partprobe /dev/nbd0 ; ' + \
                'part=`fdisk -l /dev/nbd0 |grep dev|grep Linux| grep -v swap|cut -f 1 -d " "` ; ' + \
                'mount $part /mnt ; mkdir -p /mnt/root/.ssh ; ' + \
                'cat /root/.ssh/authorized_keys >> /mnt/root/.ssh/authorized_keys ; ' + \
                'cp -r /root/.ssh/id_rsa* /mnt/root/.ssh/ ;' + \
                'umount /mnt; qemu-nbd -d /dev/nbd0'
            logger.detail(cmd)
            copy_on_vm_base = self.fact.get_remote(cmd, self.hosts).run()
            self._actions_hosts(copy_on_vm_base)

    def _remove_existing_disks(self, hosts=None):
        """Remove all img and qcow2 file from /tmp directory """
        logger.info('Removing existing disks')
        if hosts is None:
            hosts = self.hosts
        remove = self.fact.get_remote('rm -f /tmp/*.img; rm -f /tmp/*.qcow2',
                                      self.hosts).run()
        self._actions_hosts(remove)

    def _libvirt_check_service(self):
        """ """
        logger.info('Checking libvirt service name')
        cmd = "if [ ! -e /etc/init.d/libvirtd ]; " + \
            "  then if [ -e /etc/init.d/libvirt-bin ]; " + \
            "       then ln -s /etc/init.d/libvirt-bin /etc/init.d/libvirtd; " + \
            "       else echo 1; " + \
            "        fi; " + \
            "else echo 0; fi"
        check_libvirt = self.fact.get_remote(cmd, self.hosts).run()
        self._actions_hosts(check_libvirt)

    def _libvirt_uniquify(self):
        logger.info('Making libvirt host unique')
        cmd = 'uuid=`uuidgen` ' + \
            '&& sed -i "s/.*host_uuid.*/host_uuid=\\"${uuid}\\"/g" ' + \
            '/etc/libvirt/libvirtd.conf ' + \
            '&& service libvirtd restart'
        logger.debug(cmd)
        self.fact.get_remote(cmd, self.hosts).run()

    def _libvirt_bridged_network(self, bridge):
        logger.info('Configuring libvirt network')
        # Creating an XML file describing the network
        root = Element('network')
        name = SubElement(root, 'name')
        name.text = 'default'
        SubElement(root, 'forward', attrib={'mode': 'bridge'})
        SubElement(root, 'bridge', attrib={'name': bridge})
        fd, network_xml = mkstemp(dir='/tmp/', prefix='create_br_')
        f = fdopen(fd, 'w')
        f.write(prettify(root))
        f.close()
        logger.debug('Destroying existing network')
        destroy = self.fact.get_remote('virsh net-destroy default; ' +
                                       'virsh net-undefine default',
                                       self.hosts)
        put = TaktukPut(self.hosts, [network_xml],
                        remote_location='/root/')
        start = self.fact.get_remote(
            'virsh net-define /root/' + \
            network_xml.split('/')[-1] + ' ; ' + \
            'virsh net-start default; virsh net-autostart default;',
            self.hosts)
        netconf = SequentialActions([destroy, put, start]).run()
        self._actions_hosts(netconf)

    # Hosts configuration
    def _enable_bridge(self, name='br0'):
        """We need a bridge to have automatic DHCP configuration for the VM."""
        logger.info('Configuring the bridge')
        hosts_br = self._get_bridge(self.hosts)
        nobr_hosts = []
        for host, br in hosts_br.iteritems():
            if br is None:
                logger.debug('No bridge on host %s', style.host(host))
                nobr_hosts.append(host)
            elif br != name:
                logger.debug('Wrong bridge on host %s, destroying it',
                             style.host(host))
                SshProcess('ip link set ' + br + ' down ; brctl delbr ' + br,
                            host).run()
                nobr_hosts.append(host)
            else:
                logger.debug('Bridge %s is present on host %s',
                             style.emph('name'), style.host(host))

        nobr_hosts = map(lambda x: x.address if isinstance(x, Host) else x, 
                         nobr_hosts)

        if len(nobr_hosts) > 0:
            logger.debug('Creating bridge on %s', hosts_list(nobr_hosts))
            script = 'export br_if=`ip route |grep default |cut -f 5 -d " "`; \n' + \
    'ifdown $br_if ; \n' + \
    'sed -i "s/$br_if inet dhcp/$br_if inet manual/g" /etc/network/interfaces ; \n' + \
    'sed -i "s/auto $br_if//g" /etc/network/interfaces ; \n' + \
    'echo " " >> /etc/network/interfaces ; \n' + \
    'echo "auto ' + name + '" >> /etc/network/interfaces ; \n' + \
    'echo "iface ' + name + ' inet dhcp" >> /etc/network/interfaces ; \n' + \
    'echo "  bridge_ports $br_if" >> /etc/network/interfaces ; \n' + \
    'echo "  bridge_stp off" >> /etc/network/interfaces ; \n' + \
    'echo "  bridge_maxwait 0" >> /etc/network/interfaces ; \n' + \
    'echo "  bridge_fd 0" >> /etc/network/interfaces ; \n' + \
    'ifup ' + name
            fd, br_script = mkstemp(dir='/tmp/', prefix='create_br_')
            f = fdopen(fd, 'w')
            f.write(script)
            f.close()

            TaktukPut(nobr_hosts, [br_script]).run()
            self.fact.get_remote('nohup sh ' + br_script.split('/')[-1],
                                 nobr_hosts).run()

            logger.debug('Waiting for network restart')
            if_up = False
            nmap_tries = 0
            while (not if_up) and nmap_tries < 20:
                sleep(20)
                nmap_tries += 1
                nmap = Process('nmap ' +
                               ' '.join([host for host in nobr_hosts]) +
                               ' -p 22').run()
                for line in nmap.stdout.split('\n'):
                    if 'Nmap done' in line:
                        if_up = line.split()[2] == line.split()[5].replace('(',
                                                                           '')
            logger.debug('Network has been restarted')
        logger.info('All hosts have the bridge %s', style.emph(name))

    def _get_bridge(self, hosts):
        """ """
        logger.debug('Retrieving bridge on hosts %s',
                     ", ".join([host for host in hosts]))
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

    def _configure_apt(self):
        """Create the sources.list file """
        logger.info('Configuring APT')
        # Create sources.list file
        fd, tmpsource = mkstemp(dir='/tmp/', prefix='sources.list_')
        f = fdopen(fd, 'w')
        f.write('deb http://ftp.debian.org/debian wheezy main contrib non-free\n' + \
                'deb http://ftp.debian.org/debian wheezy-backports main contrib non-free\n' + \
                'deb http://security.debian.org/ wheezy/updates main contrib non-free\n')
        f.close()
        # Create preferences file
        fd, tmppref = mkstemp(dir='/tmp/', prefix='preferences_')
        f = fdopen(fd, 'w')
        f.write('Package: * \nPin: release a=wheezy \nPin-Priority: 900\n\n' + \
                'Package: * \nPin: release a=wheezy-backports \nPin-Priority: 875\n\n')
        f.close()
        # Create apt.conf file
        fd, tmpaptconf = mkstemp(dir='/tmp/', prefix='apt.conf_')
        f = fdopen(fd, 'w')
        f.write('APT::Acquire::Retries=20;\n')
        f.close()

        TaktukPut(self.hosts, [tmpsource, tmppref, tmpaptconf],
                  remote_location='/etc/apt/').run()
        cmd = 'cd /etc/apt && ' + \
            'mv ' + tmpsource.split('/')[-1] + ' sources.list &&' + \
            'mv ' + tmppref.split('/')[-1] + ' preferences &&' + \
            'mv ' + tmpaptconf.split('/')[-1] + ' apt.conf'
        apt_conf = self.fact.get_remote(cmd, self.hosts).run()
        self._actions_hosts(apt_conf)
        Local('rm ' + tmpsource + ' ' + tmppref + ' ' + tmpaptconf).run()

    def _upgrade_hosts(self):
        """Dist upgrade performed on all hosts"""
        logger.info('Upgrading packages')
        cmd = "echo 'debconf debconf/frontend select noninteractive' | debconf-set-selections ; " + \
              "echo 'debconf debconf/priority select critical' | debconf-set-selections ;      " + \
              "export DEBIAN_MASTER=noninteractive ; apt-get update ; " + \
              "apt-get dist-upgrade -y --force-yes -o Dpkg::Options::='--force-confdef' " + \
              "-o Dpkg::Options::='--force-confold' "
        upgrade = self.fact.get_remote(cmd, self.hosts).run()
        self._actions_hosts(upgrade)

    def _install_packages(self, other_packages=None, launch_disk_copy=True):
        """Installation of required packages on the hosts"""
        base_packages = 'uuid-runtime bash-completion taktuk locate htop init-system-helpers netcat-traditional'
        logger.info('Installing base packages \n%s', style.emph(base_packages))
        cmd = 'export DEBIAN_MASTER=noninteractive ; apt-get update && apt-get ' + \
            'install -y --force-yes --no-install-recommends ' + base_packages
        install_base = self.fact.get_remote(cmd, self.hosts).run()
        self._actions_hosts(install_base)
        if launch_disk_copy:
            self._start_disk_copy()
        libvirt_packages = 'libvirt-bin virtinst python2.7 python-pycurl python-libxml2 qemu-kvm nmap libgmp10'
        logger.info('Installing libvirt packages \n%s',
                    style.emph(libvirt_packages))
        cmd = 'export DEBIAN_MASTER=noninteractive ; apt-get update && apt-get install -y --force-yes '+\
            '-o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" -t wheezy-backports '+\
            libvirt_packages
        install_libvirt = self.fact.get_remote(cmd, self.hosts).run()
        self._actions_hosts(install_libvirt)
        if other_packages:
            self._other_packages(other_packages)

    def _other_packages(self, other_packages=None):
        """Installation of packages"""
        other_packages = other_packages.replace(',', ' ')
        logger.info('Installing extra packages \n%s',
                    style.emph(other_packages))

        cmd = 'export DEBIAN_MASTER=noninteractive ; ' + \
            'apt-get update && apt-get install -y --force-yes ' + \
            other_packages
        install_extra = self.fact.get_remote(cmd, self.hosts).run()
        self._actions_hosts(install_extra)

    # State related methods
    def _define_elements(self, infile=None, resources=None, vms=None,
                         distribution=None):
        """Create the list of sites, clusters, hosts, vms and check
        correspondance between infile and resources"""
        self._get_ip_mac(resources)
        self._get_resources_elements(resources)
        if not infile:
            self.vms = vms
            self.distribution = distribution if distribution else 'round-robin'
        else:
            xml = parse(infile)
            if self._check_xml_elements(xml, resources):
                self.vms = self._get_xml_vms(xml)
                self.distribution = None
            else:
                exit()

        self._add_xml_elements()
        if self.vms:
            distribute_vms(self.vms, self.hosts, self.distribution)
            self._set_vms_ip_mac()
            self._add_xml_vms()
        else:
            self.vms = []

        self.backing_files = list(set([vm['backing_file'] for vm in self.vms]))

    def _get_ip_mac(self, resources):
        """ """
        if len(resources.keys()) == 1:
            # mono site
            self.ip_mac = resources[resources.keys()[0]]['ip_mac']
            self.kavlan = resources[resources.keys()[0]]['kavlan']
        elif 'global' in resources:
            # multi site in a global kavlan
            self.ip_mac = resources['global']['ip_mac']
            self.kavlan = resources['global']['kavlan']
            self.kavlan_site = resources['global']['site']
        else:
            # multi site in prod network
            self.ip_mac = {site: resource['ip_mac']
                           for site, resource in resources.iteritems()}
        if isinstance(self.ip_mac, list) and len(self.ip_mac) == 0:
            logger.error('No ip_range given in the resources')
            exit()
        elif isinstance(self.ip_mac, dict):
            for ip_mac in self.ip_mac.itervalues():
                if len(ip_mac) == 0:
                    logger.error('No ip_range given in the resources')
                    exit()

    def _get_resources_elements(self, resources=None):
        """ """
        self.sites = sorted([site for site in resources.keys()
                                if site != 'global'])
        self.hosts = []
        for site in self.sites:
            if self.kavlan:
                self.hosts += map(lambda host: get_kavlan_host_name(host,
                                    self.kavlan), resources[site]['hosts'])
            else:
                self.hosts += resources[site]['hosts']
        self.hosts.sort(key=lambda host: (host.split('.', 1)[0].split('-')[0],
                                    int(host.split('.', 1)[0].split('-')[1])))
        self.clusters = list(set([get_host_cluster(host)
                                  for host in self.hosts]))
        self.clusters.sort()

    def _check_xml_elements(self, xml, resources, strict=False):
        sites, clusters, hosts = self._get_xml_elements(xml)
        ok = True
        if not sites == self.sites:
            logger.error('List of sites from resources differs from infile' + \
                '\n resource %s \n infile %s', self.sites, sites)
            ok = False
        if not clusters == self.clusters:
            logger.error('List of clusters from resources differs from infile' + \
                '\n resource %s \n infile %s', self.clusters, clusters)
            ok = False
        if strict:
            if not hosts == self.hosts:
                logger.error('List of hosts from resources differs from infile' + \
                    '\n resource %s \n infile %s', self.hosts, hosts)
                ok = False
        else:
            res_hosts = {}
            for host in self.hosts:
                cluster = get_host_cluster(host)
                if cluster in res_hosts:
                    res_hosts[cluster] += 1
                else:
                    res_hosts[cluster] = 1
            xml_hosts = {}
            for host in hosts:
                cluster = get_host_cluster(host)
                if cluster in xml_hosts:
                    xml_hosts[cluster] += 1
                else:
                    xml_hosts[cluster] = 1
            if not res_hosts == xml_hosts:
                logger.error('List of hosts from resources differs from infile' + \
                    '\n resource %s \n infile %s', self.hosts, hosts)
                ok = False
            else:
                for i in range(len(hosts)):
                    el_host = xml.find(".//host/[@id='" + hosts[i] + "']")
                    el_host.attrib['id'] = self.hosts[i]

        return ok

    def _get_xml_elements(self, xml):
        """ """

        sites = sorted([site.get('id') for site in xml.findall('./site')])
        clusters = sorted([cluster.get('id')
                         for cluster in xml.findall('.//cluster')])
        hosts = sorted([host.get('id') for host in xml.findall('.//host')],
                       key=lambda host: (host.split('.', 1)[0].split('-')[0],
                                    int(host.split('.', 1)[0].split('-')[1])))

        return sites, clusters, hosts

    def _get_xml_vms(self, xml):
        """Define the list of VMs from the infile """

        def _default_xml_value(key):
            return default_vm[key] if key not in vm.attrib else vm.get(key)

        vms = []
        for host in xml.findall('.//host'):
            for vm in host.findall('.//vm'):
                vms.append({'id': vm.get('id'),
                    'n_cpu': int(_default_xml_value('n_cpu')),
                    'cpuset': _default_xml_value('cpuset'),
                    'mem': int(_default_xml_value('mem')),
                    'hdd': int(_default_xml_value('hdd')),
                    'backing_file': _default_xml_value('backing_file'),
                    'real_file': _default_xml_value('real_file'),
                    'host': host.get('id'),
                    'state': 'KO'})
        return vms

    def _set_vms_ip_mac(self):
        """Not finished """
        if isinstance(self.ip_mac, dict):
            i_vm = {site: 0 for site in self.sites}
            for vm in self.vms:
                vm_site = get_host_site(vm['host'])
                vm['ip'], vm['mac'] = self.ip_mac[vm_site][i_vm[vm_site]]
                i_vm[vm_site] += 1
        else:
            i_vm = 0
            for vm in self.vms:
                vm['ip'], vm['mac'] = self.ip_mac[i_vm]
                i_vm += 1

    def _add_xml_elements(self):
        """Add sites, clusters, hosts to self.state """
        _state = self.state
        logger.debug('Initial state \n %s', prettify(_state))
        for site in self.sites:
            SubElement(_state, 'site', attrib={'id': site})
        logger.debug('Sites added \n %s', prettify(_state))
        for cluster in self.clusters:
            el_site = _state.find("./site[@id='" + get_cluster_site(cluster) \
                                  + "']")
            SubElement(el_site, 'cluster', attrib={'id': cluster})
        logger.debug('Clusters added \n %s', prettify(_state))
        hosts_attr = get_CPU_RAM_FLOPS(self.hosts)
        for host in self.hosts:
            el_cluster = _state.find(".//cluster/[@id='" + get_host_cluster(host) + "']")
            SubElement(el_cluster, 'host', attrib={'id': host,
                                                   'state': 'Undeployed',
                                                   'cpu': str(hosts_attr[host]['CPU'] * 100),
                                                   'mem': str(hosts_attr[host]['RAM'])})
        logger.debug('Hosts added \n %s', prettify(_state))

    def _add_xml_vms(self):
        """Add vms distributed on hosts to self.state """
        for vm in self.vms:
            host = self.state.find(".//host/[@id='" + vm['host'] + "']")
            SubElement(host, 'vm', attrib={'id': vm['id'],
                                           'ip': vm['ip'],
                                           'mac': vm['mac'],
                                           'mem': str(vm['mem']),
                                           'n_cpu': str(vm['n_cpu']),
                                           'cpuset': vm['cpuset'],
                                           'hdd': str(vm['hdd']),
                                           'backing_file': vm['backing_file'],
                                           'real_file': str(vm['real_file']),
                                           'state': vm['state']})

    def _print_state_compact(self):
        """Display in a compact form the distribution of vms on hosts."""
        dist = {}
        max_len_host = 0
        for host in self.hosts:
            if len(host.split('.')[0]) > max_len_host:
                max_len_host = len(host.split('.')[0])

        for vm in self.vms:
            host = vm['host'].split('.')[0]
            if len(host) > max_len_host:
                max_len_host = len(host)
            if host not in dist.keys():
                dist[host] = {vm['id']: vm['state']}
            else:
                dist[host][vm['id']] = vm['state']
        log = ''
        for host in sorted(self.hosts, key=lambda x: (x.split('.')[0].split('-')[0],
                                                      int(x.split('.')[0].split('-')[1]))):
            host = host.split('.')[0]
            if host not in dist:
                dist[host] = {}

            log += '\n' + style.host(host) + ' '.ljust(max_len_host + 2 - len(host)) + \
                   str(len(dist[host].keys())) + ' '
            try:
                vms = sorted(dist[host].keys(), key=lambda x: (x.split('.')[0].split('-')[0],
                                                               int(x.split('.')[0].split('-')[1])))
            except:
                vms = sorted(dist[host].keys())
                pass
            for vm in vms:
                if dist[host][vm] == 'OK':
                    log += style.OK(vm)
                elif dist[host][vm] == 'KO':
                    log += style.KO(vm)
                else:
                    log += style.Unknown(vm)
                log += ' '
        return log

    def _update_vms_xml(self):
        for vm in self.vms:
            self.state.find(".//vm/[@id='" + vm['id'] + "']").set('state',
                                                                vm['state'])

    def _update_hosts_state(self, hosts_ok, hosts_ko):
        """ """
        for host in hosts_ok:
            if host:
                if isinstance(host, Host):
                    host = host.address
                self.state.find(".//host/[@id='" + host + "']").set('state',
                                                                    'OK')
        for host in hosts_ko:
            if host:
                if isinstance(host, Host):
                    host = host.address
                self.state.find(".//host/[@id='" + host + "']").set('state',
                                                                    'KO')
                self.hosts.remove(host)

        if len(self.hosts) == 0:
            logger.error('No hosts available, because %s are KO',
                         hosts_list(hosts_ko))
            exit()

        if self.vms:
            distribute_vms(self.vms, self.hosts, self.distribution)
            self._set_vms_ip_mac()

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
