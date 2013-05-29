G5KDeployCloud
==============

Automate virtual machines deployment on Grid5000 in a global KaVLAN..


# Prerequisites
This script is based on *execo* to control the deployment process of *debian*-based physical hosts
with *libvirt* installed and configured

# Workflow
* define a deployment **topology**:
** regurarly distributed on a list of sites/clusters
** or from a given xml file 
* manage the **reservation**:
** find the next window available for the deployment
** or use an existing reservation
* configure the **network** 
** determine the parameters from the global KaVLAN id
** create MAC address for the VM
** generate dnsmasq configuration
* install the **hosts**
** deployment of a kadeploy environment name/environment file
** upgrade the hosts and installed libvirt packages
** create the backing file for the virtual machine
* set up the *virtual machines*
** create the qcow2 disks on the hosts
** perform installation with virt-install
** start the virtual machines



