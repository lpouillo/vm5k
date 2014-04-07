#!/usr/bin/env python
from vm5k.engine import *
from shutil import copy2
from os import rename


class RuBBoS(vm5k_engine_para):
    """ An execo engine that performs migration time measurements with
    various cpu/cell usage conditions and VM colocation. """

    def __init__(self):
        super(RuBBoS, self).__init__()
        self.env_name = 'wheezy-x64-base'
        self.stress_time = 600
        self.nb_client = 1
        self.n_nodes = 4

        self.options_parser.add_option("--nbhttp",
            dest="nb_http", type="int", default=1,
            help="maximum number of instances of the HTTP tier")
        self.options_parser.add_option("--nbapp",
            dest="nb_app", type="int", default=1,
            help="maximum number of instances of the Application tier")
        self.options_parser.add_option("--nbdb",
            dest="nb_db", type="int", default=1,
            help="maximum number of instances of the Database tier")
        self.options_parser.add_option("--nbhttp-maxcore",
            dest="nb_http_max_core", type="int", default=1,
            help="maximum amount of cores per VM for HTTP tier")
        self.options_parser.add_option("--nbhttp-maxmem",
            dest="nb_http_max_mem", type="int", default=1,
            help="maximum amount of memory (in GB) per VM for HTTP tier")
        self.options_parser.add_option("--nbapp-maxcore",
            dest="nb_app_max_core", type="int", default=1,
            help="maximum amount of cores per VM for Application tier")
        self.options_parser.add_option("--nbapp-maxmem",
            dest="nb_app_max_mem", type="int", default=1,
            help="maximum amount of memory (in GB) per VM for Application tier")
        self.options_parser.add_option("--nbdb-maxcore",
            dest="nb_db_max_core", type="int", default=1,
            help="maximum amount of cores per VM for Database tier")
        self.options_parser.add_option("--nbdb-maxmem",
            dest="nb_db_max_mem", type="int", default=1,
            help="maximum amount of memory (in GB) per VM for Database tier")

    def define_parameters(self):
        """ Create the parameters for the engine :
        - distribution of VM
        - properties of the multicore VM
        """
        cluster = self.cluster

        self.cpu_topology = get_cpu_topology(cluster, xpdir=self.result_dir)

        parameters = {
            'nbHTTP': range(1, self.options.nb_http + 1),
            'nbApp': range(1, self.options.nb_app + 1),
            'nbDB': range(1, self.options.nb_db + 1),
            'nbHTTPCore': range(1, self.options.nb_http_max_core + 1),
            'nbHTTPMem': range(1, self.options.nb_http_max_mem + 1),
            'nbAppCore': range(1, self.options.nb_app_max_core + 1),
            'nbAppMem': range(1, self.options.nb_app_max_mem + 1),
            'nbDBCore': range(1, self.options.nb_db_max_core + 1),
            'nbDBMem': range(1, self.options.nb_db_max_mem + 1),
            'mapping': ['all_tier_one_host', 'one_tier_one_host']}

        logger.debug(parameters)

        return parameters

    def workflow(self, comb, hosts, ip_mac):
        """ Perform a cpu stress on the VM """
        logger.debug('hosts %s', hosts)
        logger.debug('ip_mac %s', ip_mac)
        thread_name = style.Thread(slugify(comb)) + '\n'
        comb_ok = False
        try:
            logger.info(style.step('Performing combination ' + slugify(comb)))
            logger.info(thread_name)

            logger.detail('Destroying all vms on hosts')
            destroy_vms(hosts)

            n_vm = comb['nbHTTP'] + comb['nbApp'] + comb['nbDB'] + 4
            logger.info(thread_name + ': Defining %s virtual machines', n_vm)

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
            ids += ['http-' + str(i) for i in range(comb['nbHTTP'])] + \
                    ['app-' + str(i) for i in range(comb['nbApp'])] + \
                    ['db-' + str(i) for i in range(comb['nbDB'])]
            n_cpus += [comb['nbHTTPCore']] * comb['nbHTTP'] + \
                [comb['nbAppCore']] * comb['nbApp'] + \
                [comb['nbDBCore']] * comb['nbDB']
            mems += [comb['nbHTTPMem'] * 1024] * comb['nbHTTP'] + \
                [comb['nbAppMem'] * 1024] * comb['nbApp'] + \
                [comb['nbDBMem'] * 1024] * comb['nbDB']
            backing_files += ['/home/jorouzaudcornabas/VMs/vm-http.qcow2'] * comb['nbHTTP'] + \
                ['/home/jorouzaudcornabas/VMs/vm-app.qcow2'] * comb['nbApp'] + \
                ['/home/jorouzaudcornabas/VMs/vm-db.qcow2'] * comb['nbDB']

            if comb['mapping'] == 'all_tier_one_host':
                # Distributing one service on one host
                vms_hosts += [hosts[0]] * comb['nbHTTP'] + \
                            [hosts[1]] * comb['nbApp'] + \
                            [hosts[2]] * comb['nbDB']
                cpusets += [','.join([str(1 + i) for i in range((j - 1) \
                         * comb['nbHTTPCore'], j * comb['nbHTTPCore'])])
                         for j in range(1, comb['nbHTTP'] + 1)] + \
                         [','.join([str(1 + i) for i in range((j - 1) \
                         * comb['nbAppCore'], j * comb['nbAppCore'])])
                         for j in range(1, comb['nbApp'] + 1)] + \
                         [','.join([str(1 + i) for i in range((j - 1) \
                         * comb['nbDBCore'], j * comb['nbDBCore'])])
                         for j in range(1, comb['nbDB'] + 1)]
            elif comb['mapping'] == 'one_tier_one_host':
                # Distributing one service instance per host
                vms_hosts += hosts[0:comb['nbHTTP']] + \
                            hosts[0:comb['nbApp']] + \
                            hosts[0:comb['nbDB']]
                cpusets += [','.join([str(1 + i) \
                    for i in range(comb['nbHTTPCore'])])] * comb['nbHTTP'] + \
                    [','.join([str(1 + i + comb['nbHTTPCore'])
                    for i in range(comb['nbAppCore'])])] * comb['nbApp'] + \
                    [','.join([str(1 + i + comb['nbHTTPCore'] + comb['nbAppCore']) 
                    for i in range(comb['nbDBCore'])])] * comb['nbDB']
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

            # Create disks, install vms and boot by core
            logger.info(thread_name + ': Creating disks')
            create = create_disks(vms).run()
            if not create.ok:
                logger.error(thread_name + ': Unable to create the VMS disks')
                exit()

            logger.info(thread_name + ': Installing VMS')
            install = install_vms(vms).run()
            if not install.ok:
                logger.error(thread_name + ': Unable to install the VMS')
                exit()

            logger.info(thread_name + ': Booting VMs')
            boot_successfull = boot_vms_list(vms)
            if not boot_successfull:
                logger.error(thread_name + ': Unable to boot all the VMS')
                exit()

