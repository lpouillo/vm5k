# Copyright 2009-2012 INRIA Rhone-Alpes, Service Experimentation et
# Developpement
#
# This file is part of Execo.
#
# Execo is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Execo is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
# License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Execo.  If not, see <http://www.gnu.org/licenses/>
"""A set of functions to manipulate virtual machines on Grid'5000"""

from os import fdopen
from pprint import pformat
from execo import SshProcess, Put, logger, TaktukRemote, Process, ParallelActions, Host
from execo.log import style
from execo.time_utils import sleep
from execo_g5k import default_frontend_connection_params
from execo_g5k.api_utils import get_host_site
import tempfile
from copy import deepcopy
from execo.exception import ActionsFailed
from vm5k.config import default_vm
from vm5k.utils import get_CPU_RAM_FLOPS
from itertools import cycle
from random import randint


def show_vms(vms):
    """ """
    logger.info(style.log_header('Virtual machines \n')+'%s',
        ', '.join( [style.VM(vm['id'])+' ('+str(vm['mem'])+'Mb, '+str(vm['n_cpu'])+' cpu '+\
                   vm['cpuset']+', '+str(vm['hdd'])+'Gb)'
                    for vm in vms ] ) )


def define_vms( vms_id, template = None, ip_mac = None, state = None, host = None,
        n_cpu = 1, cpusets = None, mem = None, hdd = None, backing_file = None):
    """Create a list of virtual machines, where VM parameter is a dict similar to
    {'id': None, 'host': None, 'ip': None, 'mac': None,
    'mem': 512, 'n_cpu': 1, 'cpuset': 'auto',
    'hdd': 10, 'backing_file': '/tmp/vm-base.img',
    'state': 'KO'}
    :param template: a XML element
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
        backing_file = [default_vm['backing_file']]*n_vm if backing_file is None \
            else [backing_file] * n_vm if isinstance(backing_file, str) else backing_file
        state = [default_vm['state']]*n_vm if state is None \
            else [state] * n_vm if isinstance(state, str) else state
        host = [default_vm['host']]*n_vm if host is None \
            else [host] * n_vm if isinstance(host, Host) else host
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
        state = [default_vm['state']]*n_vm if 'state' not in template.attrib \
            else [template.get['state']] * n_vm

    ip_mac = [ (None, None) ] * n_vm if ip_mac is None else ip_mac

    vms = [ {'id': vms_id[i], 'mem': mem[i], 'n_cpu': n_cpu[i], 'cpuset': cpusets[i],
             'hdd': hdd[i], 'backing_file': backing_file[i], 'host': None, 'state': state[i],
             'ip': ip_mac[i][0], 'mac': ip_mac[i][1]} for i in range(n_vm)]

    logger.debug('VM parameters have been defined:\n%s',
                 ' '.join([style.emph(param['id']) for param in vms]))
    return vms


def distribute_vms(vms, hosts, distribution = 'round-robin'):
    """ """
    logger.debug('Initial virtual machines distribution \n%s',
        "\n".join( [ vm['id']+": "+str(vm['host']) for vm in vms] ))
    if distribution in ['round-robin', 'concentrated']:
        attr = get_CPU_RAM_FLOPS(hosts)
        dist_hosts = hosts[:]
        iter_hosts = cycle(dist_hosts)
        host = iter_hosts.next()
        for vm in vms:
            
            remaining = attr[host].copy()
            while remaining['RAM'] - vm['mem'] <= 0 \
                or remaining['CPU'] - vm['n_cpu']/3 <= 0:

                dist_hosts.remove(host)

                if len(dist_hosts) == 0:
                    req_mem = sum( [ vm['mem'] for vm in vms])
                    req_cpu = sum( [ vm['n_cpu'] for vm in vms])/3
                    logger.error('Not enough ressources ! \n'+'RAM'.rjust(20)+'CPU'.rjust(10)+'\n'+\
                                 'Available'.ljust(15)+'%s Mb'.ljust(15)+'%s \n'+\
                                 'Needed'.ljust(15)+'%s Mb'.ljust(15)+\
                                 '%s \n', attr['TOTAL']['RAM'], attr['TOTAL']['CPU'],req_mem, req_cpu)

                iter_hosts = cycle(dist_hosts)
                host = iter_hosts.next()
                remaining = attr[host].copy()

            vm['host'] = host
            remaining['RAM'] -= vm['mem']
            remaining['CPU'] -= vm['n_cpu']/3
            attr[host] = remaining.copy()
            if distribution == 'round-robin':
                host = iter_hosts.next()
                remaining = attr[host].copy()
            if distribution ==  'random':
                for i in range(randint(0, len(dist_hosts))):
                    host = iter_hosts.next()

    elif distribution == 'n_by_hosts':
        n_by_host = int(len(vms)/len(hosts))
        i_vm = 0
        for host in hosts:
            for i in range(n_by_host):
                vms[i_vm]['host'] = host
                i_vm += 1

    logger.debug('Final virtual machines distribution \n%s',
        "\n".join( [ vm['id']+": "+str(vm['host']) for vm in vms ] ) )


def list_vm( hosts, all = False ):
    """ Return the list of VMs on host """
    cmd = 'virsh --connect qemu:///system list'
    if all:
        cmd += ' --all'
    logger.debug('Listing Virtual machines on '+pformat(hosts))
    list_vm = TaktukRemote(cmd, hosts ).run()
    hosts_vms = { host: [] for host in hosts }
    for p in list_vm.processes:
        lines = p.stdout.split('\n')
        for line in lines:
            if 'vm' in line:
                std = line.split()
                hosts_vms[p.host.address].append({'id': std[1]})
#     logger.debug('List of VM on host %s\n%s', style.host(host),
#                  ' '.join([style.emph(id) for id in vms_id]))
    logger.debug(pformat(hosts_vms))
    return hosts_vms

def destroy_vms( hosts):
    """Destroy all the VM on the hosts"""

    cmds = []
    hosts_with_vms = []
    hosts_vms = list_vm(hosts, all = True)
    
    for host, vms in hosts_vms.iteritems():
        if len(vms) > 0:
            cmds.append( '; '.join('virsh destroy '+vm['id']+'; virsh undefine '+vm['id'] for vm in vms ))
            hosts_with_vms.append(host)
    
    if len(cmds) > 0:
        TaktukRemote('{{cmds}}', hosts_with_vms).run()



def create_disks(vms, backing_file = '/tmp/vm-base.img', backing_file_fmt = 'raw'):
    """ Return an action to create the disks for the VMs on the hosts"""
    hosts_cmds = {}
    for vm in vms:
        cmd = 'qemu-img create -f qcow2 -o backing_file='+backing_file+',backing_fmt='+backing_file_fmt+' /tmp/'+\
            vm['id']+'.qcow2 '+str(vm['hdd'])+'G ; '
        hosts_cmds[vm['host']] = cmd if not hosts_cmds.has_key(vm['host']) else hosts_cmds[vm['host']]+cmd

    logger.debug(pformat(hosts_cmds.values()))

    return TaktukRemote('{{hosts_cmds.values()}}', list(hosts_cmds.keys()))

def create_disks_on_hosts(vms, hosts, backing_file = '/tmp/vm-base.img', backing_file_fmt = 'raw'):
    """ Return a Parallel action to create the qcow2 disks on all hosts"""
    host_actions = []
    for host in hosts:
        tmp_vms = deepcopy(vms)
        for vm in tmp_vms:
            vm['host'] = host
        host_actions.append(create_disks(tmp_vms, backing_file, backing_file_fmt))

    return ParallelActions(host_actions)

def install_vms(vms):
    """ Return an action to install the VM on the hosts"""
    hosts_cmds = {}
    for vm in vms:
        cmd = 'virt-install -d --import --connect qemu:///system --nographics --noautoconsole --noreboot'+ \
        ' --name=' + vm['id'] + ' --network network=default,mac='+vm['mac']+' --ram='+str(vm['mem'])+ \
        ' --disk path=/tmp/'+vm['id']+'.qcow2,device=disk,bus=virtio,format=qcow2,size='+str(vm['hdd'])+',cache=none '+\
        ' --vcpus='+ str(vm['n_cpu'])+' --cpuset='+vm['cpuset']+' ; '
        hosts_cmds[vm['host']] = cmd if not hosts_cmds.has_key(vm['host']) else hosts_cmds[vm['host']]+cmd

    logger.debug(pformat(hosts_cmds))
    return TaktukRemote('{{hosts_cmds.values()}}', list(hosts_cmds.keys()))


def start_vms(vms):
    """ Return an action to start the VMs on the hosts """
    hosts_cmds = {}
    for vm in vms:
        cmd = 'virsh --connect qemu:///system start '+vm['id']+' ; '
        hosts_cmds[vm['host']] = cmd if not hosts_cmds.has_key(vm['host']) else hosts_cmds[vm['host']]+cmd

    logger.debug(pformat(hosts_cmds))
    return TaktukRemote('{{hosts_cmds.values()}}', list(hosts_cmds.keys()))


#def check_vm_state(vms):
#    """ """


def wait_vms_have_started(vms, host = None):
    """ Try to make a ls on all vms and return True when all process are ok0"""
    if host is None:
        host = get_host_site(vms[0]['host'])
        user = default_frontend_connection_params['user']
    else:
        user = 'root'

    fd, tmpfile = tempfile.mkstemp(prefix='vmips')
    f = fdopen(fd, 'w')
    for vm in vms:
        f.write(vm['ip']+'\n')
    f.close()
    Put([host], [tmpfile], connection_params = {'user': user}).run()
    nmap_tries = 0
    started_vms = '0'
    old_started = '0'
    ssh_open = False
    while (not ssh_open) and nmap_tries < 10:
        sleep(20)
        logger.debug('nmap_tries %s', nmap_tries)

        nmap = SshProcess('nmap -i '+tmpfile.split('/')[-1]+' -p 22', host, connection_params = {'user': user}).run()
        logger.debug('%s', nmap.cmd)
        for line in nmap.stdout.split('\n'):
            if 'Nmap scan report for' in line:
                ip = line.split(' ')[4].strip()
                vm = [ vm for vm in vms if vm['ip'] == ip]
                if len(vm) > 0:
                    vm[0]['state'] = 'OK'
            if 'Nmap done' in line:
                logger.debug(line)
                ssh_open = line.split()[2] == line.split()[5].replace('(','')
                started_vms = line.split()[5].replace('(','')
        if started_vms != old_started:
            old_started = started_vms
        else:
            nmap_tries += 1
        if not ssh_open:
            logger.info(str(nmap_tries)+': '+  started_vms+'/'+str(len(vms)) )
    SshProcess('rm '+tmpfile.split('/')[-1], host, connection_params = {'user': user}).run()
    Process('rm '+tmpfile).run()
    if ssh_open:
        logger.info('All VM have been started')
        return True
    else:
        logger.error('All VM have not been started')
        return False

    return ssh_open


def migrate_vm(vm, host):
    """ Migrate a VM to an host """
    if vm['host'] is None:
        raise NameError
        return None
    else:
        src = vm['host']

    # Check that the disk is here
    test_disk = TaktukRemote('ls /tmp/'+vm['id']+'.qcow2', [host]).run()
    if not test_disk.ok:
        vm['host'] = host
        create_disk_on_dest = create_disks([vm]).run()
        if not create_disk_on_dest:
            raise ActionsFailed, [create_disk_on_dest]

    cmd = 'virsh --connect qemu:///system migrate '+vm['id']+' --live --copy-storage-inc '+\
            'qemu+ssh://'+host+"/system'  "
    return TaktukRemote(cmd, [src] )





def rm_qcow2_disks( hosts):
    logger.debug('Removing existing disks')
    TaktukRemote('rm -f /tmp/*.qcow2', hosts).run()




