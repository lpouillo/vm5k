from LiveMigration import *
from execo import sleep
from random import uniform
import itertools

class VMMulticore( LiveMigration ):
    
    def __init__(self):
        super(VMMulticore, self).__init__()
        self.n_nodes = 1
        self.env_name = 'wheezy-x64-base'
        
    def workflow(self, comb):
         
        destroy_vms(self.hosts)
        n_vm = sum( [ int(i) for i in comb['dist'] ])
        i_vm = 0
        cpusets = {}
        for i in range(comb['active_core']):
            for j in range(1, int(comb['dist'][i])+1):
                cpusets['vm-'+str(i_vm)] = str(i)
                i_vm += 1
        logger.info('Defining VMS')
        vms = define_vms(n_vm, self.ip_mac,  cpusets = cpusets)
        logger.info(pformat(vms))
        for vm in vms:
            vm['host'] = self.hosts[0]
        
        logger.info('Creating disks')
        create_disks(vms).run()
         
        
        logger.info('Installing VMS')
        install_vms(vms).run()
        logger.info('Starting VMS')
        start_vms(vms).run()
        wait_vms_have_started(vms)
        
        
        logger.info('Installing kflops')
        Put(self.hosts, 'kflops.tgz').run()
        copy_all = []
        for vm in vms:
            copy = Remote( 'scp kflops.tgz root@'+vm['ip']+': ', self.hosts)            
            copy_all.append(copy)
        ParallelActions(copy_all).run()
        
        vms_ip = [vm['ip']+'.g5k' for vm in vms]
        make_all = Remote( 'tar -xzf kflops.tgz; cd kflops; make', vms_ip).run()
        logger.info('Launching kflops')
        stress = Remote('./kflops/kflops > {{vms_ip}}.out', vms_ip).start()
        sleep(300)
        stress.kill()
        logger.info('Getting the results')
        comb_dir = self.result_dir +'/'+ slugify(comb)+'/'
        Get(vms_ip, '{{vms_ip}}.out', local_location = comb_dir).run()
        
        destroy_vms(self.hosts)
        
        return True
        
    
     
    def define_parameters(self):
        
        parameters = {'cluster': {}}
        for cluster in self.clusters:
            parameters['cluster'][cluster] ={'active_core': {}}
            
            base_dist = [ k for k in range(1,9) ]
            for i in range(1,13):         
                parameters['cluster'][cluster]['active_core'][i] = {'dist': []}
                
                n_permut = 8 if i == 1 else 10
                
                for j in range(n_permut):
                    list = [ int(uniform(1,9)) for k in range(i)]
                    while ''.join(str(n) for n in list) in parameters['cluster'][cluster]['active_core'][i]['dist']:
                        list = [ int(uniform(1,9)) for k in range(i)]
                    parameters['cluster'][cluster]['active_core'][i]['dist'].append(''.join(str(n) for n in list))
            
        return parameters


    
    
    def get_results(self, host):
        """ """ 