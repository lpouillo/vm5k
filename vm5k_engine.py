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
from time import time
from pprint import pformat, pprint
from math import floor
import xml.etree.ElementTree as ET
from collections import deque
from execo import configuration, Put, Get, Remote, SequentialActions, ParallelActions, Host, TaktukPut, ChainPut, SshProcess, TaktukRemote
from execo.time_utils import sleep, timedelta_to_seconds
from execo_g5k import oarsub, OarSubmission, oardel, wait_oar_job_start, get_oar_job_nodes, get_oar_job_subnets, get_oar_job_info
from execo_g5k.api_utils import get_cluster_site, get_host_attributes
from execo_g5k.vmutils import Virsh_Deployment, destroy_vms, define_vms, create_disks, create_disks_on_hosts, install_vms, start_vms, wait_vms_have_started
from execo_g5k.planning import Planning
from time import time, struct_time
from datetime import timedelta
from execo_g5k.config import default_frontend_connection_params, g5k_configuration
from execo_g5k.oar import oar_date_to_unixts, format_oar_date, oar_duration_to_seconds
from execo.log import style
from execo_engine import Engine, ParamSweeper, sweep, slugify, logger

default_mig_speed = 125  

class vm5k_engine( Engine ):
    """ The main engine class, that need to be run with 
    execo-run vm5k_engine -ML cluster1,cluster2"""
    
    def __init__(self):
        """ Add options for the number of measures, migration bandwidth, number of nodes
        walltime, env_file or env_name, stress, and clusters and initialize the engine """
        super(vm5k_engine, self).__init__() 
        self.options_parser.set_usage("usage: %prog <cluster>")
        self.options_parser.set_description("Execo Engine that perform live migration of virtual machines with libvirt")
        self.options_parser.add_option("-m", dest = "n_measure", 
                    help = "number of measures", type = "int", default = 10 )
        self.options_parser.add_option("-b", dest = "mig_bw", 
                    help = "bandwith used for the migration", type = "int", default = default_mig_speed )
        self.options_parser.add_option("-e", dest = "env_name", 
                    help = "name of the environment to be deployed", type = "string", default = "squeeze-x64-prod")
        self.options_parser.add_option("-f", dest = "env_file", 
                    help = "path to the environment file", type = "string", default = None)
        self.options_parser.add_option("-n", dest = "n_nodes", 
                    help = "number of nodes to be deployed", type = "int", default = 1)
        self.options_parser.add_option("-w", dest = "walltime", help = "walltime for the submission", type ="string", default = "6:00:00")
        self.options_parser.add_option("-j", dest = "oarjob_id", help = "oar_job_id to relaunch an engine", type = int)
        self.options_parser.add_option("-k", dest = "keep_alive", help = "keep reservation alive ..", action = "store_true")
        self.options_parser.add_option("-p", dest = "parallel", help = "", action = "store_true")
        self.options_parser.add_argument("clusters", "comma separated list of clusters")
        logger.info( style.step('Initializing Live Migration engine') )
        
        configuration['color_styles']['step'] = 'red', 'bold'
        configuration['color_styles']['parameter'] = 'magenta', 'bold'
        self.ping_dir_created = False
    


    def force_options(self):
        for option in self.options.__dict__.keys():
            if self.__dict__.has_key(option):
                self.options.__dict__[option] = self.__dict__[option]
    
    def create_paramsweeper(self):
        """ Defining the ParamSweeper for the engine """
        
        if not hasattr(self, 'define_parameters'):
            logger.error('No define_parameters method defined in your engine, aborting')
            exit()
        else:
            parameters = self.define_parameters()
        sweeps = sweep( parameters )
        self.sweeper = ParamSweeper( path.join(self.result_dir, "sweeps"), sweeps)
        log = style.step('Parameters combinations: ')+ str(len(sweeps))
        for param, values in parameters.iteritems():
            log+='\n'+style.emph(str(param))+': '+', '.join([str(value) for value in values])
        logger.info(log)
          
      
    def get_resources(self, mode = 'sequential'):
        """ Perform a reservation and return all the required job parameters """
        logger.info('%s %s', style.step('Getting the resources on Grid5000 for cluster'), self.cluster)
        
        site = get_cluster_site(self.cluster)
        if self.options.oarjob_id is None:
            if self.options.parallel:
                n_nodes = 0
                planning = Planning({self.cluster: n_nodes}, int(time()+timedelta_to_seconds(timedelta(minutes = 1))),
                                    int(time()+timedelta_to_seconds(timedelta(days = 3, minutes = 1))) ) 
                planning.compute(out_of_chart = False)
                planning.compute_slots(self.options.walltime)
                i_slot = 0
                while n_nodes < self.options.n_nodes:
                    logger.debug(planning.slots[i_slot])
                    n_nodes = planning.slots[i_slot][2][self.cluster]-1
                    i_slot += 1
                
            else:
                n_nodes = self.options.n_nodes
            
            submission = OarSubmission(resources = "slash_22=1+{'cluster=\"%s\"'}/nodes=%i" % (self.cluster, n_nodes),
                                                 walltime = self.options.walltime,
                                                 name = self.run_name,
                                                 job_type = "deploy")
            logger.debug('%s', submission)
            ((job_id, _), ) = oarsub([(submission, site)])
        else:
            job_id = self.options.oarjob_id
        logger.info('Waiting for the job start')    
        wait_oar_job_start( job_id, site )
        logger.info('Job %s has started!', style.emph(job_id))
        self.job_info = {'job_id': job_id, 'site': site}
        self.job_info.update(get_oar_job_info( job_id, site ))
