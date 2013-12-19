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

from os import path, mkdir
from pprint import pformat, pprint
from xml.etree.ElementTree import fromstring
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
from vm5k import define_vms, create_disks, install_vms, start_vms, wait_vms_have_started,\
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
     
     
def get_cpu_topology(cluster):
    """ """
    logger.info('Determining the architecture of cluster '+style.emph(cluster))
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
    host = vms[0]['host'].address
    n_vm = len(vms)
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
        
        logger.info(host+': Starting VMS '+', '.join( [vm['id'] for vm in sorted(vms_to_boot)]))
        start_vms(vms_to_boot).run()
        booted = wait_vms_have_started(vms_to_boot)
        if not booted:
            return False
        booted_vms += len(vms_to_boot)
        logger.info(host+': '+style.emph(str(booted_vms)+'/'+str(n_vm)))               
    return True
#        
#        
#      
#    def get_resources(self, mode = 'sequential'):
#        """ Perform a reservation and return all the required job parameters """
#        logger.info('%s %s', style.step('Getting the resources on Grid5000 for cluster'), self.cluster)
#        
#        site = get_cluster_site(self.cluster)
#        if self.options.oarjob_id is None:
#            
#            print 'coucou'
#            if self.options.parallel:
#                n_nodes = 0
#                logger.debug('Compiling planning')
#                planning = get_planning([self.cluster], int(time()+timedelta_to_seconds(timedelta(minutes = 1))),
#                                    int(time()+timedelta_to_seconds(timedelta(days = 3, minutes = 1))) ) 
#                slots = compute_slots(planning, self.options.walltime)
#                logger.debug(slots)
#                
#                resa = format_oar_date(slots[0][0])
##                i_slot = 0
##                while n_nodes < self.options.n_nodes:
##                    logger.debug(slots[i_slot])
###                    n_nodes = planning.slots[i_slot][2][self.cluster]
##                    resa = format_oar_date(slots[i_slot][0])
##                    i_slot += 1
#                
#            else:
#                n_nodes = self.options.n_nodes
#            
#            n_nodes = 2
#            submission = OarSubmission(resources = "slash_22=1+{'cluster=\"%s\"'}/nodes=%i" % (self.cluster, n_nodes),
#                                                 walltime = self.options.walltime,
#                                                 name = self.run_name,
#                                                 reservation_date = resa,
#                                                 job_type = "deploy")
#            print 'coucou'
#            logger.debug('%s', submission)
#            
#            
#            ((job_id, _), ) = oarsub([(submission, site)])
#        else:
#            job_id = self.options.oarjob_id
#        logger.info('Waiting for the job start')    
#        wait_oar_job_start( job_id, site )
#        logger.info('Job %s has started!', style.emph(job_id))
#        self.job_info = {'job_id': job_id, 'site': site}
#        self.job_info.update(get_oar_job_info( job_id, site ))
#        logger.debug('%s', pprint(self.job_info))
#        logger.info( style.step('Done\n') )
#        
#        logger.info('%s', style.report_error('Getting hosts and VLAN parameters '))
#        self.hosts = get_oar_job_nodes( job_id, site )
#        logger.info('%s %s', style.parameter('Hosts:'),
#                        ' '.join( [host.address for host in self.hosts] ))
#        self.ip_mac = get_oar_job_subnets( job_id, site )[0]         
#        logger.info('%s %s %s ', style.parameter('Network:'), self.ip_mac[0][0], self.ip_mac[-1][0])
#        logger.info( style.step('Done\n') )
#        
#    
#    def setup_cluster(self):
#        logger.info('%s', style.step('Installing and configuring hosts '))
#        
#        if self.options.env_file is None:
#            virsh_setup = Virsh_Deployment( self.hosts, env_name = self.options.env_name, 
#                                oarjob_id = self.job_info['job_id'] )
#        else:
#            virsh_setup = Virsh_Deployment( self.hosts, env_file = self.options.env_file, 
#                                oarjob_id = self.job_info['job_id'] )
#        
#        logger.info('Deploying hosts')   
#        virsh_setup.deploy_hosts()
#        logger.info('Copying ssh keys on hosts for taktuk connection')
#        ssh_key = '~/.ssh/id_rsa'    
#        copy_ssh_keys = Put( virsh_setup.hosts, [ssh_key, ssh_key+'.pub'], remote_location='.ssh/', 
#              connection_params = {'user': 'root'}).run()
#        TaktukRemote(' echo "Host *" >> /root/.ssh/config ; echo " StrictHostKeyChecking no" >> /root/.ssh/config; ',
#                virsh_setup.hosts, connection_params = {'user': 'root'}).run()
#        logger.info('Configuring APT')
#        virsh_setup.configure_apt()
#        logger.info('Upgrading hosts')
#        virsh_setup.upgrade_hosts()
#        logger.info('Installing packages')
#        virsh_setup.install_packages()
##        logger.info('Creating bridge')
##        virsh_setup.create_bridge('br0')
##        
##        logger.info('Rebooting nodes')
##        virsh_setup.reboot_nodes()
#        logger.info('Configuring libvirt')
#        virsh_setup.configure_libvirt()
##        logger.info('Configuring munin')
##        virsh_setup.setup_munin()
#        logger.info('Creating backing file')
#        virsh_setup.create_disk_image( disk_image = '/grid5000/images/KVM/squeeze-x64-base.qcow2', clean = True)
#        logger.info('Copying id_rsa keys on vm-base.img')
#        virsh_setup.ssh_keys_on_vmbase()
#        logger.info('Hosts %s have been setup!', ', '.join([host.address for host in self.hosts]) )
#        
#        if len(virsh_setup.hosts) >= self.options.n_nodes:
#            self.setup = virsh_setup
#            return True
#        else:
#            return False
#    
#    def set_cpufreq(self, mode = 'performance'):
#        """ Installing cpu_freq_utils and configuring CPU with given mode """
#        install = Remote('source /etc/profile; apt-get install -y cpufrequtils', self.hosts).run()
#        if not install.ok():
#            logger.debug('Impossible to install cpufrequtils')
#            return False
#        setmode = []
#        nproc_act = Remote('nproc', self.hosts).run()
#        for p in nproc_act.processes():
#            nproc = p.stdout().strip()
#            cmd = ''
#            for i_proc in range(int(nproc)):
#                cmd += 'cpufreq-set -c '+str(i_proc)+' -g '+mode +'; '
#            setmode.append(Remote(cmd, [p.host()]))
#        setmode_act = ParallelActions(setmode).run()
#        
#        if not setmode_act.ok():
#            logger.debug('Impossible to change cpufreq mode')            
#            return False
#        else:
#            logger.debug('cpufreq mode set to %s', mode)
#            return True
#    
#    def get_results(self, comb):
#        logger.info('%s \n', style.step(' Getting results from nodes and frontend '))
#
#    
#        comb_dir = self.result_dir +'/'+ slugify(comb)+'/'
#        
#        try:
#            mkdir(comb_dir)
#        except:
#            logger.warning('%s already exists', comb_dir)
#            pass
#        cluster = comb['cluster']
#        site = get_cluster_site(cluster)
#        get_ping_files = []
#        
#        for vm_params in self.vms_params:
#            get_ping_file = Get([site+'.grid5000.fr'], self.ping_dir+'/ping_'+cluster+'_'+vm_params['vm_id']+'.out', 
#                local_location = comb_dir, connection_params = default_frontend_connection_params)            
#            get_ping_files.append( get_ping_file) 
#        rm_ping_dir = Remote('rm -rf '+self.ping_dir, [site+'.grid5000.fr'], 
#                        connection_params = default_frontend_connection_params)
#        SequentialActions( [ParallelActions(get_ping_files), rm_ping_dir] ).run()
#        
#        get_mig_file = Get(self.hosts, '*.out', local_location = comb_dir)
#        rm_mig_file = Remote('rm *.out', self.hosts)
#        logger.info('Saving files into %s', comb_dir)
#        get = SequentialActions([get_mig_file, rm_mig_file]).run()
#        
#        
#        return get.ok()
#    
#    def ping_probes( self, vms_params, cluster, jobid = None):
#        """A function that create a parallel actions to be executed on the site frontend of the cluster
#        that ping the vms and write a log file"""
#        site = get_cluster_site(cluster)
#        self.ping_dir = self.result_dir.split('/')[-1]
#        
#        if not self.ping_dir_created:
#            Remote('mkdir '+self.ping_dir, [site+'.grid5000.fr'], 
#               connection_params={'user': default_frontend_connection_params['user']}).run()
#            self.ping_dir_created = True
#        
#        pingactions=[]
#        for vm_params in vms_params:
#            cmd='ping -i 0.2 '+vm_params['ip']+ \
#            ' | while read pong; do pong=`echo $pong | cut -f4 -d "=" | cut -f1 -d \' \' `;'+\
#            'if [ -z "$pong" ]; then pong=0.0; fi;'+\
#            'echo "$(date +%s) $pong"; done > '+self.ping_dir+'/ping_'+cluster+'_'+vm_params['vm_id']+'.out'
#            pingactions.append(Remote(cmd, [site+'.grid5000.fr'], log_exit_code=False, 
#                                    connection_params={'user': default_frontend_connection_params['user']}))
#        logger.debug('%s', pformat(pingactions))    
#        return ParallelActions(pingactions)
#    
#    def kill_ping(self, site):
#        get_id = Remote('id | cut -d " " -f 1 | cut -d "=" -f 2 | cut -d "(" -f 1', 
#                        [g5k_configuration['default_frontend']+'.grid5000.fr'], connection_params = default_frontend_connection_params ).run()
#
#        for p in get_id.processes():
#            id = p.stdout().strip()
#        kill_ping = Remote( 'list_proc=`ps aux |grep ping|grep '+str(id)+'|grep -v grep| cut -d " " -f 5` ; echo $list_proc ; for proc in $list_proc; do kill $proc; done', 
#                   [site+'.grid5000.fr'], connection_params = default_frontend_connection_params ).run()
#        
#    def stress_hosts(self, hosts, params = {'cpu': 0, 'ram': 0, 'hdd': 0}):
#        cmd = ' apt-get install stress -y ; stress '
#        for param, n in params.iteritems():
#            if n != 0:
#                if param == 'cpu':
#                    cmd += ' --cpu '
#                if param == 'ram':
#                    cmd += ' --vm '
#                if param == 'hdd':
#                    cmd += ' --hdd '
#                cmd += str(n)
#        logger.info('Ready to execute stress on hosts % s\n%s', ' '.join( [self.host_string(host) for host in self.hosts]), cmd )
#        return Remote(cmd, hosts)
#    

