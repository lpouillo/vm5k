*******************************************
vm5k: automatic virtual machines deployment
*******************************************

The vm5k script provides a tool to deploy a large number of virtual machines 
on the Grid'5000 platform. It provides several options to customize your 
environnements and topology.

Workflow
--------

* define a deployment **topology** on Grid'5000:

  * distributed virtual machines using a template and a list of clusters/sites
  * or from a given xml file (see example below)
  
* manage the **reservation**:

  * find the next window available for the deployment
  * or use an existing reservation

* install the **hosts**

  * deployment of a kadeploy environment name/file
  * upgrade the hosts and configure libvirt
  * create the backing file for the virtual machine

* configure the **network**

  * determine the parameters from the oar/oargridjob
  * generate dnsmasq configuration

* deploy the **virtual machines**

  * create the qcow2 disks on the hosts
  * perform installation with virt-install
  * start the virtual machines


.. image:: _static/vm5k_workflow.png 


Basic Usage
-----------

The basic usage is to create a certain number of virtual machines on Grid'5000.
To deploy 100 VM on *wheezy-x64-base* hosts and with the *wheezy-x64-base.qcow2* KVM image
on any Grid5000 cluster with hardware virtualization, for 2 hours::

  vm5k --n_vm 100 -w 2:00:00

This will automatically find free nodes on Grid'5000 that can sustains your virtual
machines, perform the reservation and deploy hosts and VMs automatically.


Customize the environments
^^^^^^^^^^^^^^^^^^^^^^^^^^

To perform your experiments, you may want to use specific environments to test the effect of 
various configurations (distribution version, kernel parameters, vm disk, ...). You can 
choose the hosts operating system with::

 vm5k --n_vm 50 --walltime 2:00:00 --env_name wheezy-x64-prod
 vm5k --n_vm 50 --walltime 2:00:00 --env_name user:env_name
 vm5k --n_vm 50 --walltime 2:00:00 --env_file path/to/your/env_file

You may also want to use your virtual machines disk::

 vm5k --n_vm 50 --walltime 2:00:00 --vm_backing_file path_to_my_qcow2_file_on_g5k
 
For more complex situtation, i.e. using different backing_file, you need to use the XML 
topology infile.
 
 
Customize the hardware 
^^^^^^^^^^^^^^^^^^^^^^
You can customize the virtual machines hardware by defining a template::

 vm5k --n_vm 20 --vm_template '<vm mem="4096" hdd="10" cpu="4" cpuset="auto"/>' 

If you want to test your application on a specific hardware (CPU, RAM, ...), you can select the 
Grid'5000 elements you want to use by giving a list of cluster or sites::

 vm5k --n_vm 100 -r hercule,griffon,graphene  -w 2:00:00

or select the number of hosts you want on each element::

 vm5k --n_vm 100 -r taurus:4,nancy:10 -w 2:00:00
 
See https://www.grid5000.fr/mediawiki/index.php/Special:G5KHardware for more details.
 
 
Use an existing job
^^^^^^^^^^^^^^^^^^^

You may use an existing grid reservation::

 vm5k --n_vm 100 -j 42895 
 vm5k --n_vm 10 -j grenoble:1657430
 
It will retrieve the hosts that you have, deploy and configure it, and finally distribute the VM 
on them.


Deploy in an isolated vlan 
^^^^^^^^^^^^^^^^^^^^^^^^^^

Grid'5000 offers the possibility of using KaVLAN to deploy your nodes in an isolated VLAN,  
https://www.grid5000.fr/mediawiki/index.php/Network_isolation_on_Grid%275000. You can 
use it in vm5k with::

 vm5k --n_vm 100 -r reims -w 2:00:00 -k
 vm5k --n_vm 100 -r taurus:4,nancy:10 -w 2:00:00 -k
 vm5k --n_vm 600 -r grid5000:100 -w 2:00:00 -k -b reims
 
When using global kavlan, you must blacklist reims due to bug 

Use a topology file 
^^^^^^^^^^^^^^^^^^^

To have the finest control on the deployment topology, you can use an input file that described the topology and VM
characteristics::

 vm5k -i topology_file.xml -w 6:00:00

where `topology_file.xml` is:

.. literalinclude:: infile.xml
  
  
Options
-------


Execution
^^^^^^^^^

Manage how vm5k is executed

  -h, --help            show this help message and exit
  -v, --verbose         print debug messages
  -q, --quiet           print only warning and error messages
  -o OUTDIR, --outdir OUTDIR
                        where to store the vm5k log files
                        default=vm5k_20140219_003738_+0100
  -p PROGRAM, --program PROGRAM
                        Launch a program at the end of the deployment

Mode
^^^^

Define the mode of vm5k

  -n N_VM, --n_vm N_VM  number of virtual machines
  -i INFILE, --infile INFILE
                        XML file describing the placement of VM on G5K sites and clusters
  -j JOB_ID, --job_id JOB_ID
                        use the hosts from a oargrid_job or a oar_job.
  -w WALLTIME, --walltime WALLTIME
                        duration of your reservation
  -k, --kavlan          Deploy the VM in a KaVLAN

Physical hosts
^^^^^^^^^^^^^^

Tune the physical hosts.

  -r RESOURCES, --resources RESOURCES
                        list of Grid'5000 elements
  -b BLACKLISTED, --blacklisted BLACKLISTED
                        list of Grid'5000 elements to be blacklisted
  -e ENV_NAME, --env_name ENV_NAME
                        Kadeploy environment name
  -a ENV_FILE, --env_file ENV_FILE
                        path to the Kadeploy environment file
  --forcedeploy         force the deployment of the hosts
  --nodeploy            consider that hosts are already deployed
  --host-munin          monitor hosts with munin
  --host-packages HOST_PACKAGES
                        comma separated list of packages to be installed on the hosts

Virtual machines
^^^^^^^^^^^^^^^^

Tune the virtual machines.

  -t VM_TEMPLATE, --vm_template VM_TEMPLATE
                        XML string describing the virtual machine
  -f VM_BACKING_FILE, --vm_backing_file VM_BACKING_FILE
                        backing file for your virtual machines
  -l VM_DISK_LOCATION, --vm_disk_location VM_DISK_LOCATION
                        Where to create the qcow2: one (default) or all)
  -d VM_DISTRIBUTION, --vm_distribution VM_DISTRIBUTION
                        how to distribute the VM distributed (default) or concentrated
  --vm-clean-disks      force to use a fresh copy of the vms backing_file
  --vm-munin            monitor VM with munin
  --vm-packages VM_PACKAGES
                        comma separated list of packages to be installed on the vms


