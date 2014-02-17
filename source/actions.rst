**********************
:mod:`vm5k.actions`
**********************

.. automodule:: vm5k.actions

This module provides tools to interact with the virtual machines.


VM definition and distribution
------------------------------

.. autofunction:: vm5k.actions.show_vms

.. autofunction:: vm5k.actions.define_vms

.. autofunction:: vm5k.actions.distribute_vms

.. autofunction:: vm5k.actions.list_vm

VM state
--------

.. autofunction:: vm5k.actions.destroy_vms

.. autofunction:: vm5k.actions.create_disks

.. autofunction:: vm5k.actions.create_disks_on_hosts

.. autofunction:: vm5k.actions.install_vms

.. autofunction:: vm5k.actions.start_vms

.. autofunction:: vm5k.actions.wait_vms_have_started

.. autofunction:: vm5k.actions.migrate_vm

.. autofunction:: vm5k.actions.rm_qcow2_disks