#        logger.debug('%s', pprint(self.job_info))
        logger.info( style.step('Done\n') )
        
        logger.info('%s', style.report_error('Getting hosts and VLAN parameters '))
        self.hosts = get_oar_job_nodes( job_id, site )
        logger.info('%s %s', style.parameter('Hosts:'),
                        ' '.join( [host.address for host in self.hosts] ))
        self.ip_mac = get_oar_job_subnets( job_id, site )[0]         
        logger.info('%s %s %s ', style.parameter('Network:'), self.ip_mac[0][0], self.ip_mac[-1][0])
        logger.info( style.step('Done\n') )
        
    
    def setup_cluster(self):
        logger.info('%s', style.step('Installing and configuring hosts '))
        
        if self.options.env_file is None:
            virsh_setup = Virsh_Deployment( self.hosts, env_name = self.options.env_name, 
                                oarjob_id = self.job_info['job_id'] )
        else:
            virsh_setup = Virsh_Deployment( self.hosts, env_file = self.options.env_file, 
                                oarjob_id = self.job_info['job_id'] )
        
        logger.info('Deploying hosts')   
        virsh_setup.deploy_hosts()
        logger.info('Copying ssh keys on hosts for taktuk connection')
        ssh_key = '~/.ssh/id_rsa'    
        copy_ssh_keys = Put( virsh_setup.hosts, [ssh_key, ssh_key+'.pub'], remote_location='.ssh/', 
              connection_params = {'user': 'root'}).run()
        TaktukRemote(' echo "Host *" >> /root/.ssh/config ; echo " StrictHostKeyChecking no" >> /root/.ssh/config; ',
                virsh_setup.hosts, connection_params = {'user': 'root'}).run()
        logger.info('Configuring APT')
        virsh_setup.configure_apt()
        logger.info('Upgrading hosts')
        virsh_setup.upgrade_hosts()
        logger.info('Installing packages')
        virsh_setup.install_packages()
        logger.info('Configuring libvirt')
        virsh_setup.configure_libvirt()
        logger.info('Configuring munin')
        virsh_setup.setup_munin()
        logger.info('Creating backing file')
        virsh_setup.create_disk_image(clean = True)
        virsh_setup.ssh_keys_on_vmbase()
        logger.info('Hosts %s have been setup!', ', '.join([host.address for host in self.hosts]) )
        
        if len(virsh_setup.hosts) == self.options.n_nodes:
            self.setup = virsh_setup
            return True
        else:
            return False
    
    def set_cpufreq(self, mode = 'performance'):
        """ Installing cpu_freq_utils and configuring CPU with given mode """
        install = Remote('source /etc/profile; apt-get install -y cpufrequtils', self.hosts).run()
        if not install.ok():
            logger.debug('Impossible to install cpufrequtils')
            return False
        setmode = []
        nproc_act = Remote('nproc', self.hosts).run()
        for p in nproc_act.processes():
            nproc = p.stdout().strip()
            cmd = ''
            for i_proc in range(int(nproc)):
                cmd += 'cpufreq-set -c '+str(i_proc)+' -g '+mode +'; '
            setmode.append(Remote(cmd, [p.host()]))
        setmode_act = ParallelActions(setmode).run()
        
        if not setmode_act.ok():
            logger.debug('Impossible to change cpufreq mode')            
            return False
        else:
            logger.debug('cpufreq mode set to %s', mode)
            return True
    
    def get_results(self, comb):
        logger.info('%s \n', style.step(' Getting results from nodes and frontend '))

    
        comb_dir = self.result_dir +'/'+ slugify(comb)+'/'
        
        try:
            mkdir(comb_dir)
        except:
            logger.warning('%s already exists', comb_dir)
            pass
        cluster = comb['cluster']
        site = get_cluster_site(cluster)
        get_ping_files = []
        
        for vm_params in self.vms_params:
            get_ping_file = Get([site+'.grid5000.fr'], self.ping_dir+'/ping_'+cluster+'_'+vm_params['vm_id']+'.out', 
                local_location = comb_dir, connection_params = default_frontend_connection_params)            
            get_ping_files.append( get_ping_file) 
        rm_ping_dir = Remote('rm -rf '+self.ping_dir, [site+'.grid5000.fr'], 
                        connection_params = default_frontend_connection_params)
        SequentialActions( [ParallelActions(get_ping_files), rm_ping_dir] ).run()
        
        get_mig_file = Get(self.hosts, '*.out', local_location = comb_dir)
        rm_mig_file = Remote('rm *.out', self.hosts)
        logger.info('Saving files into %s', comb_dir)
        get = SequentialActions([get_mig_file, rm_mig_file]).run()
        
        
        return get.ok()
    
    def ping_probes( self, vms_params, cluster, jobid = None):
        """A function that create a parallel actions to be executed on the site frontend of the cluster
        that ping the vms and write a log file"""
        site = get_cluster_site(cluster)
        self.ping_dir = self.result_dir.split('/')[-1]
        
        if not self.ping_dir_created:
            Remote('mkdir '+self.ping_dir, [site+'.grid5000.fr'], 
               connection_params={'user': default_frontend_connection_params['user']}).run()
            self.ping_dir_created = True
        
        pingactions=[]
        for vm_params in vms_params:
            cmd='ping -i 0.2 '+vm_params['ip']+ \
            ' | while read pong; do pong=`echo $pong | cut -f4 -d "=" | cut -f1 -d \' \' `;'+\
            'if [ -z "$pong" ]; then pong=0.0; fi;'+\
            'echo "$(date +%s) $pong"; done > '+self.ping_dir+'/ping_'+cluster+'_'+vm_params['vm_id']+'.out'
            pingactions.append(Remote(cmd, [site+'.grid5000.fr'], log_exit_code=False, 
                                    connection_params={'user': default_frontend_connection_params['user']}))
        logger.debug('%s', pformat(pingactions))    
        return ParallelActions(pingactions)
    
    def kill_ping(self, site):
        get_id = Remote('id | cut -d " " -f 1 | cut -d "=" -f 2 | cut -d "(" -f 1', 
                        [g5k_configuration['default_frontend']+'.grid5000.fr'], connection_params = default_frontend_connection_params ).run()

        for p in get_id.processes():
            id = p.stdout().strip()
        kill_ping = Remote( 'list_proc=`ps aux |grep ping|grep '+str(id)+'|grep -v grep| cut -d " " -f 5` ; echo $list_proc ; for proc in $list_proc; do kill $proc; done', 
                   [site+'.grid5000.fr'], connection_params = default_frontend_connection_params ).run()
        
    def stress_hosts(self, hosts, params = {'cpu': 0, 'ram': 0, 'hdd': 0}):
        cmd = ' apt-get install stress -y ; stress '
        for param, n in params.iteritems():
            if n != 0:
                if param == 'cpu':
                    cmd += ' --cpu '
                if param == 'ram':
                    cmd += ' --vm '
                if param == 'hdd':
                    cmd += ' --hdd '
                cmd += str(n)
        logger.info('Ready to execute stress on hosts % s\n%s', ' '.join( [self.host_string(host) for host in self.hosts]), cmd )
        return Remote(cmd, hosts)
    
    def get_cpu_topology(self, cluster):
        logger.info('Determining the architecture of cluster '+style.emph(cluster))
        frontend = get_cluster_site(cluster)            
        submission = OarSubmission(resources = "{'cluster=\""+cluster+"\"'}/nodes=1",
                                                         walltime = "0:02:00",
                                                         job_type = "allow_classic_ssh")
        ((job_id, _), ) = oarsub([(submission, frontend)])
        wait_oar_job_start( job_id, frontend )        
        host = get_oar_job_nodes( job_id, frontend )[0]
        capa = SshProcess('virsh capabilities', host, 
                          connection_params = {'user': default_frontend_connection_params['user'] }).run()
        oardel( [ (job_id, frontend) ] )
        root = ET.fromstring( capa.stdout )
        cpu_topology = []
        i_cell = 0
        for cell in root.findall('.//cell'):
            cpu_topology.append([])
            for cpu in cell.findall('.//cpu'):
                cpu_topology[i_cell].append(int(cpu.attrib['id']))
            i_cell += 1
        
        return cpu_topology     
    

