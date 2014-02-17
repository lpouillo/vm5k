from vm5k.engine import *


default_mig_speed = 125


class DemoMigration(vm5k_engine):

    def __init__(self):
        # Initialize the engine using the parent class, that creates option
        super(DemoMigration, self).__init__()
        self.n_nodes = 2

    def define_parameters(self):
        cluster = self.cluster
        parameters = {}

        att = get_host_attributes(cluster+'-1')
        n_core = att['architecture']['smt_size']
        max_mem = att['main_memory']['ram_size'] / 10 ** 6
        n_vm = {i: {'cpu': [], 'mem': []}
                for i in range(1, n_core * 3 + 1)}
        vm_max_cpu = min(n_core, 16)

        for i in n_vm.iterkeys():
            n_cpu = 1
            while n_cpu <= n_core:
                n_vm[i]['cpu'].append(n_cpu)
                n_cpu += 1
            mem_size = [512]
            li = mem_size[0]
            while li * 2 <= max_mem / i:
                li *= 2
                mem_size.append(li)
                n_vm[i]['mem'] = mem_size

        parameters['n_vm'] = n_vm
        parameters['stress'] = [None, 'cpu', 'ram', 'hdd']

        return parameters
