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

from os import path, mkdir, listdir, remove
from pprint import pformat
from xml.etree.ElementTree import fromstring, parse, ElementTree
import time
import datetime
from execo import Host, SshProcess, sleep, Remote, TaktukRemote, Get, Put, ChainPut, \
    SequentialActions, ParallelActions, format_date, format_duration, \
    default_connection_params
from execo.time_utils import timedelta_to_seconds
from execo.config import SSH, SCP, TAKTUK, CHAINPUT
from execo.log import style
from execo.action import ActionFactory
from execo_g5k import default_frontend_connection_params, get_oar_job_info, \
    get_cluster_site, OarSubmission, \
    oarsub, get_oar_job_nodes, wait_oar_job_start, oardel, get_host_attributes
from execo_g5k.planning import get_planning, compute_slots, get_jobs_specs
from vm5k import config, define_vms, create_disks, install_vms, start_vms, wait_vms_have_started,\
    destroy_vms, rm_qcow2_disks, vm5k_deployment, get_oar_job_vm5k_resources, print_step
from vm5k.config import default_vm
from execo_engine import Engine, ParamSweeper, sweep, slugify, logger
from threading import Thread, Lock


default_connection_params['user'] = 'root'


class vm5k_engine(Engine):
    """ The base vm5k engine class, that is build from execo_engine.Engine
    and can be used to perform virtual machines experiments."""
    def __init__(self):
        """ Add options for the number of measures, number of nodes
        walltime, env_file or env_name and clusters and initialize the engine 
        """
        super(vm5k_engine, self).__init__()
        self.options_parser.set_usage("usage: %prog <cluster>")
        self.options_parser.set_description("Execo Engine that can be used to" + \
                "perform automatic virtual machines experiments")
        self.options_parser.add_option("-n", dest="n_nodes",
                    help="number of nodes required for a combination",
                    type="int",
                    default=1)
        self.options_parser.add_option("-m", dest="n_measure",
                    help="number of measures",
                    type="int",
                    default=10)
        self.options_parser.add_option("-e", dest="env_name",
                    help="name of the environment to be deployed",
                    type="string",
                    default="wheezy-x64-base")
        self.options_parser.add_option("-f", dest="env_file",
                    help="path to the environment file",
                    type="string",
                    default=None)
        self.options_parser.add_option("-b", dest="backing_files",
                    help="path to the vm backing files separated by ,",
                    type="string",
                    default=default_vm['backing_file'])
        self.options_parser.add_option("-w", dest="walltime",
                    help="walltime for the reservation",
                    type="string",
                    default="3:00:00")
        self.options_parser.add_option("-k", dest="keep_alive",
                    help="keep reservation alive ..",
                    action="store_true")
        self.options_parser.add_option("-j", dest="oar_job_id",
                    help="oar_job_id to relaunch an engine",
                    type=int)
        self.options_parser.add_option("-o", dest="outofchart",
                    help="Run the engine outside days",
                    action="store_true")
        self.options_parser.add_option("--no-hosts-setup",
                                       action="store_true",
                                       help="use hosts in current state")
        self.options_parser.add_argument("cluster",
                        "The cluster on which to run the experiment")

        self.frontend = None
        self.parameters = None

    def force_options(self):
        """Allow to override default options in derived engine"""
        for option in self.options.__dict__.keys():
            if option in self.__dict__:
                self.options.__dict__[option] = self.__dict__[option]

    def create_paramsweeper(self):
        """Generate an iterator over combination parameters"""
        if self.parameters is None:
            parameters = self.define_parameters()
        logger.detail(pformat(parameters))
        sweeps = sweep(parameters)
        logger.info('% s combinations', len(sweeps))
        self.sweeper = ParamSweeper(path.join(self.result_dir, "sweeps"),
                                    sweeps)

    def _get_nodes(self, starttime, endtime):
        """ """
        planning = get_planning(elements=[self.cluster],
                                starttime=starttime,
                                endtime=endtime,
                                out_of_chart=self.options.outofchart)
        slots = compute_slots(planning, self.options.walltime)
        startdate = slots[0][0]
        i_slot = 0
        n_nodes = slots[i_slot][2][self.cluster]
        while n_nodes < self.options.n_nodes:
            logger.debug(slots[i_slot])
            startdate = slots[i_slot][0]
            n_nodes = slots[i_slot][2][self.cluster]
            i_slot += 1
            if i_slot == len(slots) - 1:
                return False, False
        return startdate, self.options.n_nodes

    def make_reservation(self):
        """Perform a reservation of the required number of nodes, with 4000 IP.
        """
        logger.info('Performing reservation')
        starttime = int(time.time() + timedelta_to_seconds(datetime.timedelta(minutes=1)))
        endtime = int(starttime + timedelta_to_seconds(datetime.timedelta(days=3,
                                                                 minutes=1)))
        startdate, n_nodes = self._get_nodes(starttime, endtime)
        while not n_nodes:
            logger.info('No enough nodes found between %s and %s, ' + \
                        'increasing time window',
                        format_date(starttime), format_date(endtime))
            starttime = endtime
            endtime = int(starttime + timedelta_to_seconds(datetime.timedelta(days=3,
                                                                minutes=1)))
            startdate, n_nodes = self._get_nodes(starttime, endtime)
            if starttime > int(time.time() + timedelta_to_seconds(
                                                datetime.timedelta(weeks=6))):
                logger.error('There are not enough nodes on %s for your ' + \
                             'experiments, abort ...', self.cluster)
                exit()
        jobs_specs = get_jobs_specs({self.cluster: n_nodes},
                                    name=self.__class__.__name__)
        sub = jobs_specs[0][0]
        tmp = str(sub.resources).replace('\\', '')
        sub.resources = 'slash_22=4+' + tmp.replace('"', '')
        sub.walltime = self.options.walltime
        sub.additional_options = '-t deploy'
        sub.reservation_date = startdate
        (self.oar_job_id, self.frontend) = oarsub(jobs_specs)[0]
        logger.info('Startdate: %s, n_nodes: %s', format_date(startdate),
                    str(n_nodes))

    def get_resources(self):
        """Retrieve the ressources for the vm5k_deployement and define
        the list of hosts and ip_mac.
        """
        self.resources = get_oar_job_vm5k_resources([(self.oar_job_id,
                                                      self.frontend)])
        self.hosts = self.resources[get_cluster_site(self.cluster)]['hosts']
        self.ip_mac = self.resources[get_cluster_site(self.cluster)]['ip_mac']

    def setup_hosts(self):
        """Launch the vm5k_deployment """
        logger.info('Initialize vm5k_deployment')
        setup = vm5k_deployment(resources=self.resources,
                    env_name=self.options.env_name,
                    env_file=self.options.env_file)
        setup.fact = ActionFactory(remote_tool=TAKTUK,
                                fileput_tool=CHAINPUT,
                                fileget_tool=SCP)
        logger.info('Deploy hosts')
        setup.hosts_deployment()
        logger.info('Install packages')
        setup.packages_management()
        logger.info('Configure libvirt')
        setup.configure_libvirt()
        logger.info('Create backing file')
        backing_files = self.options.backing_files.split(',')
        setup._create_backing_file(disks=backing_files)


