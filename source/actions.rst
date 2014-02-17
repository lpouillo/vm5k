**********************
:mod:`vm5k.actions`
**********************

.. automodule:: vm5k.actions

This module provides tools to interact with the virtual machines.


VM definition and distribution
------------------------------

.. autofunction:: show_vms

.. autofunction:: define_vms

.. autofunction:: distribute_vms

.. autofunction:: list_vm

VM state
--------

.. autofunction:: destroy_vms

.. autofunction:: create_disks

.. autofunction:: create_disks_on_hosts

.. autofunction:: install_vms

.. autofunction:: start_vms

.. autofunction:: wait_vms_have_started

.. autofunction:: migrate_vm

.. autofunction:: rm_qcow2_disks