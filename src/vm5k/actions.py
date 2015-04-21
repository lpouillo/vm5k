# Copyright 2012-2014 INRIA Rhone-Alpes, Service Experimentation et
# Developpement
#
# This file is part of Vm5k.
#
# Vm5k is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Vm5k is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
# License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Vm5k.  If not, see <http://www.gnu.org/licenses/>
"""A set of functions to manipulate virtual machines on Grid'5000"""
import sys
from os import fdopen
from pprint import pformat
from execo import SshProcess, TaktukPut, logger, TaktukRemote, Process, \
    SequentialActions, ChainPut, Local
from execo.log import style
from execo.time_utils import sleep
from execo_g5k import get_host_site
import tempfile
from math import ceil
from execo.exception import ActionsFailed
from config import default_vm
from utils import get_CPU_RAM_FLOPS, get_max_vms
from itertools import cycle
from random import randint


def show_vms(vms):
    """Print a short resume of vms parameters.

    :params vms: a list containing a dict by virtual machine """
    logger.info(style.log_header('Virtual machines \n') + '%s',
                ', '.join([style.VM(vm['id']) + ' (' + str(vm['mem']) +
                           'Mb, ' + str(vm['n_cpu']) + ' cpu ' +
                           vm['cpuset'] + ', ' + str(vm['hdd']) + 'Gb)'
                           for vm in vms]))


def define_vms(vms_id, template=None, ip_mac=None, state=None, host=None,
               n_cpu=None, cpusets=None, mem=None, hdd=None, backing_file=None,
               real_file=None):
    """Create a list of virtual machines, where VM parameter is a dict
    similar to
    {'id': None, 'host': None, 'ip': None, 'mac': None,
    'mem': 512, 'n_cpu': 1, 'cpuset': 'auto',
    'hdd': 10, 'backing_file': '/tmp/vm-base.img',
    'state': 'KO'}

    Can be generated from a template or using user defined parameters that
    can be a single element or a list of element

    :param vms_id: a list of string that will be used as vm id

    :param template: an XML element defining the template of the VM

    :param ip_mac: a list of tuple containing ip, mac correspondance

    :param state: the state of the VM

    :param host: the host of the VM (string)

    :param n_cpu: the number of virtual CPU of the VMs

    :param real_file: boolean to use a real file
    """

    n_vm = len(vms_id)
    if template is None:
        n_cpu = [default_vm['n_cpu']] * n_vm if n_cpu is None \
            else [n_cpu] * n_vm if isinstance(n_cpu, int) else n_cpu
        cpusets = [default_vm['cpuset']] * n_vm if cpusets is None \
            else [cpusets] * n_vm if isinstance(cpusets, int) else cpusets
        mem = [default_vm['mem']] * n_vm if mem is None \
            else [mem] * n_vm if isinstance(mem, int) else mem
        hdd = [default_vm['hdd']] * n_vm if hdd is None \
            else [hdd] * n_vm if isinstance(hdd, int) else hdd
        backing_file = [default_vm['backing_file']] * n_vm if backing_file is None \
            else [backing_file] * n_vm if isinstance(backing_file, str) else backing_file
        real_file = [default_vm['real_file']] * n_vm if real_file is None \
            else [real_file] * n_vm if isinstance(real_file, bool) else real_file
        state = [default_vm['state']] * n_vm if state is None \
            else [state] * n_vm if isinstance(state, str) else state
        host = [default_vm['host']] * n_vm if host is None \
            else [host] * n_vm if isinstance(host, str) else host

    else:
        n_cpu = [default_vm['n_cpu']] * n_vm if 'n_cpu' not in template.attrib \
            else [int(template.get('n_cpu'))] * n_vm
        cpusets = [default_vm['cpuset']] * n_vm if 'cpuset' not in template.attrib \
            else [template.get('cpuset')] * n_vm
        mem = [default_vm['mem']] * n_vm if 'mem' not in template.attrib \
            else [int(template.get('mem'))] * n_vm
        hdd = [default_vm['hdd']] * n_vm if 'hdd' not in template.attrib \
            else [int(template.get('hdd'))] * n_vm
        backing_file = [default_vm['backing_file']] * n_vm if 'backing_file' not in template.attrib \
            else [template.get('backing_file')] * n_vm
        real_file = [default_vm['real_file']] * n_vm if 'real_file' not in template.attrib \
            else [template.get('real_file')] * n_vm
        state = [default_vm['state']] * n_vm if 'state' not in template.attrib \
            else [template.get('state')] * n_vm
        host = [default_vm['host']] * n_vm if 'host' not in template.attrib \
            else [template.get('host')] * n_vm

    ip_mac = [(None, None)] * n_vm if ip_mac is None else ip_mac

    vms = [{'id': vms_id[i], 'mem': mem[i], 'n_cpu': n_cpu[i],
            'cpuset': cpusets[i], 'hdd': hdd[i], 'host': host[i],
            'backing_file': backing_file[i], 'real_file': real_file[i],
            'state': state[i],
            'ip': ip_mac[i][0], 'mac': ip_mac[i][1]} for i in range(n_vm)]

    logger.debug('VM parameters have been defined:\n%s',
                 ' '.join([style.emph(param['id']) for param in vms]))
    return vms


