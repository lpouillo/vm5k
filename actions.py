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



from pprint import pformat
from itertools import cycle
from execo import Host, SshProcess, Remote, SequentialActions, ParallelActions, logger, TaktukRemote
from execo.log import set_style
from execo_g5k.api_utils import get_host_attributes



def list_vm( host, all = False ):
    """List the vm on host"""
    if all :
        list_vm = Remote('virsh list --all', [host] ).run()
    else:
        list_vm = Remote('virsh list', [host] ).run()
    vms_id = []
    for p in list_vm.processes():
        lines = p.stdout().split('\n')
        for line in lines:
            if 'vm' in line:
                std = line.split()
                vms_id.append(std[1])
    logger.debug('List of VM on host %s\n%s', set_style(host.address, 'host'),
                 ' '.join([set_style(vm_id, 'emph') for vm_id in vms_id]))
    return [ {'vm_id': vm_id} for vm_id in vms_id ]

def kavname_to_shortname( host):
    """ """
    if 'kavlan' in host.address:
        return Host(host.address.split('kavlan')[0][0:-1])
    else:
        return host

def define_vms( n_vm, ip_mac, mem_size = 256, hdd_size = 2, n_cpu = 1, cpusets = None, vms = None, offset = 0 ):
    """ Create a dict of the VM parameters """
    if vms is None:
        vms = []
    if cpusets is None:
        cpusets = {}
        for i in range(n_vm): cpusets['vm-'+str(i)] = 'auto'
    logger.debug('cpusets: %s', pformat(cpusets))

    for i_vm in range( len(vms), n_vm + len(vms)):
        vms.append( {'vm_id': 'vm-'+str(i_vm), 'hdd_size': hdd_size,
                'mem_size': mem_size, 'vcpus': n_cpu, 'cpuset': cpusets['vm-'+str(i_vm)],
                'ip': ip_mac[i_vm+offset][0], 'mac': ip_mac[i_vm+offset][1], 'host': None})
    logger.debug('VM parameters have been defined:\n%s',
                 ' '.join([set_style(param['vm_id'], 'emph') for param in vms]))
    return vms



def distribute_vms_on_hosts( vms, hosts, mode = 'distributed'):    
    
    dist_hosts = hosts[:]
    iter_hosts = cycle(dist_hosts)
    
    host = iter_hosts.next()
    hosts_vm = {}
    max_mem = {}
    total_mem = {}
    if mode is 'distributed':
        for h in hosts:
            max_mem[h.address] = get_host_attributes(kavname_to_shortname(h))['main_memory']['ram_size']/10**6 
            total_mem[h.address] =  0 
                
        for vm in vms:
            if total_mem[host.address] + vm['mem_size'] > max_mem[host.address]:
                dist_hosts.remove(host)
                iter_hosts = cycle(dist_hosts)
                
            vm['host'] = host
            total_mem[host.address] += vm['mem_size']
            if not hosts_vm.has_key(host.address):
                hosts_vm[host.address] = []
            hosts_vm[host.address].append(vm['vm_id'])
            host = iter_hosts.next()
            
            
    elif mode is 'concentrated':
        
        api_host = kavname_to_shortname(host)
        max_mem = get_host_attributes(api_host)['main_memory']['ram_size']/10**6
        total_mem = 0
        for vm in vms:
            total_mem += vm['mem_size']
            if total_mem > max_mem:
                host = iter_hosts.next()
                api_host = kavname_to_shortname(host)
                max_mem = get_host_attributes(api_host)['main_memory']['ram_size']/10**6
                total_mem = vm['mem_size']
            if not hosts_vm.has_key(host.address):
                hosts_vm[host.address] = []
            vm['host'] = host
            hosts_vm[host.address].append(vm['vm_id'])
    
    logger.debug( '\n%s', '\n'.join( [set_style(host, 'host')+': '+\
                                      ', '.join( [set_style(vm,'emph')  for vm in host_vms]) for host, host_vms in hosts_vm.iteritems() ] ))
    
    return vms

