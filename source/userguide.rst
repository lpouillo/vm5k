****************
vm5k user guide
****************





vm5k: automatic virtual machines deployment
===========================================

Automate virtual machines deployment on Grid5000 in a global KaVLAN.



Workflow
--------

* define a deployment **topology**:

  * distributed virtual machines using a template and a list of clusters/sites
  * or from a given xml file (see example below)
  
* manage the **reservation**:

  * find the next window available for the deployment
  * or use an existing reservation

* install the **hosts**

  * deployment of a kadeploy environment name/environment file
  * upgrade the hosts and configure libvirt
  * create the backing file for the virtual machine

* configure the **network**

  * determine the parameters from the global KaVLAN id
  * create MAC address for the VM
  * generate dnsmasq configuration

* set up the **virtual machines**

  * create the qcow2 disks on the hosts
  * perform installation with virt-install
  * start the virtual machines


.. image:: _static/vm5k_workflow.png 


Basic
-----

The basic usage is to create a certain number of virtual machines on Grid5000.
To deploy 100 VM on *wheezy-x64-base* and with the *wheezy-x64-base.qcow2* KVM image
on any Grid5000 cluster with KaVLAN and hardware virtualization, for 2 hours::

  vm5k --n_vm 100 -w 2:00:00

This will automatically get the list of clusters, determine the total number of nodes required,
perform the reservation and do setup hosts and VMs automatically.

Tune the virtual machines
-------------------------

The script use a default template for the virtual machine `<vm mem="1024" hdd="2" cpu="1" cpuset="auto" />`. You 
can define your own template by passing the xml description to vm_template option (-t)::

 vm5k --n_vm 20 --vm_template '<vm mem="4096" hdd="10" cpu="4" cpuset="auto"/>' --vm_backing_file path_to_my_qcow2_file_on_g5k

will deploy 20 virtual machines with system and components you want.

Tune the hosts
--------------

You can also select the hosts by giving a list of cluster or sites and deploy a custom environnement::

 vm5k --n_vm 100 -r hercule,griffon,graphene --host_env_file path_do_mykadeploy_env

or select the number of hosts you want on each element and in a KaVLAN::

 vm5k --n_vm 100 -r lyon:4,griffon:10 -k
 
You may use an existing grid reservation (with a KaVLAN global)::

 vm5k --n_vm 100 -j 42895
 
It will retrieve the hosts that you have, deploy and configure it, and finally distribute the VM on them.


Using a topology file
----------------------

To have the finest control on the deployment topology, you can use an input file that described the topology and VM
characteristics::

 vm5k -i topology_file.xml -w 6:00:00

where `topology_file.xml` is:

.. literalinclude:: infile.xml
  
  

vm5k_engine: automatizing experiments 
=====================================

