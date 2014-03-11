from vm5k_engine import *
from shutil import copy2
from os import rename

class RuBBoS(vm5k_engine):
    """ An execo engine that performs migration time measurements with
    various cpu/cell usage conditions and VM colocation. """

    def __init__(self):
        super(RuBBoS, self).__init__()
        self.env_name = 'wheezy-x64-base'
        self.stress_time = 600
        self.nb_client = 1
        
        self.options_parser.add_option("--nbhttp", dest="nb_http",
	      help="maximum number of instances of the HTTP tier", type="int", default=1)
        self.options_parser.add_option("--nbapp", dest="nb_app",
	      help="maximum number of instances of the Application tier", type="int", default=1)
        self.options_parser.add_option("--nbdb", dest="nb_db",
	      help="maximum number of instances of the Database tier", type="int", default=1)
        self.options_parser.add_option("--nbhttp-maxcore", dest="nb_http_max_core",
	      help="maximum amount of cores per VM for HTTP tier", type="int", default=1)
        self.options_parser.add_option("--nbhttp-maxmem", dest="nb_http_max_mem",
	      help="maximum amount of memory (in GB) per VM for HTTP tier", type="int", default=1)
        self.options_parser.add_option("--nbapp-maxcore", dest="nb_app_max_core",
	      help="maximum amount of cores per VM for Application tier", type="int", default=1)
        self.options_parser.add_option("--nbapp-maxmem", dest="nb_app_max_mem",
	      help="maximum amount of memory (in GB) per VM for Application tier", type="int", default=1)
        self.options_parser.add_option("--nbdb-maxcore", dest="nb_db_max_core",
	      help="maximum amount of cores per VM for Database tier", type="int", default=1)
        self.options_parser.add_option("--nbdb-maxmem", dest="nb_db_max_mem",
	      help="maximum amount of memory (in GB) per VM for Database tier", type="int", default=1)
        
        self.options.n_nodes = 4
        
    def define_parameters(self):
        """ Create the parameters for the engine :
        - distribution of VM
        - properties of the multicore VM
        """
        cluster = self.cluster

        self.cpu_topology = get_cpu_topology(cluster, dir=self.result_dir)

        nbHTTP = []
        nbAppServer = []
        nbDBServer = []
        nbHTTPMaxCore = []
        nbHTTPMaxMem = []
        nbAppMaxCore = []
        nbAppMaxMem = []
        nbDBMaxCore = []
        nbDBMaxMem = []
        mapping = []
        
        for i in range(1, self.options.nb_http + 1):
            nbHTTP.append(i)

        for i in range(1, self.options.nb_app + 1):
            nbAppServer.append(i)
        
        for i in range(1, self.options.nb_db + 1):
            nbDBServer.append(i)

        for i in range(1, self.options.nb_http_max_core + 1):
            nbHTTPMaxCore.append(i)
        
        for i in range(1, self.options.nb_http_max_mem + 1):
            nbHTTPMaxMem.append(i)

        for i in range(1, self.options.nb_app_max_core + 1):
            nbAppMaxCore.append(i)

        for i in range(1, self.options.nb_app_max_mem + 1):
            nbAppMaxMem.append(i)	

        for i in range(1, self.options.nb_db_max_core + 1):
            nbDBMaxCore.append(i)
        
        for i in range(1, self.options.nb_db_max_mem + 1):
            nbDBMaxMem.append(i)

        # 2 mapping policies
        for i in range(2):
            mapping.append(i)

        parameters = {'nbHTTP': nbHTTP, 'nbAppServer': nbAppServer, 'nbDBServer' : nbDBServer, 'nbHTTPMaxCore' : nbHTTPMaxCore, 'nbHTTPMaxMem' : nbHTTPMaxMem,
		      'nbAppMaxCore' : nbAppMaxCore, 'nbAppMaxMem' : nbAppMaxMem, 'nbDBMaxCore' : nbDBMaxCore, 'nbDBMaxMem' : nbDBMaxMem,
		      'mapping' : mapping}
        logger.debug(parameters)

        return parameters

    def workflow(self, comb, hosts, ip_mac):
        """ Perform a cpu stress on the VM """
        host = style.Thread(hosts[0].address.split('.')[0])
        comb_ok = False
        try:
            logger.info(style.step('Performing combination ' + slugify(comb) + ' on ' + host))
            logger.info(host + ': Destroying existing VMS')
            
            destroy_vms(hosts)
            logger.info(host + ': Removing existing drives')
            rm_qcow2_disks(hosts)
            
            logger.info(host + ': Defining virtual machines ')
            n_vm_http = comb['nbHTTP']
            n_vm_app = comb['nbApp']
            n_vm_db = comb['nbDB']
               
            core_vm_http = comb['nbHTTPMaxCore']
            mem_vm_http = comb['nbHTTPMaxMem']
            core_vm_app = comb['nbAppMaxCore']
            mem_vm_app = comb['nbAppMaxMem']
            core_vm_db = comb['nbDBMaxCore']
            mem_vm_db = comb['nbDBMaxMem']
            
            allcpusets = []
            allncpu = []
            allvmids = []
            allbackingfile = []
            allmem = []
            global_cpusets = {}
                
            # All VMs of a tier to one host
            if comb['mapping'] == 0:
                global_index = 0
                cpu_index = [item for sublist in self.cpu_topology for item in sublist]

                # 3-tier application needs 3 hosts + 1 host for the client
                if len(hosts) < 4:
                    comb_ok = False
                    logger.error('Not enough hosts for  %s', slugify(comb))
                    exit()
            
                # HTTP Server(s) + Load balancer
                ncpus = []
                vm_ids = []
                backingfile = []
                mems = []
                cpusets = []
                ###################################################
                for i in range(n_vm_http):
                    global_cpusets["vm-http-" + str(i)] = []
                    if core_vm_http > 1:
                        cpusets.append(','.join(str(cpu_index[i]) for i in range(global_index, global_index + core_vm_http)))
                        for i in range(global_index, global_index + core_vm_http):
                            global_cpusets["vm-http-" + str(i)].append(str(cpu_index[i]))
                    else:
                        index = cpu_index[global_index]
                        cpusets.append(str(index))
                        global_cpusets["vm-http-" + str(i)].append(str(index))
                        
                    global_index += core_vm_http
                    ncpus.append(core_vm_http)
                    vm_ids.append("vm-http-" + str(i))
                    mems.append(mem_vm_http * 1024)
                    backingfile.append('/tmp/vm-http.img')


                # HTTP Load balancer
                index = cpu_index[global_index]
                cpusets.append(str(index))
                ncpus.append(1)
                vm_ids.append("vm-http-lb")
                global_cpusets["vm-http-lb"] = []
                global_cpusets["vm-http-lb"].append(str(index))
                mems.append(512)
                backingfile.append('/tmp/vm-http-lb.img')
                
                allcpusets.append(cpusets)
                allncpu.append(ncpus)
                allvmids.append(vm_ids)
                allbackingfile.append(backingfile)
                allmem.appends(mems)
                
                # Application Server(s) + Load balancer
                ncpus = []
                vm_ids = []
                backingfile = []
                mems = []
                cpusets = []
                global_index = 0
            
                for i in range(n_vm_app):
                    global_cpusets["vm-app-" + str(i)] = []
                    if core_vm_app > 1:
                        cpusets.append(','.join(str(cpu_index[i]) for i in range(global_index, global_index + core_vm_app)))
                        for i in range(global_index, global_index + core_vm_app):
                            global_cpusets["vm-app-" + str(i)].append(str(cpu_index[i]))
                    else:
                        index = cpu_index[global_index]
                        cpusets.append(str(index))
                        global_cpusets["vm-app-" + str(i)].append(str(index))

                    global_index += core_vm_app
                    ncpus.append(core_vm_app)
                    vm_ids.append("vm-app-" + str(i))
                    mems.append(mem_vm_app * 1024)
                    backingfile.append('/tmp/vm-app.img')
                    
                # Load balancer
                index = cpu_index[global_index]
                cpusets.append(str(index))
                ncpus.append(1)
                vm_ids.append("vm-app-lb")
                global_cpusets["vm-app-lb"] = []
                global_cpusets["vm-app-lb"].append(str(index))
                mems.append(512)
                backingfile.append('/tmp/vm-app-lb.img')

                allcpusets.append(cpusets)
                allncpu.append(ncpus)
                allvmids.append(vm_ids)
                allbackingfile.append(backingfile)
                allmem.appends(mems)

                # Database Server(s) + Load balancer
                ncpus = []
                vm_ids = []
                backingfile = []
                mems = []
                cpusets = []
                global_index = 0

                for i in range(n_vm_db):
                    global_cpusets["vm-db-" + str(i)] = []
                    
                    if core_vm_db > 1:
                        cpusets.append(','.join(str(cpu_index[i]) for i in range(global_index, global_index + core_vm_db)))
                        for i in range(global_index, global_index + core_vm_db):
                            global_cpusets["vm-db-" + str(i)].append(str(cpu_index[i]))
                    else:
                        index = cpu_index[global_index]
                        cpusets.append(str(index))
                        global_cpusets["vm-app-" + str(i)].append(str(index))
                    
                    global_index += core_vm_db
                    ncpus.append(core_vm_db)
                    vm_ids.append("vm-db-" + str(i))
                    mems.append(mem_vm_db * 1024)
                    backingfile.append('/tmp/vm-db.img')
                    
                # Load balancer
                index = cpu_index[global_index]
                cpusets.append(str(index))
                ncpus.append(1)
                vm_ids.append("vm-db-lb")
                global_cpusets["vm-db-lb"] = []
                global_cpusets["vm-db-lb"].append(str(index))
                mems.append(512)
                backingfile.append('/tmp/vm-db-lb.img')
                    
                allcpusets.append(cpusets)
                allncpu.append(ncpus)
                allvmids.append(vm_ids)
                allbackingfile.append(backingfile)
                allmem.appends(mems)
            else:
                # All VMs of a tier to different host + 1 host for the client
                if len(hosts) < ( max(n_vm_http, n_vm_app, n_vm_db) + 1):
                    comb_ok = False
                    logger.error('Not enough hosts for  %s', slugify(comb))
                    exit()
    
                http_id = 0
                app_id = 0
                db_id = 0
    
                firstHost = True
 
                # All VMs of a tier to different host
                for i in range(max(n_vm_http, n_vm_app, n_vm_db)):
                    ncpus = []
                    vm_ids = []
                    backingfile = []
                    mems = []
                    cpusets = []
                    
                    global_index = 0
                    cpu_index = [item for sublist in self.cpu_topology for item in sublist]
                    
                    if http_id < n_vm_http:
                        global_cpusets["vm-http-" + str(i)] = []
                        if core_vm_http > 1:
                            cpusets.append(','.join(str(cpu_index[i]) for i in range(global_index, global_index + core_vm_http)))
                            for i in range(global_index, global_index + core_vm_http):
                                global_cpusets["vm-http-" + str(i)].append(str(cpu_index[i]))
                        else:
                            index = cpu_index[global_index]
                            cpusets.append(str(index))
                            global_cpusets["vm-http-" + str(i)].append(str(index))
                        
                        global_index += core_vm_http
                        cpusets.append(core_vm_http)
                        vm_ids.append("vm-http-" + str(http_id))
                        mems.append(mem_vm_http * 1024)
                        backingfile.append('/tmp/vm-http.img')
                        ncpus.append(core_vm_http)
                        http_id += 1
                    
                    if app_id < n_vm_app:
                        global_cpusets["vm-app-" + str(i)] = []
                        if core_vm_app > 1:
                            cpusets.append(','.join(str(cpu_index[i]) for i in range(global_index, global_index + core_vm_app)))
                            for i in range(global_index, global_index + core_vm_app):
                                global_cpusets["vm-app-" + str(i)].append(str(cpu_index[i]))
                        else:
                            index = cpu_index[global_index]
                            cpusets.append(str(index))
                            global_cpusets["vm-app-" + str(i)].append(str(index))
                            
                        global_index += core_vm_app
                        cpusets.append(core_vm_app)
                        vm_ids.append("vm-app-" + str(app_id))
                        mems.append(mem_vm_app * 1024)
                        backingfile.append('/tmp/vm-app.img')
                        ncpus.append(core_vm_app)
                        app_id += 1
                    
                    if db_id < n_vm_db:
                        global_cpusets["vm-db-" + str(i)] = []
                        if core_vm_db > 1:
                            cpusets.append(','.join(str(cpu_index[i]) for i in range(global_index, global_index + core_vm_db)))
                            for i in range(global_index, global_index + core_vm_db):
                                global_cpusets["vm-db-" + str(i)].append(str(cpu_index[i]))
                        else:
                            index = cpu_index[global_index]
                            cpusets.append(str(index))
                            global_cpusets["vm-db-" + str(i)].append(str(index))
                        
                        global_index += core_vm_db
                        cpusets.append(core_vm_db)
                        vm_ids.append("vm-db-" + str(db_id))
                        mems.append(mem_vm_db * 1024)
                        backingfile.append('/tmp/vm-db.img')
                        ncpus.append(core_vm_db)
                        db_id += 1

                    if firstHost:
                        firstHost = False
                        
                        # Load balancer
                        index = cpu_index[global_index]
                        cpusets.append(str(index))
                        ncpus.append(1)
                        vm_ids.append("vm-http-lb")
                        mems.append(512)
                        backingfile.append('/tmp/vm-http-lb.img')
                        global_cpusets["vm-http-lb"] = []
                        global_cpusets["vm-http-lb"].append(str(index))
                        
                        # Load balancer
                        index = cpu_index[global_index]
                        cpusets.append(str(index))
                        ncpus.append(1)
                        vm_ids.append("vm-app-lb")
                        mems.append(512)
                        backingfile.append('/tmp/vm-app-lb.img')
                        global_cpusets["vm-app-lb"] = []
                        global_cpusets["vm-app-lb"].append(str(index))
                        
                        # Load balancer
                        index = cpu_index[global_index]
                        cpusets.append(str(index))
                        ncpus.append(1)
                        vm_ids.append("vm-db-lb")
                        mems.append(512)
                        backingfile.append('/tmp/vm-db-lb.img')
                        global_cpusets["vm-db-lb"] = []
                        global_cpusets["vm-db-lb"].append(str(index))

                    allcpusets.append(cpusets)
                    allncpu.append(ncpus)
                    allvmids.append(vm_ids)
                    allbackingfile.append(backingfile)
                    allmem.appends(mems)
                    
            # For each host, call define_vms
            available_ip_mac = ip_mac
            vms = []

            for i in range(len(allcpusets)):
                cpusets = allcpusets[i]
                vm_ids = allvmids[i]
                n_cpus = allncpu[i]
                mems = allmem[i]
                backingfiles = allbackingfile[i]
                
                local_n_vm = len(vm_ids) + 1
                
                used_ip_mac = available_ip_mac[0:local_n_vm]
                available_ip_mac = available_ip_mac[local_n_vm:]
                
                local_vms = define_vms(vm_ids, ip_mac=used_ip_mac,
                             n_cpu=n_cpus, cpusets=cpusets,
                             mem=allmem, backing_file=backingfiles)
                
                for vm in local_vms:
                    vm['host'] = hosts[i]
                    
                vms.extend(local_vms)
                
                logger.info(', '.join([vm['id'] + ' ' + vm['ip'] + ' ' + str(vm['n_cpu']) + '(' + vm['cpuset'] + ')' for vm in vms]))
                
                
            vm_per_tier = {}
            vm_per_tier["vm-http"] = []
            vm_per_tier["vm-app"] = []
            vm_per_tier["vm-db"] = []
                
            for vm in vms:
                if "vm-http-lb" == vm['id']:
                    vm_per_tier["vm-http-lb"] = vm
                elif "vm-app-lb" == vm['id']:
                    vm_per_tier["vm-app-lb"] = vm
                elif "vm-db-lb" == vm['id']:
                    vm_per_tier["vm-db-lb"] = vm
                elif "vm-http" in vm['id']:
                    vm_per_tier["vm-http"].append(vm)
                elif "vm-app" in vm['id']:
                    vm_per_tier["vm-app"].append(vm)
                elif "vm-db" in vm['id']:
                    vm_per_tier["vm-db"].append(vm)
                
            # Create disks, install vms and boot by core
            logger.info(host + ': Creating disks')
            create = create_disks(vms).run()
            if not create.ok:
                logger.error(host + ': Unable to create the VMS disks %s', slugify(comb))
                exit()
                    
            logger.info(host + ': Installing VMS')
            install = install_vms(vms).run()
            if not install.ok:
                logger.error(host + ': Unable to install the VMS  %s', slugify(comb))
                exit()
                
            boot_successfull = boot_vms_by_tier(vm_per_tier)
            if not boot_successfull:
                logger.error(host + ': Unable to boot all the VMS for %s', slugify(comb))
                exit()
                    
            # Force pinning of vm-multi vcpus
            for vm in vms:
                if vm['n_cpu'] > 1:
                    cmd = '; '.join([ 'virsh vcpupin ' + vm['id'] + ' ' + str(i) + ' ' + str(global_cpusets[vm['id']][i]) for i in range(vm['n_cpu'])])
                    vcpu_pin = SshProcess(cmd, vm['host']).run()
                    if not vcpu_pin.ok:
                        logger.error(host + ': Unable to pin the vcpus of vm-multi %s', slugify(comb))
                        exit()
                
            # Contextualize the VM services
            tmp_dir = self.result_dir + '/tmp/'
            try:
                mkdir(tmp_dir)
            except:
                logger.warning('Temporary directory for %s already exists, removing existing files', tmp_dir)
                for f in listdir(tmp_dir):
                    remove(tmp_dir + f)
                
            for vm in vms:
                if "vm-http-lb" == vm['id']:
                    generate_http_proxy("conf_template/default_http_lb", tmp_dir + "default_http_lb", vm_per_tier["vm-http"])
                    # Upload file
                    Put(vm['ip'], [tmp_dir + "default_http_lb"]).run()
                    SshProcess('mv /root/default_http_lb /etc/apache2/site-available/', vm['ip']).run()
                elif "vm-app-lb" == vm['id']:
                    generate_tomcat_proxy("conf_template/default_tomcat_lb", tmp_dir + "default_tomcat_lb", vm_per_tier["vm-app"])
                    # Upload file
                    Put(vm['ip'], [tmp_dir + "default_tomcat_lb"]).run()
                    SshProcess('mv /root/default_tomcat_lb /etc/apache2/site-available/', vm['ip']).run()
                elif "vm-db-lb" == vm['id']:
                    copy2("conf_template/haproxy.cfg", tmp_dir + "haproxy.cfg")
                    f = open(tmp_dir + "haproxy.cfg", 'a')
                    for vm_db in vm_per_tier["vm-db"]:
                        f.write("server " + vm_db['id'] + " " + vm_db['ip'] + ":3306 check")
                    f.close()
                    Put(vm['ip'], [tmp_dir + "haproxy.cfg"] ).run()
                    SshProcess('mv /root/haproxy.cfg /etc/', vm['ip']).run()
                elif "vm-http" in vm['id']:
                    grep("conf_template/default_http", tmp_dir + "default_http", 'HTTP_LOADBALANCER', vm_per_tier["vm-app-lb"]['ip'])
                    Put(vm['ip'], [tmp_dir + "default_http"] ).run()
                    SshProcess('mv /root/default_http /etc/apache2/site-available/', vm['ip']).run()
                elif "vm-app" in vm['id']:
                    grep("conf_template/mysql.properties", tmp_dir + "mysql.properties", 'MYSQL_LOADBALANCER', vm_per_tier["vm-db-lb"]['ip'])
                    Put(vm['ip'], [tmp_dir + "mysql.properties"] ).run()
                    SshProcess('mv /root/mysql.properties /var/www/', vm['ip']).run()
                        
            # Restarting services to take into account new configuration
            # 1. MySQL LB    
            for vm in vm_per_tier["vm-db-lb"]:
                SshProcess('haproxy -f /etc/haproxy/haproxy.cfg', vm['ip']).run()
            
            # 2. Tomcat
            for vm in vm_per_tier["vm-app"]:
                SshProcess('/etc/init.d/tomcat6 restart', vm['ip']).run()
                
            # 3. Tomcat LB
            for vm in vm_per_tier["vm-app-lb"]:
                SshProcess('/etc/init.d/apache2 restart', vm['ip']).run()
                
            # 4. HTTP
            for vm in vm_per_tier["vm-http"]:
                SshProcess('/etc/init.d/apache2 restart', vm['ip']).run()
                    
            # 5. HTTP LB
            for vm in vm_per_tier["vm-http-lb"]:
                SshProcess('/etc/init.d/apache2 restart', vm['ip']).run()
            
            
            # Launch Client VM(s)
            vm_ids_client = []
            backing_files = []
            
            for i in range(1,self.nb_client+1):
                vm_ids_client.append("vm-client")
                backing_files.append("/tmp/vm-client.img")
                
            vms_client = define_vms(vm_ids_client, ip_mac = available_ip_mac, backing_file = backing_files)
            
            for vm in vms_client:
                vm['host'] = hosts[3]
                
            
            logger.info(host+': Installing VMS')
            install = install_vms(vms_client).run()
            if not install.ok:
                logger.error(host+': Unable to install the VMS  %s', slugify(comb))
                exit()
                
            boot_successfull = boot_vms_by_core(vms_client)
            if not boot_successfull:
                logger.error(host+': Unable to boot all the VMS for %s', slugify(comb))
                exit()
                
                
            # Generate benchmark configuration file
            grep("conf_template/rubbos.properties", tmp_dir + "rubbos.properties.1", 'HTTP_APACHE_SERVER', 
                 vm_per_tier["vm-http-lb"]['ip'])
            grep(tmp_dir + "rubbos.properties.1", tmp_dir + "rubbos.properties.2", 'TOMCAT_SERVER', 
                 vm_per_tier["vm-app-lb"]['ip'])
            grep(tmp_dir + "rubbos.properties.2", tmp_dir + "rubbos.properties", 'MARIADB_SERVER', 
                 vm_per_tier["vm-db-lb"]['ip'])
            
            # Upload benchmark configuration file
            vms_ip = [vm['ip'] for vm in vms_client]
            ChainPut(vms_ip, [ tmp_dir + "rubbos.properties" ] ).run()
            
            # Launch benchmark
            client_benchmark = []
            client_benchmark.append(TaktukRemote('cd /root/RUBBoS/Client/ &&  java -Xmx256m -Xms128m -server -classpath . edu.rice.rubbos.client.ClientEmulator', 
                                                     vms_ip))
                
            # Sleep for 10 minutes and kill the benchmark
            stress_actions = ParallelActions(client_benchmark)
            for p in stress_actions.processes:
                p.ignore_exit_code = p.nolog_exit_code = True

            logger.info(host+': Starting RUBBoS benchmark !! \n%s', pformat(client_benchmark) )
            stress_actions.start()
            for p in stress_actions.processes:
                if not p.ok:
                    logger.error(host+': Unable to start the RUBBoS benchmark for combination %s', slugify(comb))
                    exit()

            
            sleep(self.stress_time)
            logger.info(host+': Killing RUBBoS benchmark !!')
            stress_actions.kill()
            
            # Gathering results (to rewrite)
            comb_dir = self.result_dir + '/' + slugify(comb) + '/'
            try:
                mkdir(comb_dir)
            except:
                logger.warning(host + ': %s already exists, removing existing files', comb_dir)
                for f in listdir(comb_dir):
                    remove(comb_dir + f)


            logger.info(host + ': Retrieving file from VMs')
            comb_dir = self.result_dir + '/' + slugify(comb) + '/'
      
            # Get log files
            for vm in vms_client:
                # Directory /root/RUBBoS/bench sur VM Client
                get = Get(vm['ip'], [ '/root/RUBBoS/bench/' ], local_location = comb_dir).run()
                
                for p in get.processes:
                    if not p.ok:
                        logger.error(host+': Unable to retrieve the vm_multi files for combination %s', slugify(comb))
                        exit()
                
                rename(comb_dir+'bench/', comb_dir+'bench_client_'+vm['ip'])
                
            for vm in vm_per_tier["vm-http-lb"]:
                # File /var/log/apache2/access.log on VM http-lb
                get = Get(vm['ip'], [ '/var/log/apache2/access.log' ], local_location = comb_dir).run()
                
                for p in get.processes:
                    if not p.ok:
                        logger.error(host+': Unable to retrieve the vm_multi files for combination %s', slugify(comb))
                        exit()
                        
                rename(comb_dir+'access.log', comb_dir+'access.log.http_lb_'+vm['ip'])
                        
                # File /var/log/apache2/error.log on VM http-lb
                get = Get(vm['ip'], [ '/var/log/apache2/error.log' ], local_location = comb_dir).run()
                
                for p in get.processes:
                    if not p.ok:
                        logger.error(host+': Unable to retrieve the vm_multi files for combination %s', slugify(comb))
                        exit()
                
                rename(comb_dir+'error.log', comb_dir+'error.log.http_lb_'+vm['ip'])
                        
            for vm in vm_per_tier["vm-http"]:
                # File /var/log/apache2/access.log on VM http
                get = Get(vm['ip'], [ '/var/log/apache2/access.log' ], local_location = comb_dir).run()
                
                for p in get.processes:
                    if not p.ok:
                        logger.error(host+': Unable to retrieve the vm_multi files for combination %s', slugify(comb))
                        exit()
                
                rename(comb_dir+'access.log', comb_dir+'access.log.http_'+vm['ip'])
                
                # File /var/log/apache2/error.log on VM http
                get = Get(vm['ip'], [ '/var/log/apache2/error.log' ], local_location = comb_dir).run()
                
                for p in get.processes:
                    if not p.ok:
                        logger.error(host+': Unable to retrieve the vm_multi files for combination %s', slugify(comb))
                        exit()
                        
                rename(comb_dir+'error.log', comb_dir+'error.log.http_lb_'+vm['ip'])
                
                        
            for vm in vm_per_tier["vm-app-lb"]:
                # File /var/log/apache2/access.log on VM tomcat-lb
                get = Get(vm['ip'], [ '/var/log/apache2/access.log' ], local_location = comb_dir).run()
                
                for p in get.processes:
                    if not p.ok:
                        logger.error(host+': Unable to retrieve the vm_multi files for combination %s', slugify(comb))
                        exit()
                        
                rename(comb_dir+'access.log', comb_dir+'access.log.app_lb_'+vm['ip'])
                
                # File /var/log/apache2/error.log on VM tomcat-lb
                get = Get(vm['ip'], [ '/var/log/apache2/error.log' ], local_location = comb_dir).run()
                
                for p in get.processes:
                    if not p.ok:
                        logger.error(host+': Unable to retrieve the vm_multi files for combination %s', slugify(comb))
                        exit()
                        
                rename(comb_dir+'error.log', comb_dir+'error.log.app_lb_'+vm['ip'])
                
                        
            for vm in vm_per_tier["vm-app"]:
                # File /var/lib/tomcat6/logs/rubbos.log on tomcat   
                get = Get(vm['ip'], [ '/var/lib/tomcat6/logs/rubbos.log' ], local_location = comb_dir).run()
                
                for p in get.processes:
                    if not p.ok:
                        logger.error(host+': Unable to retrieve the vm_multi files for combination %s', slugify(comb))
                        exit()
                
                rename(comb_dir+'rubbos.log', comb_dir+'rubbos.log.app_'+vm['ip'])
                
                        
            comb_ok = True
        finally:

            if comb_ok:
                self.sweeper.done(comb)
                logger.info(host + ': ' + slugify(comb) + ' has been done')
            else:
                self.sweeper.cancel(comb)
                logger.warning(host + ': ' + slugify(comb) + ' has been canceled')
            logger.info(style.step('%s Remaining'), len(self.sweeper.get_remaining()))


    def comb_nvm(self, comb):
        """Calculate the number of virtual machines in the combination"""
        n_vm = sum(int(comb['nbHTTP']) + int(comb['nbApp']) + int(comb['nbDB']) + 3)
        return n_vm
    
    def setup_hosts(self):
        """ """
        logger.info('Initialize vm5k_deployment')
        setup = vm5k_deployment(resources = self.resources, env_name = self.options.env_name, env_file = self.options.env_file)
        setup.fact = ActionFactory  (remote_tool = TAKTUK,
                                fileput_tool = CHAINPUT,
                                fileget_tool = SCP)
        logger.info('Deploy hosts')
        setup.hosts_deployment()
        logger.info('Install packages')
        setup.packages_management()
        logger.info('Configure libvirt')
        setup.configure_libvirt()
        logger.info('Create backing file')
        setup._create_backing_file(from_disk = '/home/jrouzaud/VMs/vm-http-lb.qcow2', 
                                   to_disk = '/tmp/vm-http-lb.img')
        
        setup._create_backing_file(from_disk = '/home/jrouzaud/VMs/vm-client.qcow2', 
                                   to_disk = '/tmp/vm-client.img')
        
        
        setup._create_backing_file(from_disk = '/home/jrouzaud/VMs/vm-http.qcow2', 
                                   to_disk = '/tmp/vm-http.img')
        
        
        setup._create_backing_file(from_disk = '/home/jrouzaud/VMs/vm-app.qcow2', 
                                   to_disk = '/tmp/vm-app.img')
        
        
        setup._create_backing_file(from_disk = '/home/jrouzaud/VMs/vm-app-lb.qcow2', 
                                   to_disk = '/tmp/vm-app-lb.img')
        
        
        setup._create_backing_file(from_disk = '/home/jrouzaud/VMs/vm-db.qcow2', 
                                   to_disk = '/tmp/vm-db.img')
        
        
        setup._create_backing_file(from_disk = '/home/jrouzaud/VMs/vm-db-lb.qcow2', 
                                   to_disk = '/tmp/vm-db-lb.img')
      
def boot_vms_by_tier(vms):
    if boot_vms_list(vms["vm-db"]):
        if boot_vms_list(vms["vm-db-lb"]):
            if boot_vms_list(vms["vm-app"]):
                if boot_vms_list(vms["vm-app-lb"]):
                    if boot_vms_list(vms["vm-http"]):
                        if boot_vms_list(vms["vm-http-lb"]):
                            return True
    return False

def boot_vms_list(vms_to_boot):
    logger.info('Starting VMS ' + ', '.join([vm['id'] for vm in sorted(vms_to_boot)]))
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
                outfile.write("        BalancerMember http://" + vm['ip'] + ":8080/rubbos/")
        else:
            cpt_line += 1
            outfile.write(line)
    
    infile.close()
    outfile.close()
