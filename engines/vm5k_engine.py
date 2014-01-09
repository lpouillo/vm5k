#!/usr/bin/env python
#-*- coding: utf-8 -*-
# This is an execo engine that can be used as a basis to perform Virtual Machine migration 
# measurements using libvirt on Grid5000.
#
# After the definition of the conditions and parameters to be explored, the base worfklow 
# consists in:
# - getting some nodes on a Grid5000 cluster
# - deploy an environment with libvirt configured and virtual machine disks prepared 
# - perform some migration measurements (sequential, parallel, crossed)
# - get the results from nodes and the ping log of VM
# - draw some graphs
#
# It requires execo 2.2 
#
# Laurent Pouilloux, INRIA 2012-2013

from os import path, mkdir, remove, listdir
from pprint import pformat, pprint
from xml.etree.ElementTree import fromstring, parse, ElementTree
from time import time
from datetime import timedelta
from execo import configuration, Host, SshProcess, sleep, Remote, TaktukRemote, Get, Put, ChainPut, ParallelActions
from execo.time_utils import timedelta_to_seconds
from execo.config import SSH, SCP, TAKTUK, CHAINPUT
from execo.log import style
from execo.action import ActionFactory
from execo_g5k import default_frontend_connection_params, get_oar_job_info, get_cluster_site, OarSubmission, \
    oarsub, get_oar_job_nodes, wait_oar_job_start, oardel, get_host_attributes
from execo_g5k.planning import get_planning, compute_slots, get_jobs_specs
from vm5k import config, define_vms, create_disks, install_vms, start_vms, wait_vms_have_started,\
 destroy_vms, rm_qcow2_disks, vm5k_deployment, get_oar_job_vm5k_resources
from execo_engine import Engine, ParamSweeper, sweep, slugify, logger
from threading import Thread, Lock


