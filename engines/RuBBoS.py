from vm5k_engine import *
from itertools import product, repeat


class RuBBoS( vm5k_engine ):
    """ An execo engine that performs migration time measurements with
    various cpu/cell usage conditions and VM colocation. """

    def __init__(self):
        super(RuBBoS, self).__init__()
        self.env_name = 'wheezy-x64-base'
        self.stress_time = 600
	self.options_parser.add_option("--nbhttp", dest = "nb_http",
	      help = "maximum number of instances of the HTTP tier", type = "int", default = 1)
	self.options_parser.add_option("--nbapp", dest = "nb_app",
	      help = "maximum number of instances of the Application tier", type = "int", default = 1)
	self.options_parser.add_option("--nbdb", dest = "nb_db",
	      help = "maximum number of instances of the Database tier", type = "int", default = 1)
	self.options_parser.add_option("--nbhttp-maxcore", dest = "nb_http_max_core",
	      help = "maximum amount of cores per VM for HTTP tier", type = "int", default = 1)
	self.options_parser.add_option("--nbhttp-maxmem", dest = "nb_http_max_mem",
	      help = "maximum amount of memory (in GB) per VM for HTTP tier", type = "int", default = 1)
	self.options_parser.add_option("--nbapp-maxcore", dest = "nb_app_max_core",
	      help = "maximum amount of cores per VM for Application tier", type = "int", default = 1)
	self.options_parser.add_option("--nbapp-maxmem", dest = "nb_app_max_mem",
	      help = "maximum amount of memory (in GB) per VM for Application tier", type = "int", default = 1)
	self.options_parser.add_option("--nbdb-maxcore", dest = "nb_db_max_core",
	      help = "maximum amount of cores per VM for Database tier", type = "int", default = 1)
	self.options_parser.add_option("--nbdb-maxmem", dest = "nb_db_max_mem",
	      help = "maximum amount of memory (in GB) per VM for Database tier", type = "int", default = 1)
	
	
    def define_parameters(self):
        """ Create the parameters for the engine :
        - distribution of VM
        - properties of the multicore VM
        """
        cluster = self.cluster
        n_vm = 3

        self.cpu_topology = get_cpu_topology(cluster, dir = self.result_dir)

        n_core = len(self.cpu_topology[0])
        n_cell = len(self.cpu_topology)

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
	
	for i in range(self.options.nb_http+1):
	  nbHTTP.append(i)
	
	for i in range(self.options.nb_app+1):
	  nbAppServer.append(i)
	
	for i in range(self.options.nb_db+1):
	  nbDBServer.append(i)
	  
	for i in range(self.options.nb_http_max_core+1):
	  nbHTTPMaxCore.append(i)
	  
	for i in range(self.options.nb_http_max_mem+1):
	  nbHTTPMaxMem.append(i)
	  
	for i in range(self.options.nb_app_max_core+1):
	  nbAppMaxCore.append(i)
	  
	for i in range(self.options.nb_app_max_mem+1):
	  nbAppMaxMem.append(i)	
	  
	for i in range(self.options.nb_db_max_core+1):
	  nbDBMaxCore.append(i)
	  
	for i in range(self.options.nb_db_max_mem+1):
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
            logger.info(style.step('Performing combination '+slugify(comb)+' on '+host))

            logger.info(host+': Destroying existing VMS')
            destroy_vms(hosts)
            logger.info(host+': Removing existing drives')
            rm_qcow2_disks(hosts)

            logger.info(host+': Defining virtual machines ')
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
	    
	    if comb['mapping'] == 0:
	      global_index = 0
	      cpu_index = [item for sublist in self.cpu_topology for item in sublist]
	      
	      
	      # All VMs of a tier to one host
	      if (len(hosts) < 3):
		comb_ok = False
		logger.error('Not enough hosts for  %s', slugify(comb))
		exit()
	
	      ncpus = []
	      vm_ids = []
	      backingfile = []
	      mems = []
	      
	      for i in range(nb_vm_http):
		if core_vm_http > 1:
		  cpusets.append( ','.join( str(cpu_index[i]) for i in range(global_index,global_index+core_vm_http) ) )
		else:
		  index = cpu_index[global_index]
		  cpusets.append(str(index))
	        global_index += core_vm_http
		ncpus.append(core_vm_http)
		vm_ids.append("vm-http-"+str(i))
		mems.append(mem_vm_http)
		backingfile.append('/tmp/vm-http.img')
		
		
	      # Load balancer
	      index = cpu_index[global_index]
	      cpusets.append(str(index))
	      ncpus.append(1)
	      vm_ids.append("vm-http-lb")
	      mems.append(1)
	      backingfile.append('/tmp/vm-http-lb.img')
	      
	      allcpusets.append(cpusets)
	      allncpu.append(ncpus)
	      allvmids.append(vmids)
	      allbackingfile.append(backingfile)
	      allmem.appends(mems)
	      
	      ncups = []
	      vm_ids = []
	      backingfile = []
	      mems = []
	      
	      global_index = 0
	      for i in range(n_vm_app):
		if core_vm_app > 1:
		  cpusets.append( ','.join( str(cpu_index[i]) for i in range(global_index,global_index+core_vm_app) ) )
		else:
		  index = cpu_index[global_index]
		  cpusets.append(str(index))
	        global_index += core_vm_app
		ncpus.append(core_vm_app)
		vm_ids.append("vm-app-"+str(i))
		mems.append(mem_vm_app)
		backingfile.append('/tmp/vm-app.img')
		
	      # Load balancer
	      index = cpu_index[global_index]
	      cpusets.append(str(index))
	      ncpus.append(1)
	      vm_ids.append("vm-app-lb")
	      mems.append(1)
	      backingfile.append('/tmp/vm-app-lb.img')
		
	      allcpusets.append(cpusets)
	      allncpu.append(ncpus)
	      allvmids.append(vmids)
	      allbackingfile.append(backingfile)
	      allmem.appends(mems)

	      ncups = []
	      vm_ids = []
	      backingfile = []
	      mems = []
	      
	      global_index = 0
	      for i in range(n_vm_db):
		if core_vm_db > 1:
		  cpusets.append( ','.join( str(cpu_index[i]) for i in range(global_index,global_index+core_vm_db) ) )
		else:
		  index = cpu_index[global_index]
		  cpusets.append(str(index))
	        global_index += core_vm_db
	      	ncpus.append(core_vm_db)
		vm_ids.append("vm-db-"+str(i))
		mems.append(mem_vm_db)
		backingfile.append('/tmp/vm-db.img')
		
	      # Load balancer
	      index = cpu_index[global_index]
	      cpusets.append(str(index))
	      ncpus.append(1)
	      vm_ids.append("vm-db-lb")
	      mems.append(1)
	      backingfile.append('/tmp/vm-db-lb.img')
	      
	      allcpusets.append(cpusets)
      	      allncpu.append(ncpus)
      	      allvmids.append(vmids)
      	      allbackingfile.append(backingfile)
      	      allmem.appends(mems)
	    else:
	      if (len(hosts) < max(nb_vm_http,nb_vm_app,nb_vm_db):
		comb_ok = False
		logger.error('Not enough hosts for  %s', slugify(comb))
		exit()
	      
	      http_id = 0
	      app_id = 0
	      db_id = 0
	      
	      # All VMs of a tier to different host
	      for i in range(max(nb_vm_http,nb_vm_app,nb_vm_db)):
		ncpus = []
		global_index = 0
		cpu_index = [item for sublist in self.cpu_topology for item in sublist]
		cpusets = []
		
		if core_vm_http > 1:
		  cpusets.append( ','.join( str(cpu_index[i]) for i in range(global_index,global_index+core_vm_http) ) )
		else:
		  index = cpu_index[global_index]
		  cpusets.append(str(index))
	        global_index += core_vm_http
		cpusets.append(core_vm_http)
		vm_ids.append("vm-http-"+str(http_id))
		http_id+=1
		
	    	if core_vm_app > 1:
		  cpusets.append( ','.join( str(cpu_index[i]) for i in range(global_index,global_index+core_vm_app) ) )
		else:
		  index = cpu_index[global_index]
		  cpusets.append(str(index))
	        global_index += core_vm_app
	        cpusets.append(core_vm_app)
	        vm_ids.append("vm-app-"+str(app_id))
		app_id+=1
		
	        if core_vm_db > 1:
		  cpusets.append( ','.join( str(cpu_index[i]) for i in range(global_index,global_index+core_vm_db) ) )
		else:
		  index = cpu_index[global_index]
		  cpusets.append(str(index))
	        global_index += core_vm_db
	        cpusets.append(core_vm_db)
	        vm_ids.append("vm-db-"+str(db_id))
		db_id+=1
		
	        allcpusets.append(cpusets)
	      
            vms = define_vms(vm_ids, ip_mac = ip_mac,
                             n_cpu = n_cpus, cpusets = cpusets)

            for vm in vms:
                vm['host'] = hosts[0]
            logger.info(', '.join( [vm['id']+' '+ vm['ip']+' '+str(vm['n_cpu'])+'('+vm['cpuset']+')' for vm in vms]))

            # Create disks, install vms and boot by core
            logger.info(host+': Creating disks')
            create = create_disks(vms).run()
            if not create.ok:
                logger.error(host+': Unable to create the VMS disks %s', slugify(comb))
                exit()
            logger.info(host+': Installing VMS')
            install = install_vms(vms).run()
            if not install.ok:
                logger.error(host+': Unable to install the VMS  %s', slugify(comb))
                exit()
            boot_successfull = boot_vms_by_core(vms)
            if not boot_successfull:
                logger.error(host+': Unable to boot all the VMS for %s', slugify(comb))
                exit()

            # Force pinning of vm-multi vcpus
            if multi_cpu:
                cmd = '; '.join( [ 'virsh vcpupin vm-multi '+str(i)+' '+str(cpu_index[i]) for i in range(n_cpu)] )
                vcpu_pin = SshProcess(cmd, hosts[0]).run()
                if not vcpu_pin.ok:
                    logger.error(host+': Unable to pin the vcpus of vm-multi %s', slugify(comb))
                    exit()

            # Prepare virtual machines for experiments
            stress = []
            logger.info(host+': Installing kflops on vms and creating stress action')
            stress.append( self.cpu_kflops([vm for vm in vms if vm['n_cpu'] == 1 ]) )

            if multi_cpu and not self.options.cachebench:
                logger.info(host+': Installing numactl and kflops on multicore vms')
                cmd =  'export DEBIAN_MASTER=noninteractive ; apt-get update && apt-get install -y  --force-yes numactl'
                inst_numactl = Remote( cmd, [vm['ip'] for vm in vms if vm['id'] == 'vm-multi']).run()
                if not inst_numactl.ok:
                    exit()
                self.cpu_kflops([vm for vm in vms if vm['id'] == 'vm-multi' ], install_only = True)
                for multi_vm in [vm for vm in vms if vm['id'] == 'vm-multi' ]:
                    for i in range(multi_vm['n_cpu']):
                        stress.append( Remote('numactl -C '+str(i)+' ./kflops/kflops > vm_multi_'+str(cpu_index[i])+'.out ',
                                            [multi_vm['ip']] ) )

            stress_actions = ParallelActions(stress)
            for p in stress_actions.processes:
                p.ignore_exit_code = p.nolog_exit_code = True

            logger.info(host+': Starting stress !! \n%s', pformat(stress) )
            stress_actions.start()
            for p in stress_actions.processes:
                if not p.ok:
                    logger.error(host+': Unable to start the stress for combination %s', slugify(comb))
                    exit()

	    if not self.options.cachebench:
	      sleep(self.stress_time)
	      logger.info(host+': Killing stress !!')
	      stress_actions.kill()
	    else:
	      logger.info(host+': Waiting for cachebench to finish.')
	      for p in stress_actions.processes:
		while not p.ended:
		  sleep(1)

            # Gathering results
            comb_dir = self.result_dir +'/'+ slugify(comb)+'/'
            try:
                mkdir(comb_dir)
            except:
                logger.warning(host+': %s already exists, removing existing files', comb_dir)
                for f in listdir(comb_dir):
                    remove(comb_dir+f)


            logger.info(host+': Retrieving file from VMs')
            vms_ip = [vm['ip'] for vm in vms if vm['n_cpu'] == 1]
            vms_out = [vm['ip']+'_'+vm['cpuset'] for vm in vms if vm['n_cpu'] == 1]
            comb_dir = self.result_dir +'/'+ slugify(comb)+'/'
            if self.options.cachebench:
	      get_vms_output = Get(vms_ip, ['{{vms_out}}_rmw.out'], local_location = comb_dir).run()
	      for p in get_vms_output.processes:
		  if not p.ok:
		      logger.error(host+': Unable to retrieve the files for combination %s', slugify(comb))
		      exit()
		      
	      get_vms_output = Get(vms_ip, ['{{vms_out}}_memcpy.out'], local_location = comb_dir).run()
	      for p in get_vms_output.processes:
		  if not p.ok:
		      logger.error(host+': Unable to retrieve the files for combination %s', slugify(comb))
		      exit()
	    else:
	      get_vms_output = Get(vms_ip, ['{{vms_out}}.out'], local_location = comb_dir).run()
	      for p in get_vms_output.processes:
		  if not p.ok:
		      logger.error(host+': Unable to retrieve the files for combination %s', slugify(comb))
		      exit()
	      if multi_cpu:
		  for multi_vm in [vm for vm in vms if vm['id'] == 'vm-multi' ]:
		      get_multi = Get([multi_vm['ip']], ['vm_multi_'+str(cpu_index[i])+'.out ' for i in range(multi_vm['n_cpu']) ],
			  local_location = comb_dir).run()
		      for p in get_multi.processes:
			  if not p.ok:
			      logger.error(host+': Unable to retrieve the vm_multi files for combination %s', slugify(comb))
			      exit()

            comb_ok = True
        finally:

            if comb_ok:
                self.sweeper.done( comb )
                logger.info(host+': '+slugify(comb)+' has been done')
            else:
                self.sweeper.cancel( comb )
                logger.warning(host+': '+slugify(comb)+' has been canceled')
            logger.info(style.step('%s Remaining'), len(self.sweeper.get_remaining()))


    def cpu_kflops(self, vms, install_only = False):
        """Put kflops.tgz on the hosts, compile it and optionnaly prepare a TaktukRemote"""
        vms_ip = [vm['ip'] for vm in vms]

	if self.options.cachebench:
	  ChainPut(vms_ip, ['llcbench.tar.gz'] ).run()
	  TaktukRemote( 'tar -xzf llcbench.tar.gz; cd llcbench; make linux-lam; make cache-bench', vms_ip).run()
	  vms_out = [vm['ip']+'_'+vm['cpuset'] for vm in vms]
	  if not install_only:
	      return TaktukRemote('./llcbench/cachebench/cachebench -m 27 -e 1 -x 2 -d 1 -b > {{vms_out}}_rmw.out; ./llcbench/cachebench/cachebench -m 27 -e 1 -x 2 -d 1 -p > {{vms_out}}_memcpy.out', vms_ip)  
	else:
	  ChainPut(vms_ip, ['kflops.tgz'] ).run()
	  TaktukRemote( 'tar -xzf kflops.tgz; cd kflops; make', vms_ip).run()
	  vms_out = [vm['ip']+'_'+vm['cpuset'] for vm in vms]
	  if not install_only:
	      return TaktukRemote('./kflops/kflops > {{vms_out}}.out', vms_ip)


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
