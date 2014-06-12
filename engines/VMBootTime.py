#!/usr/bin/env python
from vm5k.engine import *
#from itertools import product, repeat
import sys
import time
import datetime
import string
import random
from execo import logger as ex_log


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
        #self.cpu_topology = get_cpu_topology(cluster, xpdir=self.result_dir)
        parameters = {
            'n_mem': range(1, self.options.n_mem + 1),
            'n_cpu': range(1, self.options.n_cpu + 1),
            'n_vm': range(1, self.options.n_vm + 1),
            'vm_policy': ['one_vm_per_core', 'vm_one_core'],
            'image_policy': ['one', 'one_per_vm'],
            'vm_boot_policy': ['all_at_once','one_then_others'],
            'number_of_collocated_vms' : range(0,3),
            'load_injector': ['cpu','memory','mixed'],
            'iteration': range(1,6)}

        logger.debug(parameters)

        return parameters

    def comb_nvm(self, comb):
        """Calculate the number of virtual machines in the combination,
required to attribute a number of IP/MAC for a parameter combination """
        n_vm = comb['n_vm'] + comb['n_vm'] * comb['number_of_collocated_vms']
        return n_vm

    def workflow(self, comb, hosts, ip_mac):
        """Perform a boot measurements on the VM """
        host = hosts[0]

        logger.debug('hosts %s', host)
        logger.debug('ip_mac %s', ip_mac)

        thread_name = style.Thread(host.split('.')[0]) + ': '
        comb_ok = False
        try:
            logger.info(thread_name)
            logger.info(style.step('Performing combination ' + slugify(comb)))

            logger.detail(thread_name + 'Destroying all vms on hosts')
            destroy_vms(hosts)
            sleep(30)
            
            cpusets = []
            collocated_cpusets = []
            
            if comb['vm_policy'] == 'one_vm_per_core':
                for i in range(comb['n_vm']):
                    cpusets.append(','.join(str(i)
                            for j in range(comb['n_cpu'])))
            else:
                for i in range(comb['n_vm']):
                    cpusets.append(str(0))

            backing_file = '/home/lpouilloux/synced/images/benchs_vms.qcow2'
            real_file = True if comb['image_policy'] == 'one_per_vm' else False
            
            umount = TaktukRemote('sync; echo 3 > /proc/sys/vm/drop_caches; umount /tmp; sleep 5; mount /tmp', [hosts[0]]).run()
            for p in umount.processes:
                p.shell = True
                
            retry = 10
            
            while ( not umount.finished_ok ) and ( retry > 0 ):
                
                #logger.debug(host + ': Failed to unmount /tmp for  %s, retrying... (%s)',
                #             slugify(comb),str(retry))
                #for p in umount.processes:
                #    logger.error(host + ' : mount/umount error : %s %s', p.stdout.strip(),p.stderr.strip())
                
                lsof = Remote('lsof /tmp; virsh list', [hosts[0]])
                for p in lsof.processes:
                    p.ignore_exit_code = p.nolog_exit_code = True
                
                lsof.run()
                
                for p in lsof.processes:
                    logger.error(host + ' : lsof /tmp : %s', p.stdout.strip())
                
                 
                sleep(5)
                
                umount = TaktukRemote('sync; echo 3 > /proc/sys/vm/drop_caches; umount /tmp; sleep 5; mount /tmp', [hosts[0]]).run()
                
                for p in umount.processes:
                    p.shell = True
                
                retry -= 1
                    
            
            if not umount.finished_ok:
                logger.error(host + ': Failed to unmount /tmp for  %s (%s)',
                             slugify(comb), str(retry))
                for p in umount.processes:
                    logger.error(host + ' : mount/umount error : %s %s', p.stdout.strip(),p.stderr.strip())
                
                lsof = Remote('lsof /tmp; virsh list', [hosts[0]])
                for p in lsof.processes:
                    p.ignore_exit_code = p.nolog_exit_code = True
                
                lsof.run()
                
                for p in lsof.processes:
                    logger.error(host + ' : lsof /tmp : %s', p.stdout.strip())
                
                exit()
            
            if comb['number_of_collocated_vms'] > 0:
                
                if comb['vm_policy'] == 'one_vm_per_core':
                    vms_ids = ['collocated-vm-' + str(i) for i in range(comb['n_vm']*comb['number_of_collocated_vms'])]
                    collocated_ip_mac = ip_mac[0:comb['n_vm']*comb['number_of_collocated_vms']]
                    ip_mac = ip_mac[comb['n_vm']*comb['number_of_collocated_vms']:]
                    for i in range(comb['n_vm']):
                        for k in range(comb['number_of_collocated_vms']):
                            collocated_cpusets.append(','.join(str(i)
                                for j in range(comb['n_cpu'])))
                else:
                    vms_ids = ['collocated-vm-' + str(i) for i in range(comb['number_of_collocated_vms'])]
                    
                    collocated_ip_mac = ip_mac[0:comb['number_of_collocated_vms']]
                    ip_mac = ip_mac[comb['number_of_collocated_vms']:]
                    
                    for k in range(comb['number_of_collocated_vms']):
                        collocated_cpusets.append(str(0))
                        
                # Define and start collocated VMS
                collocated_vms = define_vms(vms_ids,
                              ip_mac=collocated_ip_mac,
                              host=hosts[0],
                              n_cpu=comb['n_cpu'],
                              cpusets=collocated_cpusets,
                              mem=comb['n_mem'] * 1024,
                              backing_file=backing_file)
                
                for vm in collocated_vms:
                    vm['host'] = hosts[0]
    
                # Create disks, install vms and boot by core
                logger.info(thread_name + ': Creating disks for collocated VMs')
                    
                create = create_disks(collocated_vms).run()
                if not create.ok:
                    logger.error(thread_name + 'Unable to create the VMS disks %s for collocated VMs',
                                 slugify(comb))
                    exit()
    
                logger.info(thread_name + 'Installing VMS for collocated VMs')
                install = install_vms(collocated_vms).run()
                if not install.ok:
                    logger.error(host + ': Unable to install the VMS  %s for collocated VMs',
                                 slugify(comb))
                    exit()
                    
                logger.info(style.Thread(host)+': Starting collocated VMS '+', '.join( [vm['id'] for vm in sorted(collocated_vms)]))
                
                start_vms(collocated_vms).run()
                booted = wait_vms_have_started(collocated_vms)
                if not booted:
                    logger.error(host + ': Unable to boot all the collocated VMS for %s',
                                 slugify(comb))
                    exit()
                
                sleep(30)
                
                if comb['load_injector'] == 'cpu':
                    injector = self.kflops(collocated_vms).start()
                elif comb['load_injector'] ==  'mem':
                    injector = self.cache_bench(collocated_vms).start()
                else:
                    mem = []
                    cpu = []
                    for v in collocated_vms:
                        random.choice((mem, cpu)).append(v)
                    injector = []
                    injector.append(self.kflops(cpu).start())
                    injector.append(self.cache_bench(mem).start())


            # Define the virtual machines for the combination
            vms = define_vms(['vm-' + str(i) for i in range(comb['n_vm'])],
                              ip_mac=ip_mac,
                              host=hosts[0],
                              n_cpu=comb['n_cpu'],
                              cpusets=cpusets,
                              mem=comb['n_mem'] * 1024,
                              backing_file=backing_file,
                              real_file=real_file)
            for vm in vms:
                vm['host'] = hosts[0]

            # Create disks, install vms and boot by core
            logger.info(thread_name + ': Creating disks')
                
            create = create_disks(vms).run()
            if not create.ok:
                logger.error(thread_name + 'Unable to create the VMS disks %s',
                             slugify(comb))
                exit()

            logger.info(thread_name + 'Installing VMS')
            install = install_vms(vms).run()
            if not install.ok:
                logger.error(host + ': Unable to install the VMS  %s',
                             slugify(comb))
                exit()
                
            logger.info(style.Thread(host)+': Starting VMS '+', '.join( [vm['id'] for vm in sorted(vms)]))
            
                
            logger.debug(host + ': Sucessfully clear fs cache')
                
            mpstat = Remote('mpstat 5 -P ALL > /tmp/mpstats', [hosts[0]]).start()
            
            now = time.time()
            
            vms_sda_stat = []
            
            if comb['vm_boot_policy'] == 'all_at_once':
                start_vms(vms).run()
                booted = wait_vms_have_started(vms)
                if not booted:
                    logger.error(host + ': Unable to boot all the VMS for %s',
                                 slugify(comb))
                    exit()
                
                sleep(30)
                get_uptime = TaktukRemote('cat /proc/uptime', [vm['ip']
                                    for vm in vms]).run()
                boot_time = {}
                for p in get_uptime.processes:
                    boot_time[p.host.address] = now - float(p.stdout.strip().split(' ')[0])
                
                get_sda_stat = TaktukRemote('cat /sys/block/vda/stat',
                                [vm['ip'] for vm in vms]).run()
                    
                for p in get_sda_stat.processes:
                    vms_sda_stat.append(p.stdout.strip())
                
                get_ssh_up = TaktukRemote('grep listening /var/log/auth.log' + \
                            ' |grep 0.0.0.0|awk \'{print $1" "$2" "$3}\' | tail -n 1',
                            [vm['ip'] for vm in vms]).run()
                
                boot_duration = {}
                for p in get_ssh_up.processes:
                    ssh_up = time.mktime(datetime.datetime.strptime('2014 ' + \
                            p.stdout.strip(), "%Y %b %d %H:%M:%S").timetuple())
                    boot_duration[p.host.address] = str(ssh_up - boot_time[p.host.address])
    
                #uptime = string.join(boot_duration, ",")
            else:
                first_vm = [vms[0]] 
                
                others_vms = vms[1:]
                
                start_vms(first_vm).run()
                booted = wait_vms_have_started(first_vm)
                if not booted:
                    logger.error(host + ': Unable to boot all the first VMS for %s',
                                 slugify(comb))
                    exit()
                
                sleep(30)
                
                get_uptime = TaktukRemote('cat /proc/uptime', [vm['ip']
                                    for vm in first_vm]).run()
                boot_time = {}
                for p in get_uptime.processes:
                    boot_time[p.host.address] = now - float(p.stdout.strip().split(' ')[0])
                
                get_sda_stat = TaktukRemote('cat /sys/block/vda/stat',
                                [vm['ip'] for vm in first_vm]).run()
                    
                for p in get_sda_stat.processes:
                    vms_sda_stat.append(p.stdout.strip())
                        
                get_ssh_up = TaktukRemote('grep listening /var/log/auth.log' + \
                            ' |grep 0.0.0.0|awk \'{print $1" "$2" "$3}\' | tail -n 1',
                            [vm['ip'] for vm in first_vm]).run()
                
                boot_duration = {}
                for p in get_ssh_up.processes:
                    ssh_up = time.mktime(datetime.datetime.strptime('2014 ' + \
                            p.stdout.strip(), "%Y %b %d %H:%M:%S").timetuple())
                    boot_duration[p.host.address] = str(ssh_up - boot_time[p.host.address])
    
    
                if len(others_vms) != 0:
                    now = time.time()
                    
                    start_vms(others_vms).run()
                    booted = wait_vms_have_started(others_vms)
                    if not booted:
                        logger.error(host + ': Unable to boot all the other VMS for %s',
                                     slugify(comb))
                        exit()
                        
                    sleep(30)
                    get_uptime = TaktukRemote('cat /proc/uptime', [vm['ip']
                                        for vm in others_vms]).run()
                    boot_time = {}
                    for p in get_uptime.processes:
                        boot_time[p.host.address] = now - float(p.stdout.strip().split(' ')[0])
                    
                    get_sda_stat = TaktukRemote('cat /sys/block/vda/stat',
                                [vm['ip'] for vm in others_vms]).run()
                    
                    for p in get_sda_stat.processes:
                        vms_sda_stat.append(p.stdout.strip())
                    
                    get_ssh_up = TaktukRemote('grep listening /var/log/auth.log' + \
                                ' |grep 0.0.0.0|awk \'{print $1" "$2" "$3}\' | tail -n 1',
                                [vm['ip'] for vm in others_vms]).run()
                    
                    for p in get_ssh_up.processes:
                        ssh_up = time.mktime(datetime.datetime.strptime('2014 ' + \
                                p.stdout.strip(), "%Y %b %d %H:%M:%S").timetuple())
                        boot_duration[p.host.address] = str(ssh_up - boot_time[p.host.address])
        
            
            mpstat.kill()
            
            # Get load on host
            get_load = TaktukRemote('cat /proc/loadavg',
                            [hosts[0]]).run()
            
            load_host = []
            
            for p in get_load.processes:
                load_host.append(p.stdout.strip())
            
            load_data = string.join(load_host, ",")
                         # Gathering results
            comb_dir = self.result_dir + '/' + slugify(comb) + '/'
            try:
                mkdir(comb_dir)
            except:
                logger.warning(thread_name +
                    '%s already exists, removing existing files', comb_dir)
                for f in listdir(comb_dir):
                    remove(comb_dir + f)

            logger.info(thread_name + 'Writing boot time in result files')

            text_file = open(comb_dir+"boot_time.txt", "w")
            for vm in vms:
                text_file.write(boot_duration[vm['ip']]+','+vm['cpuset']+'\n')
            text_file.write(load_data+'\n')
            text_file.close()

            text_file = open(comb_dir+"vms_sda_stat.txt", "w")
            for sda_stat in vms_sda_stat:
                text_file.write(sda_stat+'\n')
            text_file.close()
            
            get_mpstat_output = Get([hosts[0]], ['/tmp/mpstats'],
                                     local_location=comb_dir).run()
            for p in get_mpstat_output.processes:
                if not p.ok:
                    logger.error(host +
                        ': Unable to retrieve the files for combination %s',
                        slugify(comb))
                    exit()

            comb_ok = True

        finally:
            if not mpstat.ended:
                mpstat.kill()
            
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

    def cache_bench(self, vms):
        """Prepare a benchmark command with cachebench"""
        memsize = [str(27 + int(vm['n_cpu'])) for vm in vms]
        vms_ip = [vm['ip'] for vm in vms]
        vms_out = [vm['ip'] + '_' + vm['cpuset'] for vm in vms]
        stress = TaktukRemote('while true ; do ./benchs/llcbench/cachebench/cachebench ' +
                    '-m {{memsize}} -e 1 -x 2 -d 1 -b > /root/cachebench_{{vms_out}}_rmw.out ; done', vms_ip)
        for p in stress.processes:
            p.ignore_exit_code = p.nolog_exit_code = True
            
        return stress

    def kflops(self, vms):
        """Prepare a benchmark command with kflops"""
        vms_ip = [vm['ip'] for vm in vms]
        vms_out = [vm['ip'] + '_' + vm['cpuset'] for vm in vms] 

        stress = TaktukRemote('./benchs/kflops/kflops > /root/kflops_{{vms_out}}.out',
                    vms_ip)
        
        for p in stress.processes:
            p.ignore_exit_code = p.nolog_exit_code = True
        
        return stress

    def setup_hosts(self):
        """ """
        logger.info('Initialize vm5k_deployment')
        setup = vm5k_deployment(resources=self.resources,
            env_name=self.options.env_name, env_file=self.options.env_file)
        setup.fact = ActionFactory(remote_tool=TAKTUK,
                                fileput_tool=CHAINPUT,
                                fileget_tool=SCP)
        logger.info('Deploy hosts')
        setup.hosts_deployment()
        logger.info('Install packages')
        setup.packages_management(other_packages='sysstat')
        logger.info('Configure libvirt')
        setup.configure_libvirt()
        logger.info('Create backing file')
        setup._create_backing_file(disks=['/home/lpouilloux/synced/images/benchs_vms.qcow2'])

if __name__ == "__main__":
    engine = VMBootMeasurement()
    engine.start()