class vm5k_engine( Engine ):
    """ The main engine class, that need to be run with 
    execo-run vm5k_engine -ML cluster1,cluster2"""
    
    def __init__(self):
        """ Add options for the number of measures, number of nodes
        walltime, env_file or env_name and clusters and initialize the engine """
        super(vm5k_engine, self).__init__() 
        self.options_parser.set_usage("usage: %prog <cluster>")
        self.options_parser.set_description("Execo Engine that perform live migration of virtual machines with libvirt")
        self.options_parser.add_option("-n", dest = "n_nodes", 
                    help = "number of nodes required for a combination", type = "int", default = 1)
        self.options_parser.add_option("-m", dest = "n_measure", 
                    help = "number of measures", type = "int", default = 10 ) 
        self.options_parser.add_option("-e", dest = "env_name", 
                    help = "name of the environment to be deployed", type = "string", 
                    default = "wheezy-x64-base")
        self.options_parser.add_option("-f", dest = "env_file", 
                    help = "path to the environment file", type = "string", default = None)
        self.options_parser.add_option("-w", dest = "walltime", type = "string", default = "3:00:00", 
                    help = "walltime for the reservation")
        self.options_parser.add_option("-j", dest = "oar_job_id", type = int,
                    help = "oar_job_id to relaunch an engine")
        self.options_parser.add_option("-k", dest = "keep_alive", 
                    help = "keep reservation alive ..", action = "store_true")
        self.options_parser.add_option("-o", dest = "outofchart", 
                    help = "", action = "store_true")
        self.options_parser.add_argument("cluster", "The cluster on which to run the experiment")
        
        self.oar_job_id = None
        self.frontend = None
        self.parameters = None
        
        
    def run(self):
        """The main experimental workflow, as described in ``Using the Execo toolkit to perform ... ``"""
        print_step('Defining parameters')
        # The argument is a cluster
        self.cluster = self.args[0]
        self.frontend = get_cluster_site(self.cluster)
        # Analyzing options
        if self.options.oar_job_id is not None:            
            self.oar_job_id = self.options.oar_job_id
        
        try:
            # Creation of the main iterator which is used for the first control loop.
            # You need have a method called define_parameters, that returns a list of parameter dicts
            self.create_paramsweeper()
            
            # While there combination to treat
            while len(self.sweeper.get_remaining()) > 0:
                # If no job, we make a reservation and prepare the hosts for the experiments 
                if self.oar_job_id is None:
                    self.make_reservation()
                # Retrieving the hosts and subnets parameters
                self.get_resources()
                # Hosts deployment and configuration
                self.setup_hosts()
                  
                # Initializing the resources and threads
                available_hosts = list(self.hosts)
                available_ip_mac = list(self.ip_mac)
                threads = {}
                
                # Checking that the job is running and not in Error
                while get_oar_job_info(self.oar_job_id, self.frontend)['state'] != 'Error':
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
                    if not comb: break
                    
                    used_hosts = available_hosts[0:self.options.n_nodes]
                    available_hosts = available_hosts[self.options.n_nodes:]
                    
                    n_vm = self.comb_nvm(comb)
                    used_ip_mac = available_ip_mac[0:n_vm]
                    available_ip_mac = available_ip_mac[n_vm:]
                    
                    t = Thread(target = self.workflow, args = ( comb, used_hosts, used_ip_mac ))
                    threads[t] = {'hosts': used_hosts, 'ip_mac': used_ip_mac }                
                    t.daemon = True
                    t.start()
                
                if get_oar_job_info(self.oar_job_id, self.frontend)['state'] == 'Error':
                    job_is_dead = True
                    
                if job_is_dead: self.oar_job_id = None
                
        finally:
            
            if self.oar_job_id is not None:        
                if not self.options.keep_alive:
                    logger.info('Deleting job')
                    oardel( [(self.oar_job_id, self.frontend)] )
                else:
                    logger.info('Keeping job alive for debugging')
        
    def force_options(self):
        """Allow to override default options in derived engine"""
        for option in self.options.__dict__.keys():
            if self.__dict__.has_key(option):
                self.options.__dict__[option] = self.__dict__[option]
                
    def create_paramsweeper(self):
        """Generate an iterator over combination parameters"""
        if self.parameters is None:
            parameters = self.define_parameters()
        logger.debug(pformat(parameters))
        sweeps = sweep( parameters )
        logger.info('% s combinations', len(sweeps))
        self.sweeper = ParamSweeper( path.join(self.result_dir, "sweeps"), sweeps)
        
    def make_reservation(self): 
        """Perform """
        logger.info('Performing reservation')
        planning = get_planning(elements = [self.cluster], 
                    starttime = int(time()+timedelta_to_seconds(timedelta(minutes = 1))),
                    endtime = int(time()+timedelta_to_seconds(timedelta(days = 3, minutes = 1))),
                    out_of_chart =  self.options.outofchart) 
        slots = compute_slots(planning, self.options.walltime)
        startdate = slots[0][0]
        i_slot = 0
        n_nodes = slots[i_slot][2][self.cluster]
        while n_nodes < self.options.n_nodes:
            logger.debug(slots[i_slot])
            startdate = slots[i_slot][0]
            n_nodes = slots[i_slot][2][self.cluster]
            i_slot += 1
            
        
        jobs_specs = get_jobs_specs({self.cluster: n_nodes}, name = 'vm5k_engine')
        sub = jobs_specs[0][0]
        tmp = str(sub.resources).replace('\\', '')
        sub.resources = 'slash_22=2+'+tmp.replace('"', '')
        sub.walltime = self.options.walltime
        sub.additional_options = '-t deploy'
        sub.reservation_date = startdate
        (self.oar_job_id, self.frontend) = oarsub(jobs_specs)[0]
        
        
    def get_resources(self):
        """ """
        self.resources = get_oar_job_vm5k_resources(self.oar_job_id, self.frontend)
        self.hosts = self.resources[get_cluster_site(self.cluster)]['hosts']
        self.ip_mac = self.resources[get_cluster_site(self.cluster)]['ip_mac']
        
    def setup_hosts(self):
        """ """
        logger.info('Initialize vm5k_deployment')
        setup = vm5k_deployment(resources = self.resources)
        setup.fact = ActionFactory  (remote_tool = TAKTUK,
                                fileput_tool = CHAINPUT,
                                fileget_tool = SCP)
        logger.info('Deploy hosts')
        setup.hosts_deployment()
        logger.info('Install packages')
        setup.packages_management()
        logger.info('Configure libvirt')
        setup.configure_libvirt()
        logger.info('Create backing file')
        setup._create_backing_file('/grid5000/images/KVM/squeeze-x64-base.qcow2')
         

