from LiveMigration import *


class TestLiveMigration( LiveMigration ):
    
    def __init__(self):
        super(TestLiveMigration, self).__init__()
        self.n_nodes = 3
        self.run_name = 'coucou'
        
    def workflow(self, comb):
        """ Define the workflow of the experiments and use the parameters given by the combination 
        Return True if everything is allright, """
        exit_string = 'aborting workflow'
        
        hosts = self.hosts
        
        logger.info('%s', set_style('Creating VM disks', 'parameter'))
        cpusets = {'vm-'+str(i_vm): '0' for i_vm in range(comb['n_vm'])}
        vms_params = define_vms_params( comb['n_vm'], self.ip_mac, comb['mem_size'], n_cpu = comb['n_cpu'],
                                         cpusets = cpusets )
        
        if not create_disks( self.hosts, vms_params):
            logger.info('Unable to create the disks, %s', exit_string)
            return False
        
        if not install( vms_params, hosts[0] ):
            logger.info('Unable to install the VM, %s', exit_string)
            return False
        
        pingprobes = self.ping_probes(vms_params, comb['cluster'])
        logger.info('%s', set_style(' Lauching ping probes from frontend', 'parameter'))
        
        pingprobes.start()
        
        measure = measurements_loop(self.options.n_measure, vms_params, hosts, split_merge_migrations, 
                      'sequential', label = 'SPLIT_MERGE', mig_speed = self.options.mig_bw )
        pingprobes.kill()
        if not measure:
            logger.info('Unable to destroy the VM, %s', exit_string)
            return False
            
        if not destroy_all( hosts ):
            logger.info('Unable to destroy the VM, %s', exit_string)
            return False
        
        
        return self.get_results( comb['cluster'], hosts, vms_params, comb)
        
    
     
    def create_parameters(self):
        ''' Defining the dict of parameters to explore '''
        logger.info( set_style('Creating the parameters space and the iterator', 'step') )
        parameters = {'cluster': {}}
        
        logger.info(set_style(' CLUSTERS ', 'parameter'))
        for cluster in self.clusters:
            att = get_host_attributes(cluster+'-1')
            n_core = att['architecture']['smt_size']
            max_mem = att['main_memory']['ram_size']/1024**2
            n_vm = {}
            for i in range(3, n_core+1, 3):
                vm_max_cpu = min(n_core, 16)
                n_cpu = 1
                cpu_case = []
                cpu_case.append(n_cpu)
                while n_cpu*2 <= vm_max_cpu/i+1:
                    n_cpu = 2*n_cpu 
                    cpu_case.append(n_cpu)
                n_vm[i] = {'n_cpu': cpu_case}
            for i in n_vm.iterkeys():
                mem_size = [1024]
                li = mem_size[0]
                while li*2 <= max_mem/i:
                    li *= 2
                    mem_size.append(li)        
                n_vm[i]['mem_size'] = mem_size                
            
            parameters['cluster'][cluster] = { 'n_vm': n_vm }
            
            logger.info('- %s VM=1-%s vcpu=1-%s mem=256-%s ', 
                    set_style(self.align_string(cluster, 'cluster'), 'user1'),
                    self.align_string(str(n_core), 'VM'),
                    self.align_string(str(vm_max_cpu), 'VM'),
                    self.align_string(str(max_mem), 'mem'))
        parameters['stress'] = [None, 'cpu', 'ram', 'hdd']
        logger.info('%s    %s', set_style(' STRESS ', 'parameter'), ", ".join(map(str, parameters['stress'])))
        logger.debug('%s', pformat(parameters))
    
        sweeps = sweep( parameters )
        self.sweeper = ParamSweeper(path.join(self.result_dir, "sweeps"), sweeps)
        logger.info('%s combinations', len(self.sweeper.get_remaining()))
        logger.info( set_style('Done\n', 'step') )

        