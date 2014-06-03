#!/usr/bin/env python
from vm5k.engine import *
#from itertools import product, repeat


class VMBootMeasurement(vm5k_engine_para):
    def __init__(self):
        super(VMBootMeasurement, self).__init__()
        self.n_nodes = 1
        self.options_parser.add_option("--vm",
            dest="n_vm", type="int", default=1,
            help="maximum number of VMs")
        self.options_parser.add_option("--cpu",
            dest="n_cpu", type="int", default=1,
            help="maximum number of CPUs")
        self.options_parser.add_option("--mem",
            dest="n_mem", type="int", default=1,
            help="maximum number of memory")

    def define_parameters(self):
        """Define the parameters you want to explore"""
        cluster = self.cluster
        #self.cpu_topology = get_cpu_topology(cluster, xpdir=self.result_dir)
        parameters = {
            'n_mem': range(1, self.options.n_mem + 1),
            'n_cpu': range(1, self.options.n_cpu + 1),
            'n_vm': range(1, self.options.n_vm + 1),
            'vm_policy': ['one_vm_per_core', 'vm_one_core'],
            'image_policy': ['one', 'one_per_vm']}

        logger.debug(parameters)

        return parameters


    def comb_nvm(self, comb):
        """Calculate the number of virtual machines in the combination,
required to attribute a number of IP/MAC for a parameter combination """
        n_vm = comb['n_vm']
        return n_vm

    def workflow(self, comb, hosts, ip_mac):
        """Perform a boot measurements on the VM """
        logger.debug('hosts %s', hosts)
        logger.debug('ip_mac %s', ip_mac)

        thread_name = style.Thread(' '.join(sorted(map(lambda x: x.split('.')[0], \
                                                       hosts))) + '\n')
        comb_ok = False
        try:
            logger.info(style.step('Performing combination ' + slugify(comb)))
            logger.info(thread_name)

            logger.detail('Destroying all vms on hosts')
            destroy_vms(hosts)

            cpusets = []

            if comb['vm_policy'] == 'one_vm_per_core':
                for i in range(comb['n_vm']):
                    cpusets.append(i)
            else:
                for i in range(comb['n_vm']):
                    cpusets.append(0)
                    
            backing_file='/home/lpouilloux/synced/images/benchs_vms.qcow2'    

            real_file = False
            if comb['image_policy'] == 'one_per_vm':
                real_file = True

            # Define the virtual machines for the combination
            vms = define_vms(['vm-' + i for i in range(comb['n_vm'])],
                              ip_mac=ip_mac,
                              host=hosts[0],
                              n_cpu=comb['n_cpu'],
                              cpusets=cpusets,
                              mem=comb['n_mem'] * 1024,
                              backing_file=backing_files,
                              real_file=real_file)
            
            # Create disks, install vms and boot by core
            logger.info(host + ': Creating disks')
                
            
            create = create_disks(vms).run()
            
            if not create.ok:
                logger.error(host + ': Unable to create the VMS disks %s',
                             slugify(comb))
                exit()
                
            logger.info(host + ': Installing VMS')
            install = install_vms(vms).run()
            if not install.ok:
                logger.error(host + ': Unable to install the VMS  %s',
                             slugify(comb))
                exit()
                
            logger.info(style.Thread(host)+': Starting VMS '+', '.join( [vm['id'] for vm in sorted(vms)]))
            
            now = time.time()

            start_vms(vms).run()
            booted = wait_vms_have_started(vms)
            if not booted:
                logger.error(host + ': Unable to boot all the VMS for %s',
                             slugify(comb))
                exit()
                
            get_uptime = TaktukRemote('cat /proc/uptime', [vm['ip']
                                for vm in vms]).run()
            boot_time = {}
            for p in get_uptime.processes:
                boot_time[p.host.address] = now - float(p.stdout.strip().split(' ')[0])
            
            get_ssh_up = TaktukRemote('grep listening /var/log/auth.log' + \
                        ' |grep 0.0.0.0|awk \'{print $1" "$2" "$3}\'',
                        [vm['ip'] for vm in vms]).run()
            
            boot_duration = []
            for p in get_ssh_up.processes:
                ssh_up = time.mktime(datetime.datetime.strptime('2014 ' + \
                        p.stdout.strip(), "%Y %b %d %H:%M:%S").timetuple())
                boot_duration.append(ssh_up - boot_time[p.host.address])

            uptime = string.join(array(boot_duration), ",")
            
             # Gathering results
            comb_dir = self.result_dir + '/' + slugify(comb) + '/'
            try:
                mkdir(comb_dir)
            except:
                logger.warning(host +
                    ': %s already exists, removing existing files', comb_dir)
                for f in listdir(comb_dir):
                    remove(comb_dir + f)

            logger.info(host + ': Writing boot time in result files')

            text_file = open(comb_dir+"boot_time.txt", "w")
            text_file.write(uptime)
            text_file.close()
            
            comb_ok = True
                    
        finally:
            if comb_ok:
                self.sweeper.done(comb)
                logger.info(thread_name + ': ' + slugify(comb) + \
                             ' has been done')
            else:
                self.sweeper.cancel(comb)
                logger.warning(thread_name + ': ' + slugify(comb) + \
                            ' has been canceled')
            logger.info(style.step('%s Remaining'),
                        len(self.sweeper.get_remaining()))
            
            
if __name__ == "__main__":
    engine = VMBootTime()
    engine.start()