def print_step(step_desc = None):
    """ """
    logger.info(style.step(' '+step_desc+' '))
     
     
def get_cpu_topology(cluster, dir = None):
    """ """
    logger.info('Determining the architecture of cluster '+style.emph(cluster))
    
    root = None
    # Trying to reed topology from a directory
    if dir is not None:
        fname = dir+'/topo_'+cluster+'.xml'
        try:
            tree = parse(fname)
            root = tree.getroot()
        except:
            logger.info('No cache file found, will reserve a node')
            pass
        
    if root is None:
        frontend = get_cluster_site(cluster)            
        submission = OarSubmission(resources = "{cluster='"+cluster+"'}/nodes=1",
                                                         walltime = "0:02:00",
                                                         job_type = "allow_classic_ssh")
        ((job_id, _), ) = oarsub([(submission, frontend)])
        wait_oar_job_start( job_id, frontend )        
        host = get_oar_job_nodes( job_id, frontend )[0]
        capa = SshProcess('unset LIBVIRT_DEFAULT_URI ; virsh capabilities', host, 
                          connection_params = {'user': default_frontend_connection_params['user'] }).run()
        oardel( [ (job_id, frontend) ] )
        root = fromstring( capa.stdout )
        if dir is not None:
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
    
    host = vms[0]['host'].address.split('.')[0]
    
    sub_vms = {}
    for i_core in list(set( vm['cpuset'] for vm in vms )):
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
        
        logger.info(style.Thread(host)+': Starting VMS '+', '.join( [vm['id'] for vm in sorted(vms_to_boot)]))
        start_vms(vms_to_boot).run()
        booted = wait_vms_have_started(vms_to_boot)
        if not booted:
            return False
        booted_vms += len(vms_to_boot)
        logger.info(style.Thread(host)+': '+style.emph(str(booted_vms)+'/'+str(n_vm)))               
    return True


