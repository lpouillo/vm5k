from vm5k_engine import *
from itertools import product, repeat
import xml.etree.ElementTree as ET

class MicroArchBenchmark( vm5k_engine_parallel ):
    """ An execo engine that performs migration time measurements with 
    various cpu/cell usage conditions and VM colocation. """
    
    def __init__(self):
        super(MicroArchBenchmark, self).__init__()
        self.walltime = '2:00:00'
        self.n_measure = 20
        self.env_name = 'wheezy-x64-base'
        self.parallel = True
        
        
    def define_parameters(self):
        """ Create the parameters for the engine :
        - distribution of VM
        - properties of the multicore VM
        """
        cluster = self.cluster
        n_vm = 3
        
        self.cpu_topology = self.get_cpu_topology(cluster)
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
                    
        mutl_cpu_vm = []
        for i in range(n_core+1):
            mutl_cpu_vm.append( '1'*i+'0'*(n_core-i))

        parameters = {'dist': dists, 'multi_cpu': mutl_cpu_vm}
        return parameters
    
    
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
    
                    
    def workflow(self, combs): 
        """ Perform a cpu stress on the VM """
        
        pprint( combs )
    
        cpu_index = [item for sublist in self.cpu_topology for item in sublist] 
        
        logger.info('Destroying VMS on all hosts')
        destroy_vms(self.hosts)
        n_vm = sum( [ int(i) for comb in combs.itervalues() for i in comb['dist'] ] )
        for comb in combs:
            if sum( [ int(i) for comb in comb['multi_cpu'] ]) > 0:
                n_vm += 1
        
        cpusets = {}  
        n_cpus = {}
        i_vm = 0
        for comb in combs.itervalues():
            for i in range(len(comb['dist'])):
                for j in range(int(comb['dist'][i])):
                    cpusets['vm-'+str(i_vm)] = str(cpu_index[i])
                    i_vm += 1
        vms = define_vms(n_vm, self.ip_mac, mem_size = 512, cpusets = cpusets)
        # Adding the multicore virtual machine
        for comb in combs.itervalues():
            n_cpu = sum( [ int(i) for comb in comb['multi_cpu'] ]) 
            if n_cpu > 0:
                vms = define_vms(n_vm, self.ip_mac, mem_size = 512, cpusets = cpusets, vms = vms)
            
        logger.debug(pformat(vms))
        logger.info('Cleaning all disks')
        self.setup.create_disk_image(clean = True)
        self.setup.ssh_keys_on_vmbase()
        
        logger.info('Creating disks')
        action = create_disks_on_hosts(vms, self.hosts).run()
        if not action.ok():
            return False
        for vm in vms:
            vm['host'] = self.hosts[0]
        
        logger.info('VMs defined\n'+'\n'.join( [ vm['vm_id']+': '+
            vm['cpuset']+' '+vm['host'].address+' '+vm['ip']  for vm in vms ]))
        logger.info('Installing VMS')
        action = install_vms(vms).run()
        if not action.ok():
            return False
        logger.info('Starting VMS')
        action = start_vms(vms).run()
        if not action.ok():
            return False
        if not wait_vms_have_started(vms, self.hosts[0]):
            return False
        
        
        stress = self.cpu_kflops(vms)
        stress.start()
        for p in stress.processes():
            if not p.ok():
                return False
        stress.kill()
        self.vms = vms
        
        return True
    
    
    def cpu_kflops(self, vms):
        logger.info('Installing kflops on vms')
        #ChainPut([Host(vm['ip']) for vm in vms], 'kflops.tgz' ).run()
        Put([Host(vm['ip']) for vm in vms], 'kflops.tgz' ).run()
        vms_ip = [vm['ip'] for vm in vms]
        make_all = Remote( 'tar -xzf kflops.tgz; cd kflops; make', vms_ip).run()
        
        return Remote('./kflops/kflops > {{vms_ip}}.out', vms_ip)


    def mem_update(self, vms, size, speed):
        """Copy, compile memtouch, calibrate and return memtouch action """
        
        logger.debug('VMS: %s', pformat (vms) )
        vms_ip = [Host(vm['ip']) for vm in vms]        
        #ChainPut(vms_ip, 'memtouch.tgz' ).run()
        Put(vms_ip, 'memtouch.tgz' ).run()
        Remote('tar -xzf memtouch.tgz; cd memtouch; gcc -O2 -lm -std=gnu99 -Wall memtouch-with-busyloop3.c -o memtouch-with-busyloop3', 
               vms_ip ).run()
        calibration = SshProcess('./memtouch/memtouch-with-busyloop3 --cmd-calibrate '+str(size), vms_ip[0] ).run()
        args = None
        for line in calibration.stdout().split('\n'):
            if '--cpu-speed' in line:
                args = line
        if args is None:
            return False
        logger.debug('%s', args)
        return Remote('./memtouch/memtouch-with-busyloop3 --cmd-makeload '+args+' '+str(size)+' '+str(speed), vms_ip)       