#    
#
#class vm5k_sequential_engine( vm5k_engine ):
#
#    def run(self):
#        self.force_options()
#        logger.debug('%s', pformat(self.options) )
#        self.cluster = self.args[0]
#        logger.debug('%s', pformat(self.cluster) )
#        self.create_paramsweeper()
#        
#        while len(self.sweeper.get_remaining()) > 0:
#            logger.info('Performing experiments on cluster %s', style.step(self.cluster))
#            logger.info('%s', pformat( self.sweeper.stats()['done_ratio'] ))
#        
#            try: 
#                self.get_resources()
#                if not self.setup_cluster():
#                    break
#                
#                print 'coucou'
#                while True:
#                    print 'ocuocu'
#                    
#                    combs = []
#                    if not self.options.parallel:
#                        combs.append(self.sweeper.get_next() ) 
#                    else:
#                        for i in range( min(len(self.hosts), len(self.sweeper.get_remaining())) ) :
#                            combs.append( self.sweeper.get_next() )
#                            
#                    state = self.workflow( combs )
#                    print 'coucou'
#                    
#                    if state:
#                        for comb in combs:
#                            self.sweeper.done( comb )
#                        return True
#                    else:
#                        self.sweeper.cancel( combs )
#                        return False
#                    
#                    if (int(self.job_info['start_date'])+self.job_info['walltime']) < int(time()):                        
#                        logger.info('G5K reservation has been terminated, doing a new deployment')
#                        break
#                    
#            finally:
#                if self.job_info['job_id'] is not None:
#                    if not self.options.keep_alive:
#                        logger.info('Deleting job')
#                        oardel( [(self.job_info['job_id'], self.job_info['site'])] )
#                    else:
#                        logger.info('Keeping job alive for debugging')
#
#        logger.info( style.step('\n\nvm5k-engine COMPLETED ') )     
#
#
#
#
#
#
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