class vm5k_engine_sequential( vm5k_engine ):

    def run(self):
        self.force_options()
        logger.debug('%s', pformat(self.options) )
        self.cluster = self.args[0]
        logger.debug('%s', pformat(self.cluster) )
        self.create_paramsweeper()
        
        while len(self.sweeper.get_remaining()) > 0:
            logger.info('Performing experiments on cluster %s', style.step(self.cluster))
            logger.info('%s', pformat( self.sweeper.stats()['done_ratio'] ))
        
            try: 
                self.get_resources()
                if not self.setup_cluster():
                    break
                
                print 'coucou'
                while True:
                    print 'ocuocu'
                    
                    combs = []
                    if not self.options.parallel:
                        combs.append(self.sweeper.get_next() ) 
                    else:
                        for i in range( min(len(self.hosts), len(self.sweeper.get_remaining())) ) :
                            combs.append( self.sweeper.get_next() )
                            
                    state = self.workflow( combs )
                    print 'coucou'
                    
                    if state:
                        for comb in combs:
                            self.sweeper.done( comb )
                        return True
                    else:
                        self.sweeper.cancel( combs )
                        return False
                    
                    if (int(self.job_info['start_date'])+self.job_info['walltime']) < int(time()):                        
                        logger.info('G5K reservation has been terminated, doing a new deployment')
                        break
                    
            finally:
                if self.job_info['job_id'] is not None:
                    if not self.options.keep_alive:
                        logger.info('Deleting job')
                        oardel( [(self.job_info['job_id'], self.job_info['site'])] )
                    else:
                        logger.info('Keeping job alive for debugging')

        logger.info( style.step('\n\nvm5k-engine COMPLETED ') )     



