***************************
Readme for the vm5k package
***************************

A python module to ease the experimentations of virtual Machines on the Grid'5000 platform.
It is composed of:

* a script that deploy virtual machines (vm5k)
* an experimental engine that conduct user defined workflow for a set of parameters (vm5k_engine)
* a lib to setup Debian hosts with libvirt and manage virtual machines 

Developed by the Inria Hemera initiative 2010-2014 
https://www.grid5000.fr/mediawiki/index.php/Hemera

See documentation on http://vm5k.readthedocs.org

Requirements
============
The module requires:

* execo 2.2, <http://execo.gforge.inria.fr/>
* optionnally matplotlib 1.2 <http://matplotlib.org/> and networkx 1.7 for plotting


Installation
============
Connect on a Grid'5000 frontend and type the following commands::

  export http_proxy="http://proxy:3128"
  export https_proxy="https://proxy:3128"
  wget http://execo.gforge.inria.fr/downloads/execo-2.2.tar.gz
  tar -xzf execo-2.2.tar.gz && cd execo-2.2 && python setup.py install --user
  easy_install --user matplotlib
  easy_install --user networkx
  mkdir -p vm5k && rsync -avuP /grid5000/code/staging/vm5k/ vm5k
  cd vm5k && python setup.py install --user 

Add .local/bin to your path and run vm5k !


People
======

Contributors
------------
* Laurent Pouilloux
* Daniel Balouek-Thomert
* Jonathan Rouzaud-Cornabas
* Flavien Quesnel
* Jonathan Pastor
* Takahiro Hirofuchi
* Adrien Lèbre


Grid'5000 technical support
---------------------------
* Matthieu Imbert
* Simon Delamare










