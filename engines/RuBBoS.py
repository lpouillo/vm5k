#!/usr/bin/env python
from vm5k.engine import *
from shutil import copy2
from os import rename, mkdir, listdir, remove, fdopen, rmdir
from tempfile import mkstemp


class RuBBoS(vm5k_engine_para):
    """ An execo engine that performs migration time measurements with
    various cpu/cell usage conditions and VM colocation. """

    def __init__(self):
        super(RuBBoS, self).__init__()
        self.env_name = 'wheezy-x64-base'
        self.nb_client = 1
        self.n_nodes = 4

        self.options_parser.add_option("--stress-time",
            dest="stress_time", type="int", default=600,
            help="maximum number of instances of the HTTP tier")
        self.options_parser.add_option("--http",
            dest="http", type="int", default=1,
            help="maximum number of instances of the HTTP tier")
        self.options_parser.add_option("--app",
            dest="app", type="int", default=1,
            help="maximum number of instances of the Application tier")
        self.options_parser.add_option("--db",
            dest="db", type="int", default=1,
            help="maximum number of instances of the Database tier")
        self.options_parser.add_option("--http-maxcore",
            dest="http_max_core", type="int", default=1,
            help="maximum amount of cores per VM for HTTP tier")
        self.options_parser.add_option("--http-maxmem",
            dest="http_max_mem", type="int", default=1,
            help="maximum amount of memory (in GB) per VM for HTTP tier")
        self.options_parser.add_option("--app-maxcore",
            dest="app_max_core", type="int", default=1,
            help="maximum amount of cores per VM for Application tier")
        self.options_parser.add_option("--app-maxmem",
            dest="app_max_mem", type="int", default=1,
            help="maximum amount of memory (in GB) per VM for Application tier")
        self.options_parser.add_option("--db-maxcore",
            dest="db_max_core", type="int", default=1,
            help="maximum amount of cores per VM for Database tier")
        self.options_parser.add_option("--db-maxmem",
            dest="db_max_mem", type="int", default=1,
            help="maximum amount of memory (in GB) per VM for Database tier")

    def define_parameters(self):
        """ Create the parameters for the engine :
        - distribution of VM
        - properties of the multicore VM
        """
        cluster = self.cluster

        self.cpu_topology = get_cpu_topology(cluster, xpdir=self.result_dir)

        parameters = {
            'HTTP': range(1, self.options.http + 1),
            'App': range(1, self.options.app + 1),
            'DB': range(1, self.options.db + 1),
            'HTTPCore': range(1, self.options.http_max_core + 1),
            'HTTPMem': range(1, self.options.http_max_mem + 1),
            'AppCore': range(1, self.options.app_max_core + 1),
            'AppMem': range(1, self.options.app_max_mem + 1),
            'DBCore': range(1, self.options.db_max_core + 1),
            'DBMem': range(1, self.options.db_max_mem + 1),
            'mapping': ['all_tier_one_host', 'one_tier_one_host']}

        logger.debug(parameters)

        return parameters

    def workflow(self, comb, hosts, ip_mac):
        """ Perform a cpu stress on the VM """
        logger.debug('hosts %s', hosts)
        logger.debug('ip_mac %s', ip_mac)

        thread_name = style.Thread(' '.join(sorted(map(lambda x: x.split('.')[0], hosts))) \
                                    + '\n')
        comb_ok = False
        try:
            logger.info(style.step('Performing combination ' + slugify(comb)))
            logger.info(thread_name)

            logger.detail('Destroying all vms on hosts')
            destroy_vms(hosts)

            n_vm = comb['HTTP'] + comb['App'] + comb['DB'] + 4
            logger.info(thread_name + 'Defining %s virtual machines', n_vm)

            # Defining load balancers and client virtual machines
            ids = ['lb-http', 'lb-app', 'lb-db', 'client']
            vms_hosts = [hosts[0], hosts[1], hosts[2], hosts[3]]
            n_cpus = [1] * 4
            cpusets = ['0'] * 4
            mems = [512] * 4
            disks = 12
            backing_files = ['/home/jorouzaudcornabas/VMs/vm-http-lb.qcow2',
                           '/home/jorouzaudcornabas/VMs/vm-app-lb.qcow2',
                           '/home/jorouzaudcornabas/VMs/vm-db-lb.qcow2',
                           '/home/jorouzaudcornabas/VMs/vm-client.qcow2']

            # Defining parameters independant from mapping
            ids += ['http-' + str(i) for i in range(comb['HTTP'])] + \
                    ['app-' + str(i) for i in range(comb['App'])] + \
                    ['db-' + str(i) for i in range(comb['DB'])]
            n_cpus += [comb['HTTPCore']] * comb['HTTP'] + \
                [comb['AppCore']] * comb['App'] + \
                [comb['DBCore']] * comb['DB']
            mems += [comb['HTTPMem'] * 1024] * comb['HTTP'] + \
                [comb['AppMem'] * 1024] * comb['App'] + \
                [comb['DBMem'] * 1024] * comb['DB']
            backing_files += ['/home/jorouzaudcornabas/VMs/vm-http.qcow2'] * comb['HTTP'] + \
                ['/home/jorouzaudcornabas/VMs/vm-app.qcow2'] * comb['App'] + \
                ['/home/jorouzaudcornabas/VMs/vm-db.qcow2'] * comb['DB']

            if comb['mapping'] == 'all_tier_one_host':
                # Distributing one service on one host
                vms_hosts += [hosts[0]] * comb['HTTP'] + \
                            [hosts[1]] * comb['App'] + \
                            [hosts[2]] * comb['DB']
                cpusets += [','.join([str(1 + i) for i in range((j - 1) \
                         * comb['HTTPCore'], j * comb['HTTPCore'])])
                         for j in range(1, comb['HTTP'] + 1)] + \
                         [','.join([str(1 + i) for i in range((j - 1) \
                         * comb['AppCore'], j * comb['AppCore'])])
                         for j in range(1, comb['App'] + 1)] + \
                         [','.join([str(1 + i) for i in range((j - 1) \
                         * comb['DBCore'], j * comb['DBCore'])])
                         for j in range(1, comb['DB'] + 1)]
            elif comb['mapping'] == 'one_tier_one_host':
                # Distributing one service instance per host
                vms_hosts += hosts[0:comb['HTTP']] + \
                            hosts[0:comb['App']] + \
                            hosts[0:comb['DB']]
                cpusets += [','.join([str(1 + i) \
                    for i in range(comb['HTTPCore'])])] * comb['HTTP'] + \
                    [','.join([str(1 + i + comb['HTTPCore'])
                    for i in range(comb['AppCore'])])] * comb['App'] + \
                    [','.join([str(1 + i + comb['HTTPCore'] + comb['AppCore'])
                    for i in range(comb['DBCore'])])] * comb['DB']
            logger.trace('ids %s', pformat(ids))
            logger.trace('ip_mac %s', pformat(ip_mac))
            logger.trace('vms_hosts %s', pformat(vms_hosts))
            logger.trace('n_cpus %s', pformat(n_cpus))
            logger.trace('cpusets %s', pformat(cpusets))
            logger.trace('backing_file %s', pformat(backing_files))
            vms = define_vms(ids,
                        ip_mac=ip_mac,
                        host=vms_hosts,
                        n_cpu=n_cpus,
                        cpusets=cpusets,
                        mem=mems,
                        hdd=disks,
                        backing_file=backing_files)
            logger.detail('VMS %s ', pformat(vms))
            # Create disks, install vms and boot by core
            logger.info(thread_name + 'Creating disks')
            create = create_disks(vms).run()
            if not create.ok:
                logger.error(thread_name + ': Unable to create the VMS disks')
                exit()

            logger.info(thread_name + 'Installing VMS')
            install = install_vms(vms).run()
            if not install.ok:
                logger.error(thread_name + ': Unable to install the VMS')
                exit()

            logger.info(thread_name + 'Booting VMs')
            boot_successfull = boot_vms_list(vms)
            if not boot_successfull:
                logger.error(thread_name + ': Unable to boot all the VMS')
                exit()

            # Force pinning of vm-multi vcpus
            for vm in vms:
                cmd = '; '.join(['virsh vcpupin ' + vm['id'] + ' ' + str(i) + \
                    ' ' + str(vm['cpuset'].split(',')[i]) 
                    for i in range(vm['n_cpu'])])
                vcpu_pin = SshProcess(cmd, vm['host']).run()
                if not vcpu_pin.ok:
                    logger.error(thread_name + \
                        ': Unable to pin the vcpus of vm-multi %s', slugify(comb))
                    exit()
            # Creating service configuration
            logger.info('Configuring services on VMs')
            services = {
                'lb-http':
                    {'func': generate_http_proxy,
                     'template': 'default_http_lb',
                     'remote_file': '/etc/apache2/sites-available/default',
                     'launch_cmd': '/etc/init.d/apache2 restart',
                     'member_vms': filter(lambda x: 'http-' in x['id'], vms),
                     'log_files': ['/var/log/apache2/access.log',
                                   '/var/log/apache2/error.log']},
                'lb-app':
                    {'func': generate_tomcat_proxy,
                     'template': 'default_tomcat_lb',
                     'remote_file': '/etc/apache2/sites-available/default',
                     'launch_cmd': '/etc/init.d/apache2 restart',
                     'member_vms': filter(lambda x: 'app-' in x['id'], vms),
                     'log_files': ['/var/log/apache2/access.log',
                                   '/var/log/apache2/error.log']},
                'lb-db':
                    {'func': generate_db_proxy,
                     'template': 'haproxy.cfg',
                     'remote_file': '/etc/haproxy/haproxy.cfg',
                     'launch_cmd': 'haproxy -f /etc/haproxy/haproxy.cfg',
                     'member_vms': filter(lambda x: 'db-' in x['id'], vms),
                     'log_files': None},
                'http-':
                    {'func': generate_http,
                     'template': 'default_http',
                     'remote_file': '/etc/apache2/sites-available/default',
                     'launch_cmd': '/etc/init.d/apache2 restart',
                     'member_vms': filter(lambda x: 'lb-app' in x['id'], vms),
                     'log_files': ['/var/log/apache2/access.log',
                                   '/var/log/apache2/error.log']},
                'app-':
                    {'func': generate_app,
                     'template': 'mysql.properties',
                     'remote_file': '/var/www/mysql.properties',
                     'launch_cmd': '/etc/init.d/tomcat6 restart',
                     'member_vms': filter(lambda x: 'lb-db' in x['id'], vms),
                     'log_files': ['/var/lib/tomcat6/logs/rubbos.log']},
                'db-':
                    {'func': None,
                     'template': None,
                     'remote_file': None,
                     'launch_cmd': None,
                     'member_vms': None,
                     'log_files': None},
                'client':
                    {'func': generate_client,
                     'template': 'rubbos.properties',
                     'remote_file': '/root/RUBBoS/Client/rubbos.properties',
                     'launch_cmd': 'cd /root/RUBBoS/Client/ && ' + \
                     'java -Xmx256m -Xms128m -server -classpath . ' + \
                     'edu.rice.rubbos.client.ClientEmulator',
                     'member_vms': filter(lambda x: 'lb-' in x['id'], vms),
                     'log_files': ['/root/RUBBoS/Client/bench/']}
                    }
            for service, conf in services.iteritems():
                if conf['template']:
                    service_vms = map(lambda y: y['ip'],
                        filter(lambda x: service in x['id'], vms))
                    logger.detail('service: %s %s', ','.join(service_vms),
                                ','.join([vm['id'] for vm in conf['member_vms']]))
                    f_template = open('conf_template/' + conf['template'])
                    fd, outfile = mkstemp(dir='/tmp/', prefix=service + '_')
                    f = fdopen(fd, 'w')
                    conf['func'](f, f_template, conf['member_vms'])
                    f_template.close()
                    f.close()
                    logger.detail('conf generated in ' + outfile)
                    put_file = Put(service_vms, [outfile]).run()
                    if not put_file.ok:
                        exit()
                    Remote('cp ' + outfile.split('/')[-1] + ' ' + conf['remote_file'],
                        service_vms).run()

            # Starting services sequentially
            for service in ['lb-db', 'app-', 'lb-app', 'http-', 'lb-http']:
                conf = services[service]
                launch = Remote(conf['launch_cmd'], map(lambda y: y['ip'],
                           filter(lambda x: service in x['id'], vms))).run()

            # Launching client
            rubbos_stress = SshProcess(services['client']['launch_cmd'],
                    map(lambda y: y['ip'], filter(lambda x: 'client' in x['id'],
                                                  vms))[0])
            rubbos_stress.ignore_exit_code = rubbos_stress.nolog_exit_code = True
            logger.info('Starting stress for %s', format_duration(self.options.stress_time))
            rubbos_stress.start()

            sleep(self.options.stress_time)
            rubbos_stress.kill()
            # Gathering results
            comb_dir = self.result_dir + '/' + slugify(comb) + '/'
            try:
                mkdir(comb_dir)
            except:
                logger.warning(thread_name + '%s already exists, ' + \
                               'removing existing files', comb_dir)
                for f in listdir(comb_dir):
                    try:
                        remove(comb_dir + f)
                    except:
                        rmdir(comb_dir + f)

            for vm in vms:
                vm_result_dir = comb_dir + '/' + vm['id'] + '/'
                try:
                    mkdir(vm_result_dir)
                except:
                    logger.warning(thread_name + '%s already exists, ' + \
                               'removing existing files', vm_result_dir)
                    for f in listdir(vm_result_dir):
                        remove(vm_result_dir + f)

            for service, conf in services.iteritems():
                if conf['log_files']:
                    ids = map(lambda y: y['id'],
                           filter(lambda x: service in x['id'], vms))
                    result_dir = comb_dir + '{{ids}}/'
                    logger.detail('Retrieving log files %s in %s', conf['log_files'],
                                  result_dir)
                    Get(map(lambda y: y['ip'], filter(lambda x: service in x['id'], vms)), 
                        conf['log_files'], local_location=result_dir).run()

            fileVM = comb_dir + 'vm.txt'
            with open(fileVM, 'w') as fp:
                for p in vms:
                    fp.write("%s\n" % p)

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

    def comb_nvm(self, comb):
        """Calculate the number of virtual machines in the combination"""
        n_vm = int(comb['HTTP']) + int(comb['App']) + int(comb['DB']) + 4
        return n_vm

    def setup_hosts(self):
        """Launch the vm5k_deployment """
        logger.info('Initialize vm5k_deployment')
        setup = vm5k_deployment(resources=self.resources,
                    env_name=self.options.env_name,
                    env_file=self.options.env_file)
        setup.fact = ActionFactory(remote_tool=TAKTUK,
                                fileput_tool=CHAINPUT,
                                fileget_tool=SCP)
        setup.hosts_deployment()
        setup.packages_management()
        setup.configure_libvirt()

        disks = ['vm-app-lb.qcow2', 'vm-client.qcow2', 'vm-db.qcow2',
            'vm-http.qcow2', 'vm-app.qcow2', 'vm-db-lb.qcow2',
            'vm-http-lb.qcow2']
        check_disks = Remote("ls /tmp/|grep qcow2|grep vm|wc|awk '{print $1}'",
                             setup.hosts)
        for p in check_disks.processes:
            p.shell = True
        check_disks.run()
        disks_present = True
        for p in check_disks.processes:
            if int(p.stdout.strip()) != 7:
                disks_present = False
                break
        if disks_present:
            logger.info('Disks %s are already present', ' '.join(disks))
        else:
            logger.info('Create backing file')
            setup._create_backing_file(disks=['/home/jorouzaudcornabas/VMs/'
                + disk for disk in disks])