def create_disk_host(vm, host = None,  backing_file = '/tmp/vm-base.img', backing_file_fmt = 'raw'):
    """ Return an action for the creation of the disk on the VM """
    if host is None:
        host = vm['host']
    
    cmd = 'qemu-img create -f qcow2 -o backing_file='+backing_file+',backing_fmt='+backing_file_fmt+' /tmp/'+\
            vm['vm_id']+'.qcow2 '+str(vm['hdd_size'])+'G';

    return Remote(cmd, [host])
    #return cmd

def create_disks_host(vms, host = None, backing_file = '/tmp/vm-base.img', backing_file_fmt = 'raw'):
    """ Return a ParallelAction containing the disks creation for the VM"""
#    api_host = kavname_to_shortname(host)
#    n_cpu = get_host_attributes(kavname_to_shortname(api_host))['architecture']['smt_size']    
    disks_actions = []
    for vm in vms:
        disks_actions.append( create_disk_host( vm, vm['host'],
                                    backing_file = backing_file, backing_file_fmt = backing_file_fmt))
        
    
    return SequentialActions(disks_actions)
#    return SequentialActions(disks_actions)
#    n = int(len(vms)/4)
#    split_disks_actions = [ ParallelActions(disks_actions[i::n]) for i in range(n) ]
#    return SequentialActions(split_disks_actions)


    

def create_disks_hosts(vms, hosts = None, backing_file = '/tmp/vm-base.img', backing_file_fmt = 'raw'):
    """ """
    
    hosts_vms = {}
    
    for vm in vms:
        if not hosts_vms.has_key(vm['host']):
            hosts_vms[vm['host']] = []
        hosts_vms[vm['host']].append(vm)
    
    log = ''    
    all_actions = []
    for host, vms in hosts_vms.iteritems():
        host_actions = []
        for vm in vms:
            host_actions.append(create_disk_host(vm))
        log += '\n'+set_style(host.address.split('.')[0], 'host')+': '+\
                              ', '.join([set_style(vm['vm_id'], 'emph') for vm in vms])
        all_actions.append(SequentialActions(host_actions))
    logger.info(log)
    return ParallelActions(all_actions)
   
#def create_disks_hosts_taktuk(vms, hosts, backing_file = '/tmp/vm-base.img', backing_file_fmt = 'raw'):
#    """ """
#    cmds = [ 'qemu-img create -f qcow2 -o backing_file='+backing_file+',backing_fmt='+backing_file_fmt+' /tmp/'+\
#            vm['vm_id']+'.qcow2 '+str(vm['hdd_size'])+'G' for vm in vms ]
#    
#    return TaktukRemote( "{{cmds}}", sorted(hosts*len(cmds)) ) 
    
def install_vm(vm, host = None):
    """ """
    if host is None:
        host = Host(vm['host'])
    cmd = 'virt-install -d --import --connect qemu:///system --nographics --noautoconsole --noreboot'+ \
        ' --name=' + vm['vm_id'] + ' --network network=default,mac='+vm['mac']+' --ram='+str(vm['mem_size'])+ \
        ' --disk path=/tmp/'+vm['vm_id']+'.qcow2,device=disk,format=qcow2,size='+str(vm['hdd_size'])+',cache=none '+\
        ' --vcpus='+ str(vm['vcpus'])+' --cpuset='+vm['cpuset']
    install_action = Remote(cmd, [host])
    ## TEST WHICH VERSION OF VIRT-INSTALL CORRECT THE BUG 
    cmd_fix = 'sed "s/raw/qcow2/g" /etc/libvirt/qemu/'+vm['vm_id']+'.xml >  /etc/libvirt/qemu/'+ \
        vm['vm_id']+'.xml.cor ; mv /etc/libvirt/qemu/'+vm['vm_id']+'.xml.cor /etc/libvirt/qemu/'+ \
        vm['vm_id']+'.xml; virsh define /etc/libvirt/qemu/'+vm['vm_id']+'.xml; '
    fix_action = Remote(cmd_fix, [host])    
    
    return SequentialActions([install_action, fix_action ])
    