class vm5k_engine_para(vm5k_engine):
    """A engine that use threads to treate combination in parallel
    """
    def __init__(self):
        super(vm5k_engine_para, self).__init__()

    def _get_nodes(self, starttime, endtime):
        """ """
        planning = get_planning(elements=[self.cluster],
                                starttime=starttime,
                                endtime=endtime,
                                out_of_chart=self.options.outofchart)
        slots = compute_slots(planning, self.options.walltime)
        startdate = slots[0][0]
        i_slot = 0
        n_nodes = self.options.n_nodes * \
                (slots[i_slot][2][self.cluster] // self.options.n_nodes)
        while n_nodes < self.options.n_nodes:
            logger.debug(slots[i_slot])
            startdate = slots[i_slot][0]
            n_nodes = self.options.n_nodes * \
                (slots[i_slot][2][self.cluster] // self.options.n_nodes)
            i_slot += 1
            if i_slot == len(slots) - 1:
                return False, False
        logger.debug('Reserving %s nodes at %s', n_nodes, format_date(startdate))
        return startdate, n_nodes

    def run(self):
        """The main experimental workflow, as described in
        ``Using the Execo toolkit to perform ...``
        """
        self.force_options()

        # The argument is a cluster
        self.cluster = self.args[0]
        self.frontend = get_cluster_site(self.cluster)
        # Analyzing options
        if self.options.oar_job_id:
            self.oar_job_id = self.options.oar_job_id
        else:
            self.oar_job_id = None

        try:
            # Creation of the main iterator which is used for the first control loop.
            # You need have a method called define_parameters, that returns a list of parameter dicts
            self.create_paramsweeper()

            job_is_dead = False
            # While they are combinations to treat
            while len(self.sweeper.get_remaining()) > 0:
                # If no job, we make a reservation and prepare the hosts for the experiments
                if self.oar_job_id is None:
                    self.make_reservation()
                # Retrieving the hosts and subnets parameters
                self.get_resources()
                # Hosts deployment and configuration
                if not self.options.no_hosts_setup:
                    self.setup_hosts()
                if len(self.hosts) == 0:
                    break

                # Initializing the resources and threads
                available_hosts = list(self.hosts)
                available_ip_mac = list(self.ip_mac)
                threads = {}

                # Checking that the job is running and not in Error
                while get_oar_job_info(self.oar_job_id, self.frontend)['state'] != 'Error' \
                    or len(threads.keys()) > 0:
                    job_is_dead = False
                    while self.options.n_nodes > len(available_hosts):
                        tmp_threads = dict(threads)
                        for t in tmp_threads:
                            if not t.is_alive():
                                available_hosts.extend(tmp_threads[t]['hosts'])
                                available_ip_mac.extend(tmp_threads[t]['ip_mac'])
                                del threads[t]
                        sleep(5)
                        if get_oar_job_info(self.oar_job_id, self.frontend)['state'] == 'Error':
                            job_is_dead = True
                            break
                    if job_is_dead:
                        break

                    # Getting the next combination
                    comb = self.sweeper.get_next()
                    if not comb:
                        while len(threads.keys()) > 0:
                            tmp_threads = dict(threads)
                            for t in tmp_threads:
                                if not t.is_alive():
                                    del threads[t]
                            logger.info('Waiting for threads to complete')
                            sleep(20)
                        break

                    used_hosts = available_hosts[0:self.options.n_nodes]
                    available_hosts = available_hosts[self.options.n_nodes:]

                    n_vm = self.comb_nvm(comb)
                    used_ip_mac = available_ip_mac[0:n_vm]
                    available_ip_mac = available_ip_mac[n_vm:]

                    t = Thread(target=self.workflow,
                               args=(comb, used_hosts, used_ip_mac))
                    threads[t] = {'hosts': used_hosts, 'ip_mac': used_ip_mac}
                    logger.debug('Threads: %s', len(threads))
                    t.daemon = True
                    t.start()

                if get_oar_job_info(self.oar_job_id, self.frontend)['state'] == 'Error':
                    job_is_dead = True

                if job_is_dead:
                    self.oar_job_id = None

        finally:
            if self.oar_job_id is not None:
                if not self.options.keep_alive:
                    logger.info('Deleting job')
                    oardel([(self.oar_job_id, self.frontend)])
                else:
                    logger.info('Keeping job alive for debugging')


def get_cpu_topology(cluster, xpdir=None):
    """ """
    logger.info('Determining the architecture of cluster ' + \
                style.emph(cluster))
    root = None
    # Trying to reed topology from a directory
    if xpdir:
        fname = xpdir + '/topo_' + cluster + '.xml'
        try:
            tree = parse(fname)
            root = tree.getroot()
        except:
            logger.info('No cache file found, will reserve a node and ' + \
                        'determine topology from virsh capabilities')
            pass

    if root is None:
        frontend = get_cluster_site(cluster)
        submission = OarSubmission(
            resources="{cluster='" + cluster + "'}/nodes=1",
            walltime="0:02:00",
            job_type="allow_classic_ssh")
        ((job_id, _), ) = oarsub([(submission, frontend)])
        wait_oar_job_start(job_id, frontend)
        host = get_oar_job_nodes(job_id, frontend)[0]
        capa = SshProcess('virsh capabilities', host,
            connection_params={'user': default_frontend_connection_params['user']}
            ).run()
        oardel([(job_id, frontend)])
        root = fromstring(capa.stdout)
        if xpdir is not None:
            tree = ElementTree(root)
            tree.write(fname)

    cpu_topology = []
    i_cell = 0
    for cell in root.findall('.//cell'):
        cpu_topology.append([])
        for cpu in cell.findall('.//cpu'):
            cpu_topology[i_cell].append(int(cpu.attrib['id']))
        i_cell += 1
    logger.info(pformat(cpu_topology))
    return cpu_topology


def boot_vms_by_core(vms):
    """ """
    n_vm = len(vms)
    if n_vm == 0:
        return True
    if isinstance(vms[0]['host'], Host):
        host = vms[0]['host'].address.split('.')[0]
    else:
        host = vms[0]['host'].split('.')[0]

    sub_vms = {}
    for i_core in list(set(vm['cpuset'] for vm in vms)):
        sub_vms[i_core] = list()
        for vm in vms:
            if vm['cpuset'] == i_core:
                sub_vms[i_core].append(vm)
    booted_vms = 0
    while len(sub_vms.keys()) > 0:
        vms_to_boot = []
        for i_core in sub_vms.keys():
            vms_to_boot.append(sub_vms[i_core][0])
            sub_vms[i_core].pop(0)
            if len(sub_vms[i_core]) == 0:
                del sub_vms[i_core]

        logger.info(style.Thread(host) + ': Starting VMS '+', '.join( [vm['id'] for vm in sorted(vms_to_boot)]))
        start_vms(vms_to_boot).run()
        booted = wait_vms_have_started(vms_to_boot)
        if not booted:
            return False
        booted_vms += len(vms_to_boot)
        logger.info(style.Thread(host)+': '+style.emph(str(booted_vms)+'/'+str(n_vm)))
    return True

