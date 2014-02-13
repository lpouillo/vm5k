.. vm5k documentation master file, created by
   sphinx-quickstart on Thu Feb 13 01:19:10 2014.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

vm5k
====

.. image:: grid5000.png 

A Python module to help you to deploy virtual machines on the `Grid'5000 <https://www.grid5000.fr/>`_ 
plaform. It has been designed to perform reproducible cloud experiments:  deployment of a 
customized environment, manipulation of virtual machines (VM), automatic experimental engine. 

.. automodule:: vm5k



Deployment script
=================






This module provides tools to deploy hosts and virtual machines on the Grid'5000 platform,
using a preconfigured version of debian wheezy.

* a wheezy-x64-base environnement 
* libvirt-bin and qemu-kvm from debian testing (jessie)
* a bridged networking for virtual machines

It needs a range of IP, either from g5k-subnets or kavlan to configure the VMs.


.. autoclass:: vm5k_deployment
	:members: hosts_deployment, 
   	:show-inheritance:
    



.. toctree::
    :maxdepth: 2
    

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`





