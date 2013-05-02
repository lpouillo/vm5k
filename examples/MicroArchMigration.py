#!/usr/bin/env python
from LiveMigration import *
import xml.etree.ElementTree as ET

class MicroArchMigration( LiveMigration ):
    
    def __init__(self):
        super(MicroArchMigration, self).__init__()
        
    
    def workflow(self, comb):
        """ """
        hosts = self.hosts
        
        logger.info('%s', set_style(' Defining VM params', 'parameter'))
        cpusets = self.set_cpusets( comb['mapping'], comb['n_vm'] )
        
        vms_params = define_vms_params( comb['n_vm'], self.ip_mac, comb['mem_size'], n_cpu = comb['n_cpu'],
                                        cpusets = cpusets)
        logger.info('%s', pformat(vms_params) )
        
        logger.info('%s', set_style(' Creating VM disks', 'parameter'))
        create_disks( self.hosts, vms_params)
        
        logger.info('%s', set_style(' Lauching ping probes from frontend', 'parameter'))
        pingprobes = self.ping_probes(vms_params, comb['cluster'])
        pingprobes.start()
        
        logger.info('%s', set_style('Defining stress action', 'parameter'))
        stress_params = {'cpu': 0, 'ram': 0, 'hdd': 0}
        if comb['stress'] is not None:
            if comb['stress'] in [ 'cpu', 'ram']:
                stress_params[comb['stress']] = comb['n_cpu']
            if comb['stress'] == 'cpu_ram':
                stress_params['cpu'] = comb['n_cpu']
                stress_params['ram'] = comb['n_cpu']
        vms = []
        for vm in vms_params:
            vms.append( Host(vm['ip']+'.g5k'))      
        stress = self.stress_hosts(vms, stress_params)
        
        logger.info('%s', set_style('Sequential Migration ', 'user2'))
        destroy_all( self.hosts )
        install( vms_params, self.hosts[0] )
        stress.start()
        
        measurements_loop(self.options.n_measure, vms_params, self.hosts, twonodes_migrations, 
                      'sequential', label = 'SEQ', mig_speed = self.options.mig_bw )
        destroy_all( self.hosts )
        
        if comb['n_vm'] >= 2:
            logger.info('%s', set_style('Parallel Migration ', 'user2'))
            install( vms_params, self.hosts[0] )
            measurements_loop(self.options.n_measure, vms_params, self.hosts, twonodes_migrations, 
                          'parallel', label = 'PARA', mig_speed = self.options.mig_bw )
            destroy_all( self.hosts )
        stress.kill()
        pingprobes.kill()
        
        del vms_params[:]
        
        return self.get_results( comb['cluster'], self.hosts, vms_params, comb)
    
    def create_parameters(self):
        n_vm = [ 1, 2 ]
        n_cpu = [ 1, 2, 6, 8 ]
        mem_size = [ 1024, 2048, 4096 ]
        mapping = [ 'auto', 'one_core', 'one_core_by_vm',
           'one_core_one_cell_by_vm', 'one_cell', 'one_cell_by_vm' ]
        parameters = {'cluster': {} }
        for cluster in self.clusters:
            parameters['cluster'][cluster] = {
            'n_vm': n_vm,
            'n_cpu': n_cpu,
            'mem_size': mem_size,
            'mapping': mapping
            }
        parameters['stress'] = [ None, 'cpu', 'ram', 'cpu_ram']
        logger.info('\n%s', pformat(parameters))
        sweeps = sweep( parameters )
        self.sweeper = ParamSweeper( path.join(self.result_dir, "sweeps"), sweeps)  
        
    def set_cpusets(self, mapping, n_vm):
        """ Get the cpu topology seen by libvirt and create the cpusets for the different VM """
        cpu_topology = []
        capabilities = Remote( 'virsh capabilities', [self.hosts[0]] ).run()
        for p in capabilities.processes():
            root = ET.fromstring(p.stdout())
            host = root.find('host')  
            i_cell = 0
            for cell in host.findall('.//cell'):
                cpu_topology.append([])
                for cpu in cell.findall('.//cpu'):
                    cpu_topology[i_cell].append(int(cpu.attrib['id']))
                i_cell += 1     
        logger.info('cpu topology\n%s', pformat(cpu_topology))
        
        if mapping == 'auto':
            return ( {'vm-'+str(i): 'auto' for i in range(n_vm)} )    
        elif mapping == 'one_core':
            return ( {'vm-'+str(i): '0' for i in range(n_vm)})
        elif mapping == 'one_core_by_vm':
            return ( {'vm-'+str(i): str(cpu_topology[0][i]) for i in range(n_vm)})
        elif mapping == 'one_core_one_cell_by_vm':
            return ( {'vm-'+str(i): str(min(cpu_topology[i])) for i in range(n_vm)})
        elif mapping == 'one_cell':
            return ( {'vm-'+str(i): ','.join([str(j) for j in cpu_topology[0]]) for i in range(n_vm)})
        elif mapping == 'one_cell_by_vm':
            return ( {'vm-'+str(i): ','.join([str(j) for j in cpu_topology[i]]) for i in range(n_vm)})    
        
            
            
     
        