def install_vms(vms):
    """ """    
    
    hosts_actions = {}
    for vm in vms:
        if not hosts_actions.has_key(vm['host']):
            hosts_actions[vm['host']] = []
        hosts_actions[vm['host']].append( install_vm( vm) )
    install_actions = []
    for host, actions in hosts_actions.iteritems():
        logger.info('- %s on %s', set_style( str(len(actions))+' VM', 'emph'), set_style(host.address.split('.')[0], 'host'))
        install_actions.append(SequentialActions(actions))
    
    return ParallelActions( install_actions)    
    
    



def start_vm(vm, host = None):
    if host is None:
        host = Host(vm['host'])
    cmd = 'virsh --connect qemu:///system start '+vm['vm_id']
    return Remote(cmd, [host])
    

def start_vms(vms):   
    hosts_actions = {}
    for vm in vms:
        if not hosts_actions.has_key(vm['host']):
            hosts_actions[vm['host']] = []
        hosts_actions[vm['host']].append( start_vm( vm) )
    start_actions = []
    for host, actions in hosts_actions.iteritems():
        logger.info('- %s on %s', set_style( str(len(actions))+' VM', 'emph'), set_style(host.address.split('.')[0], 'host'))
        start_actions.append(SequentialActions(actions))
    
    return ParallelActions( start_actions)  
    
#    for vm in vms:
#        start_actions.append(start_vm(vm))
#    return SequentialActions(start_actions)

def wait_vms_have_started(vms, host):
    
    ip_list = ','.join( [vm['ip'] for vm in vms ] )
    nmap_tries = 0
    ssh_open = False
    while (not ssh_open) and nmap_tries < 50:
        logger.debug('nmap_tries %s', nmap_tries)
        nmap_tries += 1            
        nmap = SshProcess('nmap -PN '+ip_list+' -p 22', host)
        nmap.run()
        logger.debug('%s', nmap.cmd())
        stdout = nmap.stdout().split('\n')
        for line in stdout:
            if 'Nmap done' in line:
                logger.debug(line)
                ssh_open = line.split()[2] == line.split()[5].replace('(','')
    if ssh_open:
        logger.info('All VM have been started')
    else:
        logger.error('All VM have not been started')



def create_disks( hosts, vms_params, backing_file = '/tmp/vm-base.img', backing_file_fmt = 'raw'):
    """ Create the VM disks on the hosts and the dict of vm parameters"""
    logger.debug('%s', pformat(hosts))
    disk_actions = []
    for vm_params in vms_params:
        logger.info('Creating disk for %s (%s)', set_style(vm_params['vm_id'], 'emph'), vm_params['ip'] )
        cmd = 'qemu-img create -f qcow2 -o backing_file='+backing_file+',backing_fmt='+backing_file_fmt+' /tmp/'+\
            vm_params['vm_id']+'.qcow2 '+str(vm_params['hdd_size'])+'G';
        disk_actions.append( Remote(cmd, hosts))
    logger.debug('%s', pformat(disk_actions))
    disks_created = SequentialActions(disk_actions).run()

    if disks_created.ok():
        return True
    else:
        return False



def install( vms_params, host, autostart = True, packages = None):
    """Perform virt-install using the dict vm_params"""
    install_actions = []
    log_vm = ' '.join([set_style(param['vm_id'], 'emph') for param in vms_params])
    for param in vms_params:
        cmd = 'virt-install -d --import --connect qemu:///system --nographics --noautoconsole --noreboot'+ \
        ' --name=' + param['vm_id'] + ' --network network=default,mac='+param['mac']+' --ram='+str(param['mem_size'])+ \
        ' --disk path=/tmp/'+param['vm_id']+'.qcow2,device=disk,format=qcow2,size='+str(param['hdd_size'])+',cache=none '+\
        ' --vcpus='+ str(param['vcpus'])+' --cpuset='+param['cpuset']
        logger.debug('%s', cmd)
        install_actions.append(Remote(cmd, [host]))
    logger.debug('%s', pformat(install_actions))
    logger.info('Installing %s on host %s', log_vm, set_style(host.address, 'host'))
    action = SequentialActions(install_actions).run()

    if not action.ok():
        return False
    ## FIX VIRT-INSTALL BUG WITH QCOW2 THAT DEFINE A WRONG DRIVER FOR THE DISK
    fix_actions = []
    for param in vms_params:
        cmd = 'sed "s/raw/qcow2/g" /etc/libvirt/qemu/'+param['vm_id']+'.xml >  /etc/libvirt/qemu/'+ \
        param['vm_id']+'.xml.cor ; mv /etc/libvirt/qemu/'+param['vm_id']+'.xml.cor /etc/libvirt/qemu/'+ \
        param['vm_id']+'.xml; virsh define /etc/libvirt/qemu/'+param['vm_id']+'.xml; '
        fix_actions.append(Remote(cmd, [host]))
    logger.debug('%s', pformat(fix_actions))
    ParallelActions(fix_actions).run()
    logger.info('%s are ready to be started', log_vm )

    if not action.ok():
        return False

    if autostart:
        result = start( vms_params, host )
        if not result:
            return False

    if packages is not None:
        logger.info('Installing additionnal packages %s', packages )
        cmd = 'apt-get update && apt-get install -y '+packages
        action = Remote(cmd, [ Host(vm['ip']+'.grid5000.fr') for vm in vms_params ]).run()
        if not action.ok():
            return False

    return True



