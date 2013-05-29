G5KDeployCloud
==============

Automate virtual machines deployment on Grid5000 in a global KaVLAN..


## Prerequisites
This script is based on *execo* to control the deployment process of *debian*-based physical hosts
with *libvirt* installed and configured

## Workflow
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
  * upgrade the hosts and installed libvirt packages
  * create the backing file for the virtual machine
* set up the **virtual machines**
  * create the qcow2 disks on the hosts
  * perform installation with virt-install
  * start the virtual machines

## Usage
To deploy 100 VM on squeeze-x64-prod and with the squeeze-x64-base.qcow2 KVM image
on any Grid5000 cluster with KaVLAN and hardware virtualization

  G5KDeployCloud.py -n 100 

To deploy 50 VM on a specific environnement for 2 hours on cluster hercule, griffon, graphene 


  G5KDeployCloud.py -n 50 -c hercule griffon graphene -w 2:0:0 -h_enf /home/lpouilloux/synced/environments/wheezy-nfs-libvirt/wheezy-nfs-libvirt.env 