def distribute_vms(vms, hosts, distribution='round-robin'):
    """Distribute the virtual machines on the hosts.

    :param vms: a list of VMs dicts which host key will be updated

    :param hosts: a list of hosts

    :param distribution: a string defining the distribution type:
     'round-robin', 'concentrated', 'n_by_hosts', 'random

    """
    logger.debug('Initial virtual machines distribution \n%s',
                 "\n".join([vm['id'] + ": " + str(vm['host']) for vm in vms]))

    if distribution in ['round-robin', 'concentrated', 'random']:
        attr = get_CPU_RAM_FLOPS(hosts)
        dist_hosts = hosts[:]
        iter_hosts = cycle(dist_hosts)
        host = iter_hosts.next()
        for vm in vms:
            remaining = attr[host].copy()
            while remaining['RAM'] - vm['mem'] <= 0 \
                    or remaining['CPU'] - vm['n_cpu'] / 3 <= 0:
                dist_hosts.remove(host)
                if len(dist_hosts) == 0:
                    req_mem = sum([vm['mem'] for vm in vms])
                    req_cpu = sum([vm['n_cpu'] for vm in vms]) / 3
                    logger.error('Not enough ressources ! \n' + 'RAM'.rjust(20)
                                 + 'CPU'.rjust(10) + '\n' + 'Needed'.ljust(15)
                                 + '%s Mb'.ljust(15) + '%s \n' +
                                 'Available'.ljust(15) + '%s Mb'.ljust(15)
                                 + '%s \n' + 'Maximum number of VM is %s',
                                 req_mem, req_cpu, attr['TOTAL']['RAM'],
                                 attr['TOTAL']['CPU'],
                                 style.emph(str(get_max_vms(hosts, vm['mem']))))
                    exit()

                iter_hosts = cycle(dist_hosts)
                host = iter_hosts.next()
                remaining = attr[host].copy()

            vm['host'] = host
            remaining['RAM'] -= vm['mem']
            remaining['CPU'] -= vm['n_cpu'] / 3
            attr[host] = remaining.copy()
            if distribution == 'round-robin':
                host = iter_hosts.next()
                remaining = attr[host].copy()
            if distribution == 'random':
                for i in range(randint(0, len(dist_hosts))):
                    host = iter_hosts.next()
                    remaining = attr[host].copy()

    elif distribution == 'n_by_hosts':
        n_by_host = int(len(vms) / len(hosts))
        i_vm = 0
        for host in hosts:
            for i in range(n_by_host):
                vms[i_vm]['host'] = host
                i_vm += 1
        if len(vms) % len(hosts) != 0:
            logger.warning('Reducing number of VMs to have %s by host',
                           style.emph(n_by_host))
            vms[:] = vms[0:n_by_host * len(hosts)]
    else:
        logger.debug('No valid distribution given')
    logger.debug('Final virtual machines distribution \n%s',
                 "\n".join([vm['id'] + ": " + str(vm['host']) for vm in vms]))


def list_vm(hosts, not_running=False):
    """ Return the list of VMs on hosts using a disk which keys are the hosts and
    value are list of VM id"""
    cmd = 'virsh --connect qemu:///system list'
    if not_running:
        cmd += ' --all'
    logger.debug('Listing Virtual machines on ' + pformat(hosts))
    list_vm = TaktukRemote(cmd, hosts).run()
    hosts_vms = {host: [] for host in hosts}
    for p in list_vm.processes:
        lines = p.stdout.split('\n')
        for line in lines:
            if 'running' in line or 'shut off' in line:
                std = line.split()
                hosts_vms[p.host.address].append({'id': std[1]})
    logger.debug(pformat(hosts_vms))
    return hosts_vms