class vm5k_engine_parallel( vm5k_engine ):
    
    def run(self):
        print "parallel engine"
        self.force_options()
        logger.debug('%s', pformat(self.options) )
        self.cluster = self.args[0]
        logger.debug('%s', pformat(self.cluster) )
        self.create_paramsweeper()
        
        while len(self.sweeper.get_remaining()) > 0:
            logger.info('Performing experiments on cluster %s', style.step(self.cluster))
            logger.info('%s', pformat( self.sweeper.stats()['done_ratio'] ))
        
            try: 
                self.get_resources()
                if not self.setup_cluster():
                    break
               
                while True:
                    
                    combs = []
                    if not self.options.parallel:
                        combs.append(self.sweeper.get_next() ) 
                    else:
                        for i in range( floor(min(len(self.hosts)/self.options.n_nodes), len(self.sweeper.get_remaining())) ) :
                            combs.append( self.sweeper.get_next() )
                            
                    state = self.workflow( combs )
                    print 'coucou'
                    
                    if state:
                        for comb in combs:
                            self.sweeper.done( comb )
                        return True
                    else:
                        self.sweeper.cancel( combs )
                        return False
                    
                    if (int(self.job_info['start_date'])+self.job_info['walltime']) < int(time()):                        
                        logger.info('G5K reservation has been terminated, doing a new deployment')
                        break
                    
            finally:
                if self.job_info['job_id'] is not None:
                    if not self.options.keep_alive:
                        logger.info('Deleting job')
                        oardel( [(self.job_info['job_id'], self.job_info['site'])] )
                    else:
                        logger.info('Keeping job alive for debugging')

        logger.info( style.step('\n\nvm5k-engine-parallel COMPLETED ') )     





# Migration functions


def split_vm( vms_params, n = 2 ):
    split_vms = [0] * n
    for i_params in range(n):
        split_vms[i_params] = vms_params[i_params::n]
    return split_vms

def host_shortname( host):
    ''' Return the short name of a G5K host, with a color_style '''
    return host.address.split('.')[0]

def migration_measure( vm, host_src, host_dest, i_mes = 0, label = 'MIG', mig_speed = default_mig_speed):
    ''' Return an Remote action to measure migration time of vm_id from
    host_src to host_dest '''
    cmd = "virsh --connect qemu:///system migrate-setspeed "+vm['vm_id']+" "+str(mig_speed)+"; timestamp=`date +%s`; "+ \
            "duration=`/usr/bin/time  -f \""+str(i_mes)+"\t%e\" sh -c '"+ \
            "virsh --connect qemu:///system migrate "+vm['vm_id']+" --live --copy-storage-inc "+\
            "qemu+ssh://"+host_dest.address+"/system'  2>&1 `;"+ \
            "echo $timestamp "+vm['vm_id']+" $duration >> "+\
            label+"_"+host_shortname(host_src)+"_"+host_shortname(host_dest)+".out"
    logger.info(style.host(vm['vm_id'], 'object_repr')+': '+host_shortname(host_src)+" -> "+host_shortname(host_dest))
    logger.debug('%s %s %s', cmd, host_src, host_dest)
    return Remote(cmd, [ host_src ])

