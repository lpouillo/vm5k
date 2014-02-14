from vm5k.engine import *
from itertools import product
import xml.etree.ElementTree as ET
import socket


class MicroarchMigration(vm5k_engine):
    """ An execo engine that performs migration time measurements with 
    various cpu/cell usage conditions and VM colocation. """

    def __init__(self):
        """ """
        super(MicroarchMigration, self).__init__()
        self.walltime = '6:00:00'
        self.n_nodes = 2
        self.n_measure = 20
        self.env_name = 'wheezy-x64-nfs'

    def workflow(self, comb): 

        cpu_topology = self.cpu_topology[comb['cluster']]
        cpu_index = [item for sublist in cpu_topology for item in sublist] 

        logger.info('Destroying VMS on all hosts')
        destroy_vms(self.hosts)
        n_vm = sum( [ int(i) for i in comb['dist'] ]) + 1
        cpusets = {}  
        i_vm = 0
        for i in range(len(comb['dist'])):
            for j in range(int(comb['dist'][i])):
                cpusets['vm-'+str(i_vm)] = str(cpu_index[i])
                i_vm += 1
        cpusets['vm-'+str(i_vm)] = str(0)
        
        vms = define_vms(n_vm, self.ip_mac, mem_size = 512, cpusets = cpusets)
        
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
        
        
        for type_stress in  [None, 'cpu', 'ram']:
            if type_stress == 'cpu':
                stress = self.cpu_kflops(vms)
            elif type_stress == 'ram':
                logger.info('Performing measurements with RAM stress')
                stress = self.mem_update(vms, 0.9*512, 10)
            if type_stress is not None:
                if type(stress) == type(True):
                    return False
                stress.start()
                for p in stress.processes():
                    if not p.ok():
                        return False
                
            logger.info(style.step('Performing measurements with '+str(type_stress)+' stress'))
            measure = measurements_loop(self.options.n_measure, [vms[-1]], self.hosts, twonodes_migrations, 
                 'sequential', label = str(type_stress), mig_speed = self.options.mig_bw )
            if type_stress is not None:
                stress.kill()
        self.vms = vms
        return True
        
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
        root = ET.fromstring( capa.stdout() )
        cpu_topology = []
        i_cell = 0
        for cell in root.findall('.//cell'):
            cpu_topology.append([])
            for cpu in cell.findall('.//cpu'):
                cpu_topology[i_cell].append(int(cpu.attrib['id']))
            i_cell += 1
        
        return cpu_topology

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

    
    def cpu_kflops(self, vms):
        logger.info('Installing kflops on vms')
        #ChainPut([Host(vm['ip']) for vm in vms], 'kflops.tgz' ).run()
        Put([Host(vm['ip']) for vm in vms], 'kflops.tgz' ).run()
        vms_ip = [vm['ip'] for vm in vms]
        make_all = Remote( 'tar -xzf kflops.tgz; cd kflops; make', vms_ip).run()
        
        return Remote('./kflops/kflops > {{vms_ip}}.out', vms_ip)
     
    def define_parameters(self):
        """ The base routines that define the parameters that need to be explored """
        
        max_vm_core = 3
        parameters = {'cluster': {}}
        self.cpu_topology = {}
        for cluster in self.clusters:
            parameters['cluster'][cluster] = {}
            self.cpu_topology[cluster] = self.get_cpu_topology(cluster)
            n_core = len(self.cpu_topology[cluster][0])
            n_cell = len(self.cpu_topology[cluster])
        
            dists = []
            
            for n_vm_core in range(max_vm_core+1):
                base_dist = list( product( range(0, max_vm_core+1), repeat = n_core-1))
                for dist in base_dist:
                    tmp_dist = str(n_vm_core)+''.join( [ str(i) for i in sorted(list(dist), reverse=True) ])+\
                        '0'*(n_cell-1)*(n_core-1)
                    if tmp_dist not in dists:
                        dists.append(tmp_dist )
            
            
#            base_dist = list( product( range(0, max_vm_core+1), repeat=n_core))
#            for dist in base_dist:
#                tmp_dist = ''.join( [ str(i) for i in sorted(list(dist), reverse=True) ])+\
#                    '0'*(n_cell-1)*n_core
#                if tmp_dist not in dists:
#                    dists.append(tmp_dist )
#            base_dist = list( product( range(0, max_vm_core+1), repeat=n_cell))
#            for cell_dist in base_dist:
#                tmp_dist = ''.join( [ str(i)*n_core for i in sorted(list(cell_dist), reverse=True) ])
#                if tmp_dist not in dists:
#                    dists.append(tmp_dist)
                    
            tmp_dists = list(dists)
            for dist in tmp_dists:
                if sum( [ int(i) for i in dist ]) > 48:
                    dists.remove(dist) 
            

            parameters['cluster'][cluster]['dist'] = dists

        return parameters
    
    def get_results(self, comb):
        logger.info('Getting the results')
        comb_dir = self.result_dir +'/'+ slugify(comb)+'/'
        try:
            mkdir(comb_dir)
        except:
            logger.warning('%s already exists', comb_dir)
        vms_ip = [vm['ip'] for vm in self.vms]        
        Get(vms_ip, '{{vms_ip}}.out', local_location = comb_dir).run()
        get_mig_file = Get(self.hosts, '*.out', local_location = comb_dir).run()
        rm_mig_file = Remote('rm *.out', self.hosts).run()
        logger.info('Saving files into %s', comb_dir)
        
        get_munin_server = Remote('ls /var/cache/munin/www', self.hosts).run()
        for p in get_munin_server.processes():
            if p.ok():
                service_node = p.host()
                break;
        
        SshProcess('tar -czf www.tgz --directory /var/cache/munin www', service_node).run()
        Get([service_node], ['www.tgz'], local_location = comb_dir).run()
         
        return True