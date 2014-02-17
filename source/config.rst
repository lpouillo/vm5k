******************
:mod:`vm5k.config`
******************

.. automodule:: vm5k.config

Define a dict for default VM:: 

    default_vm = {'id': None, 'host': None, 'ip': None, 'mac': None,
    'mem': 512, 'n_cpu': 1, 'cpuset': 'auto',
    'hdd': 10, 'backing_file': '/tmp/vm-base.img',
    'state': 'KO'}
    
Create some new color_style.