def destroy_vms(hosts, undefine=False):
    """Destroy all the VM on the hosts"""
    cmds = []
    hosts_with_vms = []
    hosts_vms = list_vm(hosts, not_running=True)

    for host, vms in hosts_vms.iteritems():
        if len(vms) > 0:
            if not undefine:
                cmds.append('; '.join('virsh destroy ' + vm['id']
                                      for vm in vms))
            else:
                cmds.append('; '.join('virsh destroy ' + vm['id'] + '; '
                                      'virsh undefine ' + vm['id']
                                      for vm in vms))
            hosts_with_vms.append(host)
    if len(cmds) > 0:
        TaktukRemote('{{cmds}}', hosts_with_vms).run()


def cmd_disk_real(vm):
    """Return a command to create a new disk from the backing_file"""
    return 'qemu-img convert /tmp/' + vm['backing_file'].split('/')[-1] + \
        ' -O qcow2 /tmp/' + vm['id'] + '.qcow2 ;'


def cmd_disk_qcow2(vm):
    """Return a command to create a qcow2 file using the backing_file"""
    return 'qemu-img create -f qcow2 -o backing_file=/tmp/' + \
        vm['backing_file'].split('/')[-1] + ',backing_fmt=qcow2 /tmp/' + \
        vm['id'] + '.qcow2 ' + str(vm['hdd']) + 'G ; '


def create_disks(vms):
    """ Return an action to create the disks for the VMs on the hosts"""
    logger.detail(', '.join([vm['id'] for vm in sorted(vms)]))
    hosts_cmds = {}

    for vm in vms:
        if vm['real_file']:
            cmd = cmd_disk_real(vm)
        else:
            cmd = cmd_disk_qcow2(vm)
        logger.detail(vm['id'] + ': ' + cmd)
        hosts_cmds[vm['host']] = cmd if not vm['host'] in hosts_cmds \
            else hosts_cmds[vm['host']] + cmd

    logger.debug(pformat(hosts_cmds.values()))

    return TaktukRemote('{{hosts_cmds.values()}}', list(hosts_cmds.keys()))


def create_disks_all_hosts(vms, hosts):
    """Create a temporary file containing the vms disks creation commands
    upload it and run it on the hosts"""

    fd, vms_disks = tempfile.mkstemp(dir='/tmp/', prefix='vms_disks_')
    f = fdopen(fd, 'w')
    for vm in vms:
        if vm['real_file']:
            vm_cmd = cmd_disk_real(vm)
        else:
            vm_cmd = cmd_disk_qcow2(vm)
        f.write('\n' + vm_cmd)
    f.close()

    return SequentialActions([ChainPut(hosts, [vms_disks]),
                              TaktukRemote('sh ' + vms_disks.split('/')[-1], 
                                           hosts),
                              Local('rm ' + vms_disks)])


def install_vms(vms):
    """ Return an action to install the VM on the hosts"""
    logger.detail(', '.join([vm['id'] for vm in sorted(vms)]))
    hosts_cmds = {}
    for vm in vms:
        cmd = 'virt-install -d --import --connect qemu:///system ' + \
            '--nographics --noautoconsole --noreboot --name=' + vm['id'] + ' '\
            '--network network=default,mac=' + vm['mac'] + ' --ram=' + \
            str(vm['mem']) + ' --disk path=/tmp/' + vm['id'] + \
            '.qcow2,device=disk,bus=virtio,format=qcow2,size=' + \
            str(vm['hdd']) + ',cache=none ' + \
            '--vcpus=' + str(vm['n_cpu']) + ' --cpuset=' + vm['cpuset'] + ' ; '
        hosts_cmds[vm['host']] = cmd if not vm['host'] in hosts_cmds \
            else hosts_cmds[vm['host']] + cmd

    return TaktukRemote('{{hosts_cmds.values()}}', list(hosts_cmds.keys()))


def start_vms(vms):
    """ Return an action to start the VMs on the hosts """
    hosts_cmds = {}
    for vm in vms:
        cmd = 'virsh --connect qemu:///system start ' + vm['id'] + ' ; '
        hosts_cmds[vm['host']] = cmd if not vm['host'] in hosts_cmds \
            else hosts_cmds[vm['host']] + cmd

    logger.debug(pformat(hosts_cmds))
    return TaktukRemote('{{hosts_cmds.values()}}', list(hosts_cmds.keys()))