def get_log_files(vms, logfile, suffix, host, comb_dir):
    for vm in vms:
        get = Get(vm['ip'], [logfile],
                  local_location=comb_dir).run()

        for p in get.processes:
            if not p.ok:
                logger.error(host +
                    ': Unable to retrieve the vm_multi files for ' +
                    'combination %s', comb_dir.split('/')[-1])
                exit()

        rename(comb_dir + logfile.split('/')[-1], comb_dir +
               logfile.split('/')[-1] + suffix + vm['ip'])


def boot_vms_list(vms_to_boot):
    logger.detail(', '.join([vm['id'] for vm in sorted(vms_to_boot)]))
    start_vms(vms_to_boot).run()
    booted = wait_vms_have_started(vms_to_boot)

    if not booted:
        return False

    booted_vms = len(vms_to_boot)
    logger.info(style.emph(str(booted_vms)))
    return True


def grep(infilepath, outfilepath, oldstring, newstring):
    infile = open(infilepath)
    outfile = open(outfilepath)

    for line in infile:
        line = line.replace(oldstring, newstring)
        outfile.write(line)
    infile.close()
    outfile.close()


def generate_http_proxy(f, f_template, vms):
    cpt_line = 1
    for line in f_template:
        if cpt_line == 7:
            for vm in vms:
                f.write("        BalancerMember http://" + vm['ip'] + "\n")
        else:
            f.write(line)
        cpt_line += 1


