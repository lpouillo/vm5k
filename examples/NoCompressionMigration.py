#!/usr/bin/env python
from LiveMigration import *
from execo.time_utils import sleep

class NoCompressionMigration( LiveMigration ):
    
    def __init__(self):
        super(NoCompressionMigration, self).__init__()
        self.env_file = '~/synced/environments/cloudperf/cloudperf.env'
                
    def workflow(self, comb):
        exit_string = set_style('\nABORTING WORKFLOW\n', 'report_error')
        logger.info('%s \n%s', set_style('Performing measurements for: ', 'report_error'), pformat(comb))
        
        logger.info('%s', set_style('Defining VM parameters', 'parameter'))
        cpusets = {'vm-'+str(i_vm): '0' for i_vm in range(1 + 2*comb['cpu_load'])}

        self.vms_params = define_vms_params( 1 + 2*comb['cpu_load'], self.ip_mac, vms_params = [],
                                        mem_size = comb['mem_size'], cpusets = cpusets)
        
        logger.info('%s', set_style('Creating VM disks', 'parameter'))
        if not create_disks( self.hosts, self.vms_params):
            logger.error('Unable to create the disks, %s', exit_string)
            return False
        
        destroy_all( self.hosts )
        
        logger.info('%s', set_style('Performing migration with other VM on node SRC ', 'user2'))
        
        mig_vm = self.vms_params[0]
        
        static_vms = list(self.vms_params) 
        static_vms.remove(mig_vm)
        split_vms = split_vm(static_vms)
        
        if not install([mig_vm], self.hosts[0]):
            logger.error('Unable to install the migrating VM, %s', exit_string)
            return False
        if len(split_vms[0]) > 0:
            if not install( split_vms[0], self.hosts[0]):
                logger.error('Unable to install the colocated VM, %s', exit_string)
                return False
        
        
        logger.info('%s', set_style('Launching ping probes from frontend', 'parameter'))
        pingprobes = self.ping_probes( self.vms_params, comb['cluster'] )
        pingprobes.start()
              
          
        stress = self.mem_update( [mig_vm]+split_vms[0], size = comb['mem_size'] * 0.9, 
                                  speed = comb['mig_bw']*comb['mem_update_rate']/100 )
        
        if stress == 'ERROR':
            return False
        
        logger.info('%s %s', set_style('Starting stress on', 'parameter'),
                    ' '.join([set_style(param['vm_id'], 'object_repr') for param in split_vms[0]+[mig_vm]]))
        stress.start()
        
        sleep( comb['mem_size'] * comb['mem_update_rate']/ 10000 )
        
        measurements_loop(self.options.n_measure, [mig_vm], self.hosts, twonodes_migrations, 
                      'sequential', label = 'ONE', mig_speed = comb['mig_bw'] )
        stress.kill()
        
        logger.info('%s', set_style('Performing migration with other VM on BOTH nodes ', 'user2'))
        destroy_all( self.hosts )
        
        if not install([mig_vm], self.hosts[0]):
            logger.error('Unable to install the migrating VM, %s', exit_string)
            return False
         
        if len(split_vms[0]) > 0:
            if not install( split_vms[0], self.hosts[0]):
                logger.error('Unable to install the colocated VM on SRC, %s', exit_string)
                return False
            if not install( split_vms[1], self.hosts[1]):
                logger.error('Unable to install the colocated VM on DST, %s', exit_string)
                return False        
            
        stress = self.mem_update( self.vms_params , size = comb['mem_size'] * 0.9, 
                                  speed = comb['mig_bw']*comb['mem_update_rate']/100 )
        if stress == 'ERROR':
            return False
        
        logger.info('%s %s', set_style('Starting stress on ', 'parameter'),
                    ' '.join([set_style(param['vm_id'], 'object_repr') for param in self.vms_params ]))
        stress.start()
        sleep( comb['mem_size'] * comb['mem_update_rate']/ 10000 )
                    
        measurements_loop(self.options.n_measure, [mig_vm], self.hosts, twonodes_migrations, 
                      'sequential', label = 'BOTH', mig_speed = comb['mig_bw'] )
        stress.kill()
        destroy_all( self.hosts )
         
        pingprobes.kill()
        
        return True
        
        
    def mem_update(self, vms_params, size, speed):
        """Copy, compile memtouch, calibrate and return memtouch action """
        vms = [ Host(vm_param['ip']+'.g5k') for vm_param in vms_params ]
        logger.info('VMS: %s', pformat (vms) )
        
        files = [ 'memtouch/memtouch-with-busyloop3.c' ] 
        putfiles = Put(vms, files).run()
        puttries = 1
        while (not putfiles.ok()) and puttries < 5:
            puttries += 1
            sleep(5)            
            files = [ 'memtouch/memtouch-with-busyloop3.c' ] 
            putfiles = Put(vms, files).run()
        if not putfiles.ok():
            return 'ERROR'
        Remote('gcc -O2 -lm -std=gnu99 -Wall memtouch-with-busyloop3.c -o memtouch-with-busyloop3', vms ).run()
        calibration = Remote('./memtouch-with-busyloop3 --cmd-calibrate '+str(size), [vms[0]] ).run()
        args = ''
        for p in calibration.processes():
            for line in p.stdout().split('\n'):
                if '--cpu-speed' in line:
                    args = line
        logger.debug('%s', args)
        return Remote('./memtouch-with-busyloop3 --cmd-makeload '+args+' '+str(size)+' '+str(speed), vms)       
    
        
    def define_parameters(self):
        """ Definining the ParamSweeper for the engine """
        return {
          'cluster':            self.clusters,
          'mem_size':           [ 2048, 4096, 8192 ],
          'mig_bw':             [ 32, 125 ],
          'cpu_load':           [ 0, 1, 2, 3 ],
          'mem_update_rate':    [ 0, 10, 25, 50, 75 ]
          }
        
    
    