def start( vms_params, host):
    """Start vm on hosts """
    log_vm = ' '.join([set_style(param['vm_id'], 'emph') for param in vms_params])
    start_tries = 0
    vm_started = False
    while (not vm_started) and start_tries < 5:

        logger.debug('start_tries %s', start_tries)
        start_tries += 1
        start_actions = []
        for param in vms_params:
            cmd = 'virsh --connect qemu:///system destroy '+param['vm_id']+';  virsh --connect qemu:///system start '+param['vm_id']+';  sleep 20;'
            logger.debug('%s', cmd)
            start_actions.append(Remote(cmd, [host]))
        logger.debug('%s', pformat(start_actions))
        logger.info('Starting %s ...', log_vm)
        SequentialActions(start_actions).run()
        
        ip_range = vms_params[0]['ip'].rsplit('.', 1)[0]+'.'+','.join([vm_param['ip'].split('.')[3] for vm_param in vms_params])

        nmap_tries = 0
        ssh_open = False
        while (not ssh_open) and nmap_tries < 30:
            logger.debug('nmap_tries %s', nmap_tries)
            nmap_tries += 1            
            nmap = SshProcess('nmap '+ip_range+' -p 22', host)
            nmap.run()
            logger.debug('%s', nmap.cmd())
            stdout = nmap.stdout().split('\n')
            for line in stdout:
                if 'Nmap done' in line:
                    logger.debug(line)
                    ssh_open = line.split()[2] == line.split()[5].replace('(','')

        if ssh_open:
            logger.info('All VM have been started')
            vm_started = True
        else:
            logger.error('All VM have not been started')
        logger.debug('vm_started %s', vm_started)

    return vm_started

def destroy( vms_params, host, autoundefine = True ):
    """Destroy vm on hosts """
    if len(vms_params) > 0:
        logger.info('Destroying %s VM on hosts %s', ' '.join([set_style(param['vm_id'], 'emph') for param in vms_params]),
                    set_style(host.address, 'host') )
        destroy_actions = []
        for param in vms_params:
            cmd = "virsh destroy "+param['vm_id']
            destroy_actions.append(Remote(cmd, [host], ignore_exit_code = True))
        action = ParallelActions(destroy_actions).run()

        if not action.ok():
            return False

        if autoundefine:
            result = undefine( vms_params, host )
            if not result:
                return False

    return True

def undefine(vms_params, host):
    undefine_actions = []
    for param in vms_params:
        cmd = "virsh undefine "+param['vm_id']
        undefine_actions.append(Remote(cmd, [host], ignore_exit_code = True))
    logger.info('Undefining %s VM on hosts %s', ' '.join([set_style(param['vm_id'], 'emph') for param in vms_params]),
                        set_style(host.address, 'host') )
    

    action = ParallelActions(undefine_actions).run()

    return action.ok()


def destroy_all( hosts):
    """Destroy all the VM on the hosts"""
    actions = []
    for host in hosts:
        vms_params = list_vm(host, all = True)
        
        if len(list_vm(host, all = True)) > 0:
            action = destroy( vms_params, host )
            actions.append(action)

#    logger.debug('%s', pprint(actions))

    if False in actions:
        return False
    else:
        return True


