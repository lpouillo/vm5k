**********************
:mod:`vm5k.deployment`
**********************

.. automodule:: vm5k.deployment



This module provides tools to deploy hosts and virtual machines on the Grid'5000 platform,
using a preconfigured version of debian wheezy.

* a wheezy-x64-base environnement 
* libvirt-bin and qemu-kvm from debian testing (jessie)
* a bridged networking for virtual machines

It needs a range of IP, either from g5k-subnets or kavlan to configure the VMs.


.. autoclass:: vm5k_deployment
	:members: run, hosts_deployment, packages_management, configure_service_node, configure_libvirt, deploy_vms
   	:show-inheritance:

