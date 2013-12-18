from execo import configuration


default_vm =  {'id': None, 'host': None, 'ip': None, 'mac': None,
    'mem': 512, 'n_cpu': 1, 'cpuset': 'auto', 
    'hdd': 10, 'backing_file': '/tmp/vm-base.img',
    'state': 'KO'}

configuration['color_styles']['OK'] = 'green',  'bold'
configuration['color_styles']['KO'] = 'red', 'bold'
configuration['color_styles']['Unknown'] = 'white', 'bold'
configuration['color_styles']['step'] = 'on_yellow', 'bold'
configuration['color_styles']['VM'] = 'white', 'bold'