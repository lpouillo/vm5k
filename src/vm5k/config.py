from execo import configuration

default_vm = {'id': None, 'host': None, 'ip': None, 'mac': None,
    'mem': 512, 'n_cpu': 1, 'cpuset': 'auto',
    'hdd': 10, 'backing_file': '/grid5000/images/KVM/wheezy-x64-base.qcow2',
    'real_file': False, 'state': 'KO'}

configuration['color_styles']['OK'] = 'green',  'bold'
configuration['color_styles']['KO'] = 'red', 'bold'
configuration['color_styles']['Unknown'] = 'white', 'bold'
configuration['color_styles']['step'] = 'yellow', 'bold'
configuration['color_styles']['VM'] = 'white', 'bold'
configuration['color_styles']['Thread'] = 'cyan', 'bold'
