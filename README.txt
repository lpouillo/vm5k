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
* matplotlib 1.2 <http://matplotlib.org/> for plotting


Installation
============
Connect on a Grid'5000 frontend and type the following commands::

  export http_proxy="http://proxy:3128"
  export https_proxy="https://proxy:3128"
  easy_install --user execo
  easy_install --user matplotlib
  cd /grid5000/code/staging/
  python setup.py install --user

Configure your PATH according to 
http://execo.gforge.inria.fr/doc/userguide.html#installation



People
======

Contributors
------------
* Laurent Pouilloux
* Jonathan Rouzaud-Cornabas
* Daniel Balouek-Thomert
* Flavien Quesnel
* Jonathan Pastor
* Takahiro Hirofuchi
* Adrien Lèbre


Grid'5000 technical support
---------------------------
* Matthieu Imbert
* Simon Delamare










