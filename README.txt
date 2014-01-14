====
vm5k
====

A python module to ease the experimentations of virtual Machines for the Grid'5000 platform.
It is composed of:
- a lib to setup Debian hosts with libvirt and manage virtual machines
- a script that deploy virtual machines
- an experimental engine that conduct user defined workflow for a set of parameters

Developped by the Inria Hemera initiative 2010-2014.


Requirements
============
The module requires:
* execo 2.2, <http://execo.gforge.inria.fr/>


Installation
============
You first need to install execo and it's dependencies on any Grid'5000 frontend.
http://execo.gforge.inria.fr/doc/userguide.html
Then you clone the repository and install the package:
   
   git clone https://github.com/lpouillo/vm5k.git
   cd vm5k
   python setup.py install --user


Usage
=====

Virtual machines deployment with vm5k
-------------------------------------
Automate virtual machines deployment on Grid5000 in a global KaVLAN.
     
### Workflow
* define a deployment **topology**:
  * distributed virtual machines using a template and a list of clusters/sites
  * or from a given xml file (see example below)
* manage the **reservation**:
  * find the next window available for the deployment
  * or use an existing reservation
* configure the **network** 
  * determine the parameters from the global KaVLAN id
  * create MAC address for the VM
  * generate dnsmasq configuration
* install the **hosts**
  * deployment of a kadeploy environment name/environment file
  * upgrade the hosts and configure libvirt
  * create the backing file for the virtual machine
* set up the **virtual machines**
  * create the qcow2 disks on the hosts
  * perform installation with virt-install
  * start the virtual machines

### Basic
The basic usage is to create a certain number of virtual machines on Grid5000.
To deploy 100 VM on *squeeze-x64-prod* and with the *squeeze-x64-base.qcow2* KVM image
on any Grid5000 cluster with KaVLAN and hardware virtualization, for 2 hours:

    vm5k.py --n_vm 100 -w 2:00:00

This will automatically get the list of clusters, determine the total number of nodes required,
perform the reservation and do setup hosts and VMs automatically.

### Tune the virtual machines
The script use a default template for the virtual machine `<vm mem="1024" hdd="2" cpu="1" cpuset="auto" />`.
You can define your own one an one-line XML file and also use a custom backing file:

    vm5k.py --n_vm 20 --vm_template mytemplate.xml --vm_backing_file path_to_my_qcow2_file_on_g5k

will deploy 20 virtual machines with system and components you want.

### Tune the hosts 
You can also select the hosts by giving a list of cluster or sites and deploy a custom environnement

    vm5k.py --n_vm 100 -c hercule griffon graphene --host_env_file path_do_mykadeploy_env
    vm5k.py --n_vm 100 -c hercule griffon graphene --host_env_name wheezy-x64-base
    
You may use an existing grid reservation (with a KaVLAN global) 
    
    vm5k.py --n_vm 100 -j 42895

It will retrieve the hosts that you have, deploy and configure it, and finally distribute the VM on them.
   
### Using an topology file
To have the finest control on the deployment, you can use an input file that described the topology and VM 
characteristics. 

    vm5k.py -i topology_file.xml -w 6:00:00
    
where `topology_file.xml` is:

    <vm5k>
      <site id="luxembourg">
        <cluster id="granduc">
          <host id="granduc-2">
            <vm mem="2048" hdd="4" id="vm-33" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-34" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-35" cpu="1"/>
          </host>
          <host id="granduc-9">
            <vm mem="2048" hdd="4" id="vm-54" cpu="1"/>
          </host>
          <host id="granduc-2">
            <vm mem="2048" hdd="4" id="vm-33" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-34" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-35" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-33" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-34" cpu="1"/>
          </host>
          <host id="granduc-3">
            <vm mem="2048" hdd="4" id="vm-36" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-37" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-38" cpu="1"/>
          </host>      
        </cluster>
      </site>
      <site id="lyon">
        <cluster id="hercule">
          <host id="hercule-1">
            <vm mem="2048" hdd="4" id="vm-30" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-31" cpu="1"/>
          </host>    
        </cluster>
        <cluster id="orion">
          <host id="orion-1">
            <vm mem="2048" hdd="4" id="vm-38" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-39" cpu="1"/>
          </host>
           <host id="orion-2">
            <vm mem="2048" hdd="4" id="vm-30" cpu="1"/>
            <vm mem="2048" hdd="4" id="vm-31" cpu="1"/>
          </host>
        </cluster>
      </site>
     </vm5k>
     
    


Publications
============



People
======

Contributors
------------
* Laurent Pouilloux
* Daniel Balouek-Thomert

Grid'5000 technical support
---------------------------
* Matthieu Imbert
* Simon Delamare

Testers
-------
* Jonathan Rouzaud-Cornabas
* Jonathan Pastor
* Takahiro Hirofuchi
* Adrien Lèbre