#
#
## Migration functions
#def split_vm( vms_params, n = 2 ):
#    split_vms = [0] * n
#    for i_params in range(n):
#        split_vms[i_params] = vms_params[i_params::n]
#    return split_vms
#
#def host_shortname( host):
#    ''' Return the short name of a G5K host, with a color_style '''
#    return host.address.split('.')[0]
#
#def migration_measure( vm, host_src, host_dest, i_mes = 0, label = 'MIG', mig_speed = default_mig_speed):
#    ''' Return an Remote action to measure migration time of vm_id from
#    host_src to host_dest '''
#    cmd = "virsh --connect qemu:///system migrate-setspeed "+vm['vm_id']+" "+str(mig_speed)+"; timestamp=`date +%s`; "+ \
#            "duration=`/usr/bin/time  -f \""+str(i_mes)+"\t%e\" sh -c '"+ \
#            "virsh --connect qemu:///system migrate "+vm['vm_id']+" --live --copy-storage-inc "+\
#            "qemu+ssh://"+host_dest.address+"/system'  2>&1 `;"+ \
#            "echo $timestamp "+vm['vm_id']+" $duration >> "+\
#            label+"_"+host_shortname(host_src)+"_"+host_shortname(host_dest)+".out"
#    logger.info(style.host(vm['vm_id'], 'object_repr')+': '+host_shortname(host_src)+" -> "+host_shortname(host_dest))
#    logger.debug('%s %s %s', cmd, host_src, host_dest)
#    return Remote(cmd, [ host_src ])
#
#def measurements_loop(n_measure, vms, hosts, mig_function, mode, label = None, mig_speed = default_mig_speed, cache = False):
#    ''' Perform a loop of migration given by the mig_function'''
#    if not cache:
#        clear_cache = Remote('sync; echo 3 > /proc/sys/vm/drop_caches', hosts)
#
#    n_nodes = len(hosts)
#    permut = deque(''.join([`num` for num in range(n_nodes)]))
#    for i_mes in range( n_measure ):
#        if not cache:
#            clear_cache.run()
#            clear_cache.reset()
#
#        logger.info( style.user3('Measure '+str(i_mes+1)+'/'+str(n_measure)))
#        ii = [int(permut[i]) for i in range(n_nodes)]
#
#        nodes = [ hosts[ii[i]] for i in range(n_nodes)]
#
#        migractions = mig_function( vms, nodes, i_mes = i_mes,
#                    mode = mode, label = label, mig_speed = mig_speed)
#
#        migractions.run()
#        if not migractions.ok():
#            return False
#
#        if not cache:
#            clear_cache.run()
#            clear_cache.reset()
#
#        if mig_function != split_merge_migrations:
#            permut.rotate(+1)
#
#    return True
#
#def twonodes_migrations( vms, hosts, mode = 'sequential', i_mes = 0, label = 'SEQ', mig_speed = default_mig_speed):
#    ''' Return SequentialActions to perform sequential measurements '''
#    migractions = []
#    for vm in vms:
#        migractions.append(migration_measure( vm, hosts[0], hosts[1], i_mes, label, mig_speed = mig_speed))
#    if mode == 'sequential':
#        return SequentialActions(migractions)
#    else:
#        return ParallelActions(migractions)
#
#def crossed_migrations( vms, hosts, mode = 'parallel', i_mes = 0, label = 'CROSSED', mig_speed = default_mig_speed):
#    ''' Return ParallelActions to perform parallel measurements '''
#    vms = split_vm(vms)
#    migractions_01 = []; migractions_10 = []
#    for vm in vms[0]:
#        migractions_01.append(migration_measure( vm, hosts[0], hosts[1], i_mes, label, mig_speed = mig_speed))
#    for vm in vms[1]:
#        migractions_10.append(migration_measure( vm, hosts[1], hosts[0], i_mes, label, mig_speed = mig_speed))
#    if mode == 'sequential':
#        return ParallelActions( [ SequentialActions( migractions_01 ), SequentialActions( migractions_10 ) ] )
#    else:
#        return ParallelActions( migractions_01 + migractions_10 )
#
#def circular_migrations( vms, hosts, mode = 'sequential', i_mes = 0, label = 'CIRC', mig_speed = default_mig_speed):
#    n_nodes = len(hosts)
#    if n_nodes < 3:
#        print 'Error, number of hosts must be >= 3'
#    elif len(vms) % (n_nodes) !=0:
#        print 'Error, number of VMs not divisible by number of hosts'
#    else:
#        vms = split_vm(vms, n_nodes )
#        migractions = []
#        for i_from in range(n_nodes):
#            i_to = i_from+1 if i_from < n_nodes-1 else 0
#            if mode == 'sequential':
#                label = 'CIRCSEQ'
#            elif mode == 'parallel':
#                label = 'CIRCPARA'
#            migractions.append(twonodes_migrations(vms[i_to], hosts[i_from], hosts[i_to], mode = mode, i_mes = 0, label = label ))
#        return ParallelActions(migractions)
#
#def split_merge_migrations( vms, hosts, mode = 'parallel', i_mes = 0, label = 'SPLITMERGE', mig_speed = default_mig_speed):
#    ''' Return ParallelActions to perform split migration '''
#    if len(hosts) < 3:
#        print 'Error, number of hosts must be >= 3'
#    elif len(vms) % (len(hosts)) !=0:
#        print 'Error, number of VMs not divisible by number of hosts'
#    else:
#        vms = split_vm(vms, len(hosts)-1 )
#        migsplit = []
#        migmerge = []
#        for idx in range(len(hosts)-1):
#            for vm in vms[idx]:
#                migsplit.append(migration_measure( vm, hosts[0], hosts[idx+1], i_mes, label, mig_speed = mig_speed))
#                migmerge.append(migration_measure( vm, hosts[idx+1], hosts[0], i_mes, label, mig_speed = mig_speed))
#
#        if mode == 'sequential':
#            return SequentialActions( [SequentialActions(migsplit), SequentialActions(migmerge)])
#        else:
#            return SequentialActions( [ParallelActions(migsplit), ParallelActions(migmerge)])
