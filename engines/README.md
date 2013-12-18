vm5k-engine
===========

LiveMigration.py is an experimental engine that helps you to perform migration 
measurements of virtual machines on the Grid5000 platform. 

https://www.grid5000.fr/mediawiki/index.php/Grid5000:Home

It is based on:

- execo http://execo.gforge.inria.fr/doc/readme.html to control the execution of the processes

- libvirt http://libvirt.org/ to setup the virtual machine and perform the migration measurements

- debian http://www.debian.org/index.fr.html

It provides a basic workflow:

- submit a cluster reservation for a given number of nodes (associated with a g5K-subnet)

- deploy an environment on the hosts and configure libvirt

- execute a given workflow for a given range of parameters

- get the results and generate some graphs

The basic usage is to extend it to suit your needs by defining a parameter space and a workflow 
and run it through:

execo-run YOURENGINE -ML cluster


Installation
------------
- install all dependencies listed above
- clone the repository


Laurent Pouilloux, Hemera Engineer - 2013