def measurements_loop(n_measure, vms, hosts, mig_function, mode, label = None, mig_speed = default_mig_speed, cache = False):
    ''' Perform a loop of migration given by the mig_function'''
    if not cache:
        clear_cache = Remote('sync; echo 3 > /proc/sys/vm/drop_caches', hosts)

    n_nodes = len(hosts)
    permut = deque(''.join([`num` for num in range(n_nodes)]))
    for i_mes in range( n_measure ):
        if not cache:
            clear_cache.run()
            clear_cache.reset()

        logger.info( style.user3('Measure '+str(i_mes+1)+'/'+str(n_measure)))
        ii = [int(permut[i]) for i in range(n_nodes)]

        nodes = [ hosts[ii[i]] for i in range(n_nodes)]

        migractions = mig_function( vms, nodes, i_mes = i_mes,
                    mode = mode, label = label, mig_speed = mig_speed)

        migractions.run()
        if not migractions.ok():
            return False

        if not cache:
            clear_cache.run()
            clear_cache.reset()

        if mig_function != split_merge_migrations:
            permut.rotate(+1)

    return True

def twonodes_migrations( vms, hosts, mode = 'sequential', i_mes = 0, label = 'SEQ', mig_speed = default_mig_speed):
    ''' Return SequentialActions to perform sequential measurements '''
    migractions = []
    for vm in vms:
        migractions.append(migration_measure( vm, hosts[0], hosts[1], i_mes, label, mig_speed = mig_speed))
    if mode == 'sequential':
        return SequentialActions(migractions)
    else:
        return ParallelActions(migractions)

def crossed_migrations( vms, hosts, mode = 'parallel', i_mes = 0, label = 'CROSSED', mig_speed = default_mig_speed):
    ''' Return ParallelActions to perform parallel measurements '''
    vms = split_vm(vms)
    migractions_01 = []; migractions_10 = []
    for vm in vms[0]:
        migractions_01.append(migration_measure( vm, hosts[0], hosts[1], i_mes, label, mig_speed = mig_speed))
    for vm in vms[1]:
        migractions_10.append(migration_measure( vm, hosts[1], hosts[0], i_mes, label, mig_speed = mig_speed))
    if mode == 'sequential':
        return ParallelActions( [ SequentialActions( migractions_01 ), SequentialActions( migractions_10 ) ] )
    else:
        return ParallelActions( migractions_01 + migractions_10 )

def circular_migrations( vms, hosts, mode = 'sequential', i_mes = 0, label = 'CIRC', mig_speed = default_mig_speed):
    n_nodes = len(hosts)
    if n_nodes < 3:
        print 'Error, number of hosts must be >= 3'
    elif len(vms) % (n_nodes) !=0:
        print 'Error, number of VMs not divisible by number of hosts'
    else:
        vms = split_vm(vms, n_nodes )
        migractions = []
        for i_from in range(n_nodes):
            i_to = i_from+1 if i_from < n_nodes-1 else 0
            if mode == 'sequential':
                label = 'CIRCSEQ'
            elif mode == 'parallel':
                label = 'CIRCPARA'
            migractions.append(twonodes_migrations(vms[i_to], hosts[i_from], hosts[i_to], mode = mode, i_mes = 0, label = label ))
        return ParallelActions(migractions)

def split_merge_migrations( vms, hosts, mode = 'parallel', i_mes = 0, label = 'SPLITMERGE', mig_speed = default_mig_speed):
    ''' Return ParallelActions to perform split migration '''
    if len(hosts) < 3:
        print 'Error, number of hosts must be >= 3'
    elif len(vms) % (len(hosts)) !=0:
        print 'Error, number of VMs not divisible by number of hosts'
    else:
        vms = split_vm(vms, len(hosts)-1 )
        migsplit = []
        migmerge = []
        for idx in range(len(hosts)-1):
            for vm in vms[idx]:
                migsplit.append(migration_measure( vm, hosts[0], hosts[idx+1], i_mes, label, mig_speed = mig_speed))
                migmerge.append(migration_measure( vm, hosts[idx+1], hosts[0], i_mes, label, mig_speed = mig_speed))

        if mode == 'sequential':
            return SequentialActions( [SequentialActions(migsplit), SequentialActions(migmerge)])
        else:
            return SequentialActions( [ParallelActions(migsplit), ParallelActions(migmerge)])
