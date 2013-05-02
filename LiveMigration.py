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
from execo import configuration, Put, Get, Remote, SequentialActions, ParallelActions, Host
from execo_g5k import oarsub, OarSubmission, oardel, wait_oar_job_start, get_oar_job_nodes, get_oar_job_subnets, get_oar_job_info
from execo_g5k.vmutils import *
from execo_g5k.planning import get_first_cluster_available
from execo_g5k.config import default_frontend_connexion_params
from execo_engine import Engine, ParamSweeper, sweep, slugify, logger

class LiveMigration(Engine):
    """ The main engine class, that need to be run with 
    execo-run LiveMigration -ML """
    
    def __init__(self):
        """ Add options for the number of measures, migration bandwidth, number of nodes
        walltime, env_file or env_name, stress, and clusters and initialize the engine """
        super(LiveMigration, self).__init__()
        configuration['color_styles']['step'] = 'red', 'bold'
        configuration['color_styles']['parameter'] = 'magenta', 'bold' 
        self.options_parser.set_usage("usage: %prog <cluster>")
        self.options_parser.set_description("Execo Engine that perform live migration of virtual machines with libvirt")
        self.options_parser.add_option("-m", dest = "n_measure", help = "number of measures", type = "int", default = 10 )
        self.options_parser.add_option("-b", dest = "mig_bw", help = "bandwith used for the migration", type = "int", default = 125 )
        self.options_parser.add_option("-e", dest = "env_name", help = "name of the environment to be deployed", type = "string", default = "squeeze-x64-prod")
        self.options_parser.add_option("-f", dest = "env_file", help = "path to the environment file", type = "string", default = None)
        self.options_parser.add_option("-n", dest = "n_nodes", help = "number of nodes to be deployed", type = "int", default = 2)
        self.options_parser.add_option("-w", dest = "walltime", help = "walltime for the submission", type ="string", default = "4:00:00")
        self.options_parser.add_argument("clusters", "comma separated list of clusters")
        logger.info( set_style('Initializing Live Migration engine', 'step') )
        
        
    def run(self):
        self.force_options()
        if globals().has_key('env_file'):
            self.options.env_file = self.env_file
        logger.debug('%s', pformat(self.options) )
        self.clusters = self.args[0].split(",")
        logger.debug('%s', pformat(self.clusters) )
        self.create_parameters()
        while len(self.sweeper.get_remaining()) > 0:
            logger.info('%s', set_style('Finding the first cluster available ', 'step'))
            (cluster, _) = get_first_cluster_available(self.clusters, self.options.walltime, self.options.n_nodes)
            logger.info('%s', set_style(cluster, 'user1'))
            
            try: 
                self.get_resources( cluster )
                self.setup_cluster()
                
                while True:
                    logger.info('%s', pformat( self.sweeper.stats()['done_ratio']['cluster'] ))
                    comb = self.sweeper.get_next(filtr = lambda r: filter(lambda subcomb: subcomb['cluster'] == cluster, r))
                    if not comb: 
                        logger.info('Cluster %s has been done, removing it from the list.', cluster)
                        self.clusters.remove(cluster)
                        break
                    state = self.workflow( comb )
                    print state
                    if state:
                        self.sweeper.done(comb)
                    else:
                        self.sweeper.cancel(comb)
                    
                    if (int(self.job_info['start_date'])+self.job_info['walltime']) > int(time()):
                        break
            finally:
                if self.job_info['job_id'] is not None:
                    logger.info('Deleting job')
                    oardel( [(self.job_info['job_id'], self.job_info['site'])] )
                    
        logger.info( set_style('\n\nLive Migration engine COMPLETED ', 'step') )     

    def force_options(self):
        for option in self.options.__dict__.keys():
            if self.__dict__.has_key(option):
                self.options.__dict__[option] = self.__dict__[option]
            
      
    def get_resources(self, cluster):
        """ Perform a reservation and return all the required job parameters """
        logger.info('%s %s', set_style('Getting the resources on Grid5000 for cluster', 'step'), cluster)
        site = get_cluster_site(cluster)
        submission = OarSubmission(resources = "slash_22=1+{'cluster=\"%s\"'}/nodes=%i" % (cluster, self.options.n_nodes),
                                             walltime = self.options.walltime,
                                             name = self.run_name,
                                             job_type = "deploy")
        logger.debug('%s', submission)
        ((job_id, _), ) = oarsub([(submission, site)])
        wait_oar_job_start( job_id, site )
        logger.info('Job %s has started!', set_style(job_id, 'emph'))
        self.job_info = {'job_id': job_id, 'site': site}
        self.job_info.update(get_oar_job_info( job_id, site ))
        logger.debug('%s', pprint(self.job_info))
        logger.info( set_style('Done\n', 'step') )
        
        logger.info('%s', set_style('Getting hosts and VLAN parameters ', 'report_error'))
        self.hosts = get_oar_job_nodes( job_id, site )
        logger.info('%s %s', set_style('Hosts:', 'parameter'),
                        ' '.join( [self.host_string(host) for host in self.hosts] ))
        self.ip_mac = get_oar_job_subnets( job_id, site )[0]         
        logger.info('%s %s %s ', set_style('Network:', 'parameter'), self.ip_mac[0][0], self.ip_mac[-1][0])
        logger.info( set_style('Done\n', 'step') )
        
    
    def setup_cluster(self):
        logger.info('%s', set_style('Installing and configuring hosts ', 'step'))                
        if self.options.env_file is None:
            virsh_setup = VirshCluster( self.hosts, env_name = self.options.env_name )
        else:
            virsh_setup = VirshCluster( self.hosts, env_file = self.options.env_file )
        virsh_setup.run()
        self.set_cpufreq('performance')
        logger.info('Hosts %s have been setup!', ', '.join([self.host_string(host) for host in self.hosts]) )
    
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
                cmd +='cpufreq-set -c '+str(i_proc)+' -g '+mode +'; '
            setmode.append(Remote(cmd, [p.host()]))
        setmode_act = ParallelActions(setmode).run()
        
        if not setmode_act.ok():
            logger.debug('Impossible to change cpufreq mode')            
            return False
        else:
            logger.debug('cpufreq mode set to %s', mode)
            return True
    
    def get_results(self, cluster, hosts, vms_params, comb):
        logger.info('%s \n', set_style(' Getting results from nodes and frontend ', 'step'))
        comb_dir = self.result_dir +'/'+ slugify(comb)+'/'
        
        try:
            mkdir(comb_dir)
        except:
            logger.warning('%s already exists', comb_dir)
            pass
        site = get_cluster_site(cluster)
        get_ping_files = []
        
        for vm_params in vms_params:
            get_ping_file = Get([site+'.grid5000.fr'], self.ping_dir+'/ping_'+cluster+'_'+vm_params['vm_id']+'.out', 
                local_location = comb_dir, connexion_params = default_frontend_connexion_params)            
            get_ping_files.append( get_ping_file) 
        rm_ping_dir = Remote('rm -rf '+self.ping_dir, [site+'.grid5000.fr'], 
                        connexion_params = default_frontend_connexion_params)
        ping_actions = SequentialActions( [ParallelActions(get_ping_files), rm_ping_dir] )
        
        get_mig_file = Get(hosts, '*.out', local_location = comb_dir)
        rm_mig_file = Remote('rm *.out', hosts)
        mig_actions = SequentialActions([get_mig_file, rm_mig_file])
        
        logger.info('Saving files into %s', comb_dir)
        get = ParallelActions( [ping_actions] + [mig_actions]).run()
        
        return get.ok()
    
    def ping_probes( self, vms_params, cluster, jobid = None):
        """A function that create a parallel actions to be executed on the site frontend of the cluster
        that ping the vms and write a log file"""
        site = get_cluster_site(cluster)
        self.ping_dir = self.result_dir.split('/')[-1]
        Remote('mkdir '+self.ping_dir, [site+'.grid5000.fr'], 
               connexion_params={'user': default_frontend_connexion_params['user']}).run()
        
        pingactions=[]
        for vm_params in vms_params:
            
            
            cmd='ping -i 0.2 '+vm_params['ip']+ \
            ' | while read pong; do pong=`echo $pong | cut -f4 -d "=" | cut -f1 -d \' \' `;'+\
            'if [ -z "$pong" ]; then pong=0.0; fi;'+\
            'echo "$(date +%s) $pong"; done > '+self.result_dir+'/ping_'+cluster+'_'+vm_params['vm_id']+'.out'
            pingactions.append(Remote(cmd, [site+'.grid5000.fr'], log_exit_code=False, 
                                    connexion_params={'user': default_frontend_connexion_params['user']}))
        logger.debug('%s', pformat(pingactions))    
        return ParallelActions(pingactions)
        
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
    
    def host_string(self, host):
        return set_style(host.address.split('.')[0], 'host')
                
    def align_string(self, string, kind):
        length = {'cluster': len(max(self.clusters, key=len))+1, 'VM': 3, 'mem': 5, 'hdd': 3}
        return string+''.join([' ' for i in range(length[kind] - len(string))])    