def generate_tomcat_proxy(f, f_template, vms):
    cpt_line = 1
    for line in f_template:
        if cpt_line == 7:
            for vm in vms:
                f.write("        BalancerMember http://" + vm['ip'] + \
                              ":8080/rubbos/\n")
        else:
            f.write(line)
        cpt_line += 1


def generate_db_proxy(f, f_template, vms):
    for line in f_template:
        f.write(line)
    for vm in vms:
        f.write("        server " + vm['id'] + " " + vm['ip'] + ":3306 check")


def generate_http(f, f_template, vms):
    """ """
    for line in f_template:
        line = line.replace('APP_LOADBALANCER', vms[0]['ip'])
        f.write(line)

def generate_app(f, f_template, vms):
    """ """
    for line in f_template:
        line = line.replace('MYSQL_LOADBALANCER', vms[0]['ip'])
        f.write(line)

def generate_client(f, f_template, vms):
    """ """
    for line in f_template:
        line = line.replace('HTTP_APACHE_SERVER',
                            filter(lambda x: 'lb-http' in x['id'],
                                   vms)[0]['ip'])
        line = line.replace('TOMCAT_SERVER',
                            filter(lambda x: 'lb-app' in x['id'],
                                   vms)[0]['ip'])
        line = line.replace('MARIADB_SERVER',
                            filter(lambda x: 'lb-db' in x['id'], vms)[0]['ip'])
        f.write(line)


if __name__ == "__main__":
    engine = RuBBoS()
    engine.start()