def activate_vms(vms, dest='lyon.grid5000.fr'):
    """Connect locally on every host and on all VMS to ping a host
    and update ARP tables"""
    logger.info('Executing ping from virtual machines on hosts')
    cmd = "VMS=`virsh list | grep -v State | grep -v -e '----' | awk '{print $2}'`; " + \
        "for VM in $VMS; do " + \
        " ssh $VM \"ping -c 3 " + dest + " \"; " + \
        "done"
    logger.debug('Launching ping probes to update ARP tables with %s', cmd)
    activate = TaktukRemote(cmd, list(set([vm['host'] for vm in vms])))
    for p in activate.processes:
        p.ignore_exit_code = p.nolog_exit_code = True
        if logger.getEffectiveLevel() <= 10:
            p.stdout_handlers.append(sys.stdout)
    activate.run()
    return activate.ok


def wait_vms_have_started(vms, restart=True):
    """Scan port 22 on all vms, distributed on hosts"""
    # Creating file with list of VMs ip
    fd, tmpfile = tempfile.mkstemp(prefix='vmips')
    f = fdopen(fd, 'w')
    for vm in vms:
        f.write(vm['ip'] + '\n')
    f.close()
    # getting the list of host
    hosts = list(set([vm['host'] for vm in vms]))
    hosts.sort()
    # Pushing file on all hosts
    TaktukPut(hosts, [tmpfile]).run()
    logger.debug(pformat(hosts))
    # Splitting nmap scan
    n_vm_scan = ceil(len(vms) / len(hosts)) + 1
    cmds = []
    for i in range(len(hosts)):
        start = str(int(i * n_vm_scan))
        end = str(int((i + 1) * n_vm_scan))
        cmds.append("awk 'NR>=" + start + " && NR<" + end +
                    "' " + tmpfile.split('/')[-1] + " > nmap_file ; "
                    + "nmap -v -oG - -i nmap_file -p 22")
    logger.debug('%s', pformat(cmds))
    nmap = TaktukRemote('{{cmds}}', hosts)
    nmap_tries = 0
    all_up = False
    started_vms = []
    old_started = started_vms[:]
    while (not all_up) and nmap_tries < 10:
        sleep(15)
        logger.detail('nmap_tries %s', nmap_tries)
        nmap.run()
        for p in nmap.processes:
            for line in p.stdout.split('\n'):
                if 'Status' in line:
                    split_line = line.split(' ')
                    ip = split_line[1]
                    state = split_line[3].strip()
                    if state == 'Up':
                        vm = [vm for vm in vms if vm['ip'] == ip]
                        if len(vm) > 0:
                            vm[0]['state'] = 'OK'

        started_vms = [vm for vm in vms if vm['state'] == 'OK']
        all_up = len(started_vms) == len(vms)
        if started_vms != old_started:
            old_started = started_vms
        else:
            if restart:
                restart_vms([vm for vm in vms if vm['state'] == 'KO'])
            nmap_tries += 1
        if nmap_tries == 1:
            activate_vms([vm for vm in vms if vm['state'] == 'KO'])
        if not all_up:
            logger.info(str(nmap_tries) + ': ' + str(len(started_vms)) + '/' +
                        str(len(vms)))
        nmap.reset()

    TaktukRemote('rm ' + tmpfile.split('/')[-1], hosts).run()
    Process('rm ' + tmpfile).run()
    if all_up:
        logger.info('All VM have been started')
        return True
    else:
        logger.error('All VM have not been started')
        return False


def restart_vms(vms):
    """ """
    hosts = [vm['host'] for vm in vms]
    running_vms = list_vm(hosts)
    for vm in vms:
        if {'id': vm['id']} not in running_vms[vm['host']]:
            logger.info('%s has not been started on %s, starting it',
                        style.vm(vm['id']), style.host(vm['host']))
            SshProcess('virsh start ' + vm['id'], vm['host']).run()


def migrate_vm(vm, host):
    """ Migrate a VM to an host """
    if vm['host'] is None:
        raise NameError
        return None
    else:
        src = vm['host']

    # Check that the disk is here
    test_disk = TaktukRemote('ls /tmp/' + vm['id'] + '.qcow2', [host]).run()
    if not test_disk.ok:
        vm['host'] = host
        create_disk_on_dest = create_disks([vm]).run()
        if not create_disk_on_dest:
            raise ActionsFailed, [create_disk_on_dest]

    cmd = 'virsh --connect qemu:///system migrate ' + vm['id'] + \
        ' --live --copy-storage-inc qemu+ssh://' + host + "/system' "
    return TaktukRemote(cmd, [src])


def rm_qcow2_disks(hosts):
    """Removing qcow2 disks located in /tmp"""
    logger.debug('Removing existing disks')
    TaktukRemote('rm -f /tmp/*.qcow2', hosts).run()