#             # Force pinning of vm-multi vcpus
#             for vm in vms:
#                 if vm['n_cpu'] > 1:
#                     cmd = '; '.join(['virsh vcpupin ' + vm['id'] + ' ' + str(i) + 
#                         ' ' + str(global_cpusets[vm['id']][i]) for i in range(vm['n_cpu'])])
#                     vcpu_pin = SshProcess(cmd, vm['host']).run()
#                     if not vcpu_pin.ok:
#                         logger.error(thread_name + 
#                             ': Unable to pin the vcpus of vm-multi %s', slugify(comb))
#                         exit()
# 
#             # Contextualize the VM services
#             tmp_dir = self.result_dir + '/tmp/'
#             try:
#                 mkdir(tmp_dir)
#             except:
#                 logger.warning('Temporary directory for %s already exists, removing existing files', tmp_dir)
#                 for f in listdir(tmp_dir):
#                     remove(tmp_dir + f)
# 
#             for vm in vms:
#                 if "vm-http-lb" == vm['id']:
#                     generate_http_proxy("conf_template/default_http_lb", tmp_dir + "default_http_lb", vm_per_tier["vm-http"])
#                     # Upload file
#                     Put(vm['ip'], [tmp_dir + "default_http_lb"]).run()
#                     SshProcess('mv /root/default_http_lb /etc/apache2/site-available/', vm['ip']).run()
#                 elif "vm-app-lb" == vm['id']:
#                     generate_tomcat_proxy("conf_template/default_tomcat_lb", tmp_dir + "default_tomcat_lb", vm_per_tier["vm-app"])
#                     # Upload file
#                     Put(vm['ip'], [tmp_dir + "default_tomcat_lb"]).run()
#                     SshProcess('mv /root/default_tomcat_lb /etc/apache2/site-available/', vm['ip']).run()
#                 elif "vm-db-lb" == vm['id']:
#                     copy2("conf_template/haproxy.cfg", tmp_dir + "haproxy.cfg")
#                     f = open(tmp_dir + "haproxy.cfg", 'a')
#                     for vm_db in vm_per_tier["vm-db"]:
#                         f.write("server " + vm_db['id'] + " " + vm_db['ip'] + ":3306 check")
#                     f.close()
#                     Put(vm['ip'], [tmp_dir + "haproxy.cfg"] ).run()
#                     SshProcess('mv /root/haproxy.cfg /etc/', vm['ip']).run()
#                 elif "vm-http" in vm['id']:
#                     grep("conf_template/default_http", tmp_dir + "default_http", 'HTTP_LOADBALANCER', vm_per_tier["vm-app-lb"]['ip'])
#                     Put(vm['ip'], [tmp_dir + "default_http"] ).run()
#                     SshProcess('mv /root/default_http /etc/apache2/site-available/', vm['ip']).run()
#                 elif "vm-app" in vm['id']:
#                     grep("conf_template/mysql.properties", tmp_dir + "mysql.properties", 'MYSQL_LOADBALANCER', vm_per_tier["vm-db-lb"]['ip'])
#                     Put(vm['ip'], [tmp_dir + "mysql.properties"] ).run()
#                     SshProcess('mv /root/mysql.properties /var/www/', vm['ip']).run()
# 
#             # Restarting services to take into account new configuration
#             # 1. MySQL LB
#             for vm in vm_per_tier["vm-db-lb"]:
#                 SshProcess('haproxy -f /etc/haproxy/haproxy.cfg', vm['ip']).run()
# 
#             # 2. Tomcat
#             for vm in vm_per_tier["vm-app"]:
#                 SshProcess('/etc/init.d/tomcat6 restart', vm['ip']).run()
# 
#             # 3. Tomcat LB
#             for vm in vm_per_tier["vm-app-lb"]:
#                 SshProcess('/etc/init.d/apache2 restart', vm['ip']).run()
# 
#             # 4. HTTP
#             for vm in vm_per_tier["vm-http"]:
#                 SshProcess('/etc/init.d/apache2 restart', vm['ip']).run()
# 
#             # 5. HTTP LB
#             for vm in vm_per_tier["vm-http-lb"]:
#                 SshProcess('/etc/init.d/apache2 restart', vm['ip']).run()
# 
#             # Launch Client VM(s)
#             vm_ids_client = []
#             backing_files = []
# 
#             for i in range(1, self.nb_client + 1):
#                 vm_ids_client.append("vm-client")
#                 backing_files.append("/tmp/vm-client.img")

