from vm5k_engine import *
from itertools import product, repeat


class MicroArchBenchmark( vm5k_engine ):
    """ An execo engine that performs migration time measurements with 
    various cpu/cell usage conditions and VM colocation. """
    
    def __init__(self):
        super(MicroArchBenchmark, self).__init__()
        self.env_name = 'wheezy-x64-base'
        self.stress_time = 300
        
    def define_parameters(self):
        """ Create the parameters for the engine :
        - distribution of VM
        - properties of the multicore VM
        """
        cluster = self.cluster
        n_vm = 3
        
        self.cpu_topology = get_cpu_topology(cluster)
        
        n_core = len(self.cpu_topology[0])
        n_cell = len(self.cpu_topology)
        
        base_dist = list( product( range(0, n_vm+1), repeat=n_core))

        dists = []
        for cell_dist in base_dist:
            tmp_dist = ''.join( [ str(i) for i in sorted(list(cell_dist), reverse=True) ])
            one_cell = tmp_dist +'0'*(n_cell-1)*n_core
            if one_cell not in dists:
                dists.append(one_cell)
            
            for i in range(n_cell):
                other_cell = ''.join( [ str(k) for k in [item for sublist in list(repeat(tmp_dist, i+1)) for item in sublist ] ] )+(n_cell-i-1)*n_core*'0'          
                if other_cell not in dists:
                    dists.append(other_cell)
                    
        mult_cpu_vm = []
        for i in range(n_core+1):
            mult_cpu_vm.append( '1'*i+'0'*(n_core-i))
        mult_cpu_vm.remove('1'+'0'*(n_core-1))
        
        parameters = {'dist': dists, 'multi_cpu': mult_cpu_vm}
        logger.debug(parameters)
        
        return parameters
                    
    def workflow(self, comb, hosts, ip_mac): 
        """ Perform a cpu stress on the VM """
        host = hosts[0].address
        comb_ok = False
        try:
            logger.info(style.step('Performing combination '+slugify(comb)+' on '+host))
            
            logger.info(host+': Destroying existing VMS')
            destroy_vms(hosts)
            logger.info(host+': Removing existing drives')
            rm_qcow2_disks(hosts)
            
            logger.info(host+': Defining virtual machines for the combination')
            n_vm = self.comb_nvm(comb)
            if n_vm == 0:
	      self.sweeper.done( comb )
	      exit()
            
            # Affecting a cpuset to each virtual machine
            cpu_index = [item for sublist in self.cpu_topology for item in sublist]
            cpusets = []
            for i in range(len(comb['dist'])):
                index = cpu_index[i]
                for j in range(int(comb['dist'][i])): 
                    cpusets.append(str(index))
            
            vms = define_vms(['vm-'+str(i+1) for i in range(n_vm-1)], ip_mac = ip_mac, cpusets = cpusets)
            
            n_cpu = sum( [ int(i) for i in comb['multi_cpu'] ])
            if n_cpu > 1:                
                cpuset =  ','.join( str(i) for i in range(n_cpu) )
                print cpuset
                vms += define_vms(['vm-multi'], ip_mac = [ip_mac[len(vms)]], n_cpu = n_cpu, cpusets = cpuset)
                multi_cpu = True
            else:
                multi_cpu = False

            
            for vm in vms:
                vm['host'] = hosts[0]
            logger.info(', '.join( [vm['id']+' '+ vm['ip']+' '+str(vm['n_cpu'])+'('+vm['cpuset']+')' for vm in vms]))
            
                
            # Create disks, install vms and boot by core 
            logger.info(host+': Creating disks')
            create = create_disks(vms).run()
            logger.info(host+': Installing VMS')
            install_vms(vms).run()
            boot_vms_by_core(vms)
            
            # Prepare virtual machines for experiments
            stress = []
            logger.info(host+': Installing kflops on vms and creating stress action')
            stress.append( self.cpu_kflops([vm for vm in vms if vm['n_cpu'] == 1 ]) )
            
            if multi_cpu:
                logger.info(host+': Installing numactl and kflops on multicore vms')
                cmd =  'export DEBIAN_MASTER=noninteractive ; apt-get update && apt-get install -y  --force-yes numactl'
                inst_numactl = Remote( cmd, [vm['ip'] for vm in vms if vm['id'] == 'vm-multi']).run()
                self.cpu_kflops([vm for vm in vms if vm['id'] == 'vm-multi' ], install_only = True)
                for multi_vm in [vm for vm in vms if vm['id'] == 'vm-multi' ]:
                    for i in range(multi_vm['n_cpu']):
                        stress.append( Remote('numactl -C '+str(i)+' ./kflops/kflops > vm_multi_'+str(i)+'.out ', 
                                            [multi_vm['ip']] ) )
                        
                        
            logger.info(host+': Starting stress !! \n%s', pformat(stress) )
            stress_actions = ParallelActions(stress).start()
            for p in stress_actions.processes:
                if not p.ok:
                    exit()       
                    
            sleep(self.stress_time)
            logger.info(host+': Killing stress !!')
            stress_actions.kill()
            
            for p in stress_actions.processes:
                if not p.ok:
                    exit()  
            
            
            # Gathering results
            comb_dir = self.result_dir +'/'+ slugify(comb)+'/'
            try:
                mkdir(comb_dir)
            except:
                logger.warning('%s already exists', comb_dir)
            vms_ip = [vm['ip'] for vm in vms if vm['n_cpu'] == 1]
            comb_dir = self.result_dir +'/'+ slugify(comb)+'/'
            Get(vms_ip, ['{{vms_ip}}.out'], local_location = comb_dir).run()
            if multi_cpu:
                for multi_vm in [vm for vm in vms if vm['id'] == 'vm-multi' ]:
                    Get([multi_vm['ip']], ['vm_multi_'+str(i)+'.out ' for i in range(multi_vm['n_cpu']) ], 
                        local_location = comb_dir).run()
            
            comb_ok = True
        finally:
            print comb_ok
            if comb_ok:
                self.sweeper.done( comb )
            else:
                self.sweeper.cancel( comb )
            
    
    def comb_nvm(self, comb):
        """ """          
        n_vm = sum( [ int(i) for i in comb['dist'] ] )
        if sum( [ int(i) for i in comb['multi_cpu'] ]) > 1:
            n_vm += 1
        return n_vm
    
    def cpu_kflops(self, vms, install_only = False):
        vms_ip = [vm['ip'] for vm in vms]
        #ChainPut([Host(vm['ip']) for vm in vms], 'kflops.tgz' ).run()
        ChainPut(vms_ip, ['kflops.tgz'] ).run()
        TaktukRemote('echo 8146 > /proc/sys/kernel/pty/max',vms_ip).run()
        
        TaktukRemote( 'tar -xzf kflops.tgz; cd kflops; make', vms_ip).run()
        if not install_only:                
            return Remote('./kflops/kflops > {{vms_ip}}.out', vms_ip)


#    def mem_update(self, vms, size, speed):
#        """Copy, compile memtouch, calibrate and return memtouch action """
#        
#        logger.debug('VMS: %s', pformat (vms) )
#        vms_ip = [Host(vm['ip']) for vm in vms]        
#        #ChainPut(vms_ip, 'memtouch.tgz' ).run()
#        Put(vms_ip, 'memtouch.tgz' ).run()
#        Remote('tar -xzf memtouch.tgz; cd memtouch; gcc -O2 -lm -std=gnu99 -Wall memtouch-with-busyloop3.c -o memtouch-with-busyloop3', 
#               vms_ip ).run()
#        calibration = SshProcess('./memtouch/memtouch-with-busyloop3 --cmd-calibrate '+str(size), vms_ip[0] ).run()
#        args = None
#        for line in calibration.stdout().split('\n'):
#            if '--cpu-speed' in line:
#                args = line
#        if args is None:
#            return False
#        logger.debug('%s', args)
#        return Remote('./memtouch/memtouch-with-busyloop3 --cmd-makeload '+args+' '+str(size)+' '+str(speed), vms_ip)       
