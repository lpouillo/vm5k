====
vm5k
====

A python module to ease the experimentations of virtual Machines for the Grid'5000 platform.
It is composed of:

* a lib to setup Debian hosts with libvirt and manage virtual machines
* a script that deploy virtual machines
* an experimental engine that conduct user defined workflow for a set of parameters

Developped by the Inria Hemera initiative 2010-2014 
https://www.grid5000.fr/mediawiki/index.php/Hemera

See proper documentation on :
http://vm5k.readthedocs.org

Requirements
============
The module requires:
* execo 2.2, <http://execo.gforge.inria.fr/>


Installation
============
You first need to install execo and on one of the Grid'5000 frontend.

http://execo.gforge.inria.fr/doc/userguide.html

Then you clone the repository and install the package:

    $ git clone https://github.com/lpouillo/vm5k.git
    $ cd vm5k
    $ python setup.py install --user

Don't forget to configure your PYTHONPATH and your PATH according to http://execo.gforge.inria.fr/doc/userguide.html#installation




Publications
============

Matthieu Imbert, Laurent Pouilloux, Jonathan Rouzaud-Cornabas, Adrien
Lèbre, Takahiro Hirofuchi "`Using the EXECO toolbox to perform
automatic and reproducible cloud experiments
<http://hal.inria.fr/hal-00861886/>`_" *1st International Workshop on
UsiNg and building ClOud Testbeds UNICO, collocated with IEEE CloudCom
2013* 2013

Takahiro Hirofuchi, Adrien Lèbre, and Laurent Pouilloux
"`Adding a Live Migration Model Into SimGrid, One More Step Toward the Simulation
of Infrastructure-as-a-Service Concerns`"
In 5th IEEE International Conference on Cloud Computing Technology and Science (IEEE CloudCom 2013), Bristol, United Kingdom, December 2013

Daniel Balouek, Alexandra Carpen Amarie, Ghislain Charrier, Frédéric Desprez, Emmanuel Jeannot, Emmanuel Jeanvoine, Adrien Lèbre, David Margery, Nicolas Niclausse, Lucas Nussbaum, Olivier Richard, Christian Pérez, Flavien Quesnel, Cyril Rohr, and Luc Sarzyniec
Adding Virtualization Capabilities to Grid'5000
Research Report RR-8026, INRIA, July 2012 [bibtex] [pdf]



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

