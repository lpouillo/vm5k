#!/usr/bin/env python
from vm5k.engine import *
#from itertools import product, repeat
import string
import random
import os
from vm5k.utils import get_hosts_jobs, reboot_hosts
from execo import logger as exlog


class VMBootMeasurement(vm5k_engine_para):
    def __init__(self):
        super(VMBootMeasurement, self).__init__()
        self.n_nodes = 1
        self.options_parser.add_option("--vm", dest="n_vm",
                                       type="int", default=1,
                                       help="maximum number of VMs")
        self.options_parser.add_option("--cpu", dest="n_cpu",
                                       type="int", default=1,
                                       help="maximum number of CPUs")
        self.options_parser.add_option("--mem", dest="n_mem",
                                       type="int", default=1,
                                       help="maximum number of memory")
        self.options_parser.add_option("--host",
                                       dest="host",
                                       help="force host choice")

    def define_parameters(self):
        """Define the parameters you want to explore"""
        parameters = {
            'n_vm':           range(1, self.options.n_vm + 1),
            'n_co_vms':       range(0, 3),
            'n_mem':          range(1, self.options.n_mem + 1),
            'n_cpu':          range(1, self.options.n_cpu + 1),
            'cpu_sharing':    [True, False],
            'cpu_policy':     ['one_core', 'one_by_core'],
            'image_policy':   ['one', 'one_per_vm'],
            'boot_policy':    ['all_at_once', 'one_then_others'],
            'load_injector':  ['cpu', 'memory', 'mixed'],
            'iteration':      range(1, 3)}

        logger.info('Exploring the following parameters \n%s',
                    pformat(parameters))

        return parameters

    def comb_nvm(self, comb):
        """Calculate the number of virtual machines in the combination,
        required to attribute a number of IP/MAC for a parameter combination
        """
        return comb['n_vm'] * (1 + comb['n_co_vms'])

    def workflow(self, comb, hosts, ip_mac):
        """Perform a boot measurements on the VM """
        host = hosts[0]
        logger.debug('hosts %s', host)
        logger.debug('ip_mac %s', ip_mac)

        thread_name = style.Thread(host.split('.')[0]) + ': '

        comb_ok = False

        try:
            logger.info(thread_name)
            logger.info(style.step(' Performing combination') + '\n' +
                        slugify(comb))

            logger.info(thread_name + 'Destroying all vms on hosts')
            destroy_vms(hosts, undefine=True)

            self.umount_mount_tmp(host)

            vms = self.create_vms(comb, host, ip_mac)
            logger.info('VMs are ready to be started')

            xpvms = filter(lambda v: 'covm' not in v['id'], vms)
            covms = filter(lambda v: 'covm' in v['id'], vms)

            # Starting collocated VMs
            if len(covms) > 0:
                logger.info('Starting covms \n%s',
                            "\n".join([vm['id'] + ': ' + vm['ip']
                                      for vm in covms]))
                start_vms(covms).run()
                booted = wait_vms_have_started(covms)
                if not booted:
                    logger.error('Unable to boot all the coVMS for %s',
                                     slugify(comb))
                    exit()

                # Inject load in covms
                if comb['load_injector'] == 'cpu':
                    injector = self.kflops(covms).start()
                elif comb['load_injector'] == 'mem':
                    injector = self.cache_bench(covms).start()
                else:
                    mem = []
                    cpu = []
                    for v in covms:
                        random.choice((mem, cpu)).append(v)
                        injector = []
                        injector.append(self.kflops(cpu).start())
                        injector.append(self.cache_bench(mem).start())
                logger.info('Sleep 10 seconds to wait for stress to reach its maximum')
                sleep(10)
                logger.info('covms are up and run stress %s',
                            comb['load_injector'])

            # Boot XP vms
            logger.info('Booting xpvms %s\n%s', comb['boot_policy'],
                        "\n".join([vm['id'] + ': ' + vm['ip']
                                   for vm in xpvms]))
            if comb['boot_policy'] == 'all_at_once':
                start_vms(xpvms)
                booted = wait_vms_have_started(xpvms)
            else:
                first_vm = [xpvms[0]]
                start_vms(first_vm)
                booted = wait_vms_have_started(first_vm)
                if len(xpvms) > 1:
                    other_vms = xpvms[1:]
                    start_vms(other_vms)
                    booted = wait_vms_have_started(other_vms)

            # Retrieves measurements on XPVms
            boot_duration = self.get_boot_duration(xpvms)
            if not self.save_results(host, comb, xpvms, boot_duration):
                exit()

            comb_ok = True

        finally:
            if comb_ok:
                self.sweeper.done(comb)
                logger.info(thread_name + slugify(comb) +
                            ' has been done')
            else:
                self.sweeper.cancel(comb)
                logger.warning(thread_name + slugify(comb) +
                               ' has been canceled')
            logger.info(style.step('%s Remaining'),
                        len(self.sweeper.get_remaining()))

    def cache_bench(self, vms):
        """Prepare a benchmark command with cachebench"""
        memsize = [str(27 + int(vm['n_cpu'])) for vm in vms]
        vms_ip = [vm['ip'] for vm in vms]
        vms_out = [vm['ip'] + '_' + vm['cpuset'] for vm in vms]
        stress = TaktukRemote('while true ; do ./benchs/llcbench/cachebench/cachebench ' +
                              '-m {{memsize}} -e 1 -x 2 -d 1 -b > /root/cachebench_{{vms_out}}_rmw.out ; done',
                              vms_ip)

        return stress

    def get_boot_duration(self, vms):
        """Boot duration is defined as the time f """
        boot_duration = {}
        cmd = 'grep "link up" /var/log/messages |grep eth0| tail -n 1 ' + \
            '| awk \'{print $7}\''
        get_boottime = TaktukRemote(cmd, [vm['ip'] for vm in vms]).run()
        for p in get_boottime.processes:
            boot_duration[p.host.address] = p.stdout.strip()[0:-1]
        return boot_duration

    def save_results(self, host, comb, vms, boot_duration):
        # Gathering results
        comb_dir = self.result_dir + '/' + slugify(comb) + '/'
        if not os.path.exists(comb_dir):
            os.mkdir(comb_dir)
        else:
            logger.warning('%s already exists, removing '
                           'existing files', comb_dir)
            for f in listdir(comb_dir):
                remove(comb_dir + f)

        logger.info('Writing boot time in result files')
        print boot_duration
        text_file = open(comb_dir + "boot_time.txt", "w")
        for vm in vms:
            text_file.write(boot_duration[vm['ip']] + ',' + vm['cpuset']
                            + '\n')
        text_file.close()

        return True

    def create_vms(self, comb, host, ip_mac):
        """ """
        # set the ID of the virtual machine
        vms_ids = ['vm-' + str(i) for i in range(comb['n_vm'])] + \
            ['covm-' + str(i) for i in range(comb['n_co_vms'] * comb['n_vm'])]
        # set the disk
        backing_file = '/home/lpouilloux/synced/images/benchs_vms.qcow2'
        real_file = comb['image_policy'] == 'one_per_vm'
        # set the CPU
        n_cpu = comb['n_cpu']
        if comb['cpu_policy'] == 'one_by_core':
            cpusets = [','.join(str(i) for j in range(comb['n_cpu']))
                       for i in range(comb['n_vm'])]
            if comb['cpu_sharing']:
                cpusets += [','.join(str(i) for j in range(comb['n_cpu']))
                            for i in range(comb['n_vm'])] * comb['n_co_vms']
            else:
                cpusets += [str(comb['n_vm'] + k)
                            for k in range(comb['n_co_vms'] * comb['n_vm'])]
        else:
            cpusets = [str(0)] * comb['n_vm']
            if comb['cpu_sharing']:
                cpusets += [str(0)] * comb['n_co_vms'] * comb['n_vm']
            else:
                cpusets += [str(1)] * comb['n_co_vms'] * comb['n_vm']
        # set the memory
        mem = comb['n_mem'] * 1024

        # define all the virtual machines
        vms = define_vms(vms_ids,
                         host=host,
                         ip_mac=ip_mac,
                         n_cpu=n_cpu,
                         cpusets=cpusets,
                         mem=mem,
                         backing_file=backing_file,
                         real_file=real_file)

        logger.info('Creating disks')
        create = create_disks(vms).run()
        if not create.ok:
            logger.error('Unable to create the VMS disks for %s ',
                         slugify(comb))
            exit()
        logger.info('Installing VMS')
        install = install_vms(vms).run()
        if not install.ok:
            logger.error('Unable to install the VMS for %s ',
                         slugify(comb))
            exit()

        return vms

    def umount_mount_tmp(self, host, retry=10):
        umount = SshProcess('sync; echo 3 > /proc/sys/vm/drop_caches; '
                                'umount /tmp; sleep 5; mount /tmp',
                                host, shell=True).run()

        while (not umount.finished_ok) and (retry > 0):
            lsof = SshProcess('lsof /tmp; virsh list', host,
                              ignore_exit_code=True,
                              nolog_exit_code=True).run()
            logger.info(host + ' : lsof /tmp : %s', lsof.stdout.strip())
            sleep(5)
            umount.reset()
            umount.run()
            retry -= 1

        if not umount.finished_ok:
            logger.error('Failed to unmount /tmp for %s', host)
            logger.error('mount/umount error : %s %s',
                         umount.stdout.strip(),
                         umount.stderr.strip())
            exit()

    def kflops(self, vms):
        """Prepare a benchmark command with kflops"""
        vms_ip = [vm['ip'] for vm in vms]
        vms_out = [vm['ip'] + '_' + vm['cpuset'] for vm in vms] 

        stress = TaktukRemote('./benchs/kflops/kflops > /root/kflops_{{vms_out}}.out',
                              vms_ip)

        return stress

    def make_reservation(self):
        """ """
        jobs_specs = get_hosts_jobs([self.options.host], self.options.walltime)

        sub = jobs_specs[0][0]
        tmp = str(sub.resources).replace('\\', '')
        sub.name = self.__class__.__name__
        sub.resources = 'slash_22=4+' + tmp.replace('"', '')
        sub.walltime = self.options.walltime
        sub.additional_options = '-t deploy'
        startdate = sub.reservation_date
        self.oar_job_id, self.frontend = oarsub(jobs_specs)[0]
        logger.info('Startdate: %s, host: %s', format_date(startdate),
                    self.options.host)

    def setup_hosts(self):
        """ """
        disks = ['/home/lpouilloux/synced/images/benchs_vms.qcow2']
        logger.info('Initialize vm5k_deployment')
        setup = vm5k_deployment(resources=self.resources,
                                env_name=self.options.env_name,
                                env_file=self.options.env_file)
        setup.fact = ActionFactory(remote_tool=TAKTUK,
                                   fileput_tool=CHAINPUT,
                                   fileget_tool=SCP)
        logger.info('Deploy hosts')
        setup.hosts_deployment()
        setup._start_disk_copy(disks)
        logger.info('Install packages')
        setup.packages_management(other_packages='sysstat')
        logger.info('Configure libvirt')
        setup.configure_libvirt()
        logger.info('Rebooting hosts')
        reboot_hosts(setup.hosts)
        logger.info('Create backing file')
        setup._create_backing_file(disks=disks)


if __name__ == "__main__":
    engine = VMBootMeasurement()
    engine.start()
