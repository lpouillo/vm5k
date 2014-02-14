***************************
Readme for the vm5k package
***************************

A python module to ease the experimentations of virtual Machines on the Grid'5000 platform.
It is composed of:

* a script that deploy virtual machines (vm5k)
* an experimental engine that conduct user defined workflow for a set of parameters (vm5k_engine)
* a lib to setup Debian hosts with libvirt and manage virtual machines 


Developped by the Inria Hemera initiative 2010-2014 
https://www.grid5000.fr/mediawiki/index.php/Hemera

See documentation on http://vm5k.readthedocs.org

Requirements
============
The module requires:

* execo 2.2, <http://execo.gforge.inria.fr/>
* 


Installation
============
You first need to install execo and on one of the Grid'5000 frontend.

http://execo.gforge.inria.fr/doc/userguide.html

Then you clone the repository and install the package:

 git clone https://github.com/lpouillo/vm5k.git
 cd vm5k
 python setup.py install --user

Don't forget to configure your PYTHONPATH and your PATH according to 
http://execo.gforge.inria.fr/doc/userguide.html#installation


People
======

Contributors
------------
* Laurent Pouilloux
* Jonathan Rouzaud-Cornabas
* Daniel Balouek-Thomert
* Flavien Quesnel


Grid'5000 technical support
---------------------------
* Matthieu Imbert
* Simon Delamare

Testers
-------
* Jonathan Pastor
* Takahiro Hirofuchi
* Adrien Lèbre