#             logger.info(host + ': Installing VMS')
#             install = install_vms(vms_client).run()
#             if not install.ok:
#                 logger.error(host + ': Unable to install the VMS  %s', slugify(comb))
#                 exit()
# 
#             boot_successfull = boot_vms_by_core(vms_client)
#             if not boot_successfull:
#                 logger.error(host + ': Unable to boot all the VMS for %s', slugify(comb))
#                 exit()
# 
#             # Generate benchmark configuration file
#             grep("conf_template/rubbos.properties", tmp_dir + "rubbos.properties.1", 
#                  'HTTP_APACHE_SERVER', vm_per_tier["vm-http-lb"]['ip'])
#             grep(tmp_dir + "rubbos.properties.1", tmp_dir + "rubbos.properties.2", 
#                  'TOMCAT_SERVER', vm_per_tier["vm-app-lb"]['ip'])
#             grep(tmp_dir + "rubbos.properties.2", tmp_dir + "rubbos.properties", 
#                  'MARIADB_SERVER', vm_per_tier["vm-db-lb"]['ip'])
# 
#             # Upload benchmark configuration file
#             vms_ip = [vm['ip'] for vm in vms_client]
#             ChainPut(vms_ip, [ tmp_dir + "rubbos.properties" ] ).run()
# 
#             # Launch benchmark
#             client_benchmark = []
#             client_benchmark.append(TaktukRemote('cd /root/RUBBoS/Client/ &&  java -Xmx256m -Xms128m -server -classpath . edu.rice.rubbos.client.ClientEmulator', 
#                                                      vms_ip))
# 
#             # Sleep for 10 minutes and kill the benchmark
#             stress_actions = ParallelActions(client_benchmark)
#             for p in stress_actions.processes:
#                 p.ignore_exit_code = p.nolog_exit_code = True
# 
#             logger.info(host + ': Starting RUBBoS benchmark !! \n%s', pformat(client_benchmark) )
#             stress_actions.start()
#             for p in stress_actions.processes:
#                 if not p.ok:
#                     logger.error(host+': Unable to start the RUBBoS benchmark for combination %s', slugify(comb))
#                     exit()
# 
#             sleep(self.stress_time)
#             logger.info(host + ': Killing RUBBoS benchmark !!')
#             stress_actions.kill()
# 
#             # Gathering results (to rewrite)
#             comb_dir = self.result_dir + '/' + slugify(comb) + '/'
#             try:
#                 mkdir(comb_dir)
#             except:
#                 logger.warning(host + ': %s already exists, removing existing files', comb_dir)
#                 for f in listdir(comb_dir):
#                     remove(comb_dir + f)
# 
#             logger.info(host + ': Retrieving file from VMs')
#             comb_dir = self.result_dir + '/' + slugify(comb) + '/'
# 
#             # Get log files
#             for vm in vms_client:
#                 # Directory /root/RUBBoS/bench sur VM Client
#                 get = Get(vm['ip'], ['/root/RUBBoS/bench/'], local_location = comb_dir).run()
# 
#                 for p in get.processes:
#                     if not p.ok:
#                         logger.error(host+': Unable to retrieve the vm_multi files for combination %s', slugify(comb))
#                         exit()
# 
#                 rename(comb_dir+'bench/', comb_dir+'bench_client_'+vm['ip'])
# 
#             get_log_files(vm_per_tier["vm-http-lb"], '/var/log/apache2/access.log',
#                           '.http_lb_', host, comb_dir)
#             get_log_files(vm_per_tier["vm-http-lb"], '/var/log/apache2/error.log',
#                           '.http_lb_', host, comb_dir)
# 
#             get_log_files(vm_per_tier["vm-http"], '/var/log/apache2/access.log',
#                           '.http_', host, comb_dir)
#             get_log_files(vm_per_tier["vm-http"], '/var/log/apache2/error.log',
#                           '.http_', host, comb_dir)
# 
#             get_log_files(vm_per_tier["vm-app-lb"], '/var/log/apache2/access.log',
#                           '.app_lb_', host, comb_dir)
#             get_log_files(vm_per_tier["vm-app-lb"], '/var/log/apache2/error.log',
#                           '.app_lb_', host, comb_dir)
# 
#             get_log_files(vm_per_tier["vm-app"], '/var/lib/tomcat6/logs/rubbos.log',
#                           '.app_', host, comb_dir)
            comb_ok = True
        finally:

            if comb_ok:
                self.sweeper.done(comb)
                logger.info(thread_name + ': ' + slugify(comb) + ' has been done')
            else:
                self.sweeper.cancel(comb)
                logger.warning(thread_name + ': ' + slugify(comb) + \
                               ' has been canceled')
            logger.info(style.step('%s Remaining'),
                        len(self.sweeper.get_remaining()))

    def comb_nvm(self, comb):
        """Calculate the number of virtual machines in the combination"""
        n_vm = int(comb['nbHTTP']) + int(comb['nbApp']) + int(comb['nbDB']) + 4
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
        logger.info('Deploy hosts')
        setup.hosts_deployment()
        logger.info('Install packages')
        setup.packages_management()
        logger.info('Configure libvirt')
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
            logger.info('Disks %s are already present', pformat(disks))
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
    logger.info('Starting VMS ' + ', '.join([vm['id']
                                for vm in sorted(vms_to_boot)]))
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


def generate_http_proxy(infilepath, outfilepath, vms):
    infile = open(infilepath)
    outfile = open(outfilepath)

    cpt_line = 0
    for line in infile:
        if cpt_line == 7:
            for vm in vms:
                outfile.write("        BalancerMember http://" + vm['ip'])
        else:
            cpt_line += 1
            outfile.write(line)

    infile.close()
    outfile.close()


def generate_tomcat_proxy(infilepath, outfilepath, vms):
    infile = open(infilepath)
    outfile = open(outfilepath)

    cpt_line = 0
    for line in infile:
        if cpt_line == 7:
            for vm in vms:
                outfile.write("        BalancerMember http://" + vm['ip'] + \
                              ":8080/rubbos/")
        else:
            cpt_line += 1
            outfile.write(line)

    infile.close()
    outfile.close()


if __name__ == "__main__":
    engine = RuBBoS()
    engine.start()
