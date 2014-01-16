# Copyright 2009-2013 INRIA Rhone-Alpes, Service Experimentation et
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
from os import fdopen
from tempfile import mkstemp
from execo import logger, SshProcess, Put, Remote, Host, TaktukRemote
from execo.log import style
from execo_g5k import get_g5k_sites, default_frontend_connection_params, g5k_configuration


def vms_lists(vms, server):
    """ """
    logger.debug('Adding the VM in /etc/hosts ...')
    fd, vms_list = mkstemp(dir = '/tmp/', prefix='vms_')
    f = fdopen(fd, 'w')
    f.write('\n'+'\n'.join( [vm['ip']+' \t '+vm['id'] for vm in vms ] ) )
    f.close()
    Put([server], [vms_list], remote_location= '/etc/').run()
    SshProcess('[ -f /etc/hosts.bak ] && cp /etc/hosts.bak /etc/hosts || cp /etc/hosts /etc/hosts.bak',
           server).run()
    Remote('cat /etc/'+vms_list.split('/')[-1]+' >> /etc/hosts', [server]).run()

def get_server_ip(host):
    """ """
    if isinstance(host, Host):
        host = host.address
    logger.debug('Retrieving IP from %s', style.host(host))
    get_ip = SshProcess('host '+host+' |cut -d \' \' -f 4', g5k_configuration['default_frontend'],
                  connection_params = default_frontend_connection_params).run()
    ip =  get_ip.stdout.strip()
    return ip

def get_server_iface(server):
    """ """
    logger.debug('Retrieving default interface from %s', style.host(server.address))
    get_if = SshProcess('ip route |grep default |cut -f 5 -d " "', server).run()
    return get_if.stdout.strip()


def resolv_conf(server, clients):
    """ """
    fd, resolv = mkstemp(dir = '/tmp/', prefix='resolv_')
    f = fdopen(fd, 'w')
    f.write('domain grid5000.fr\nsearch grid5000.fr '+\
            ' '.join( [site+'.grid5000.fr' for site in get_g5k_sites()] )
            +' \nnameserver '+get_server_ip(server)+ '\n')
    f.close()
    Put(clients, [resolv], remote_location = '/etc/').run()
    TaktukRemote('cd /etc && cp '+resolv.split('/')[-1]+' resolv.conf', clients).run()

def dhcp_conf(server, vms):
    """ """
    logger.debug('Creating dnsmasq.conf')
    ip_mac = [ (vm['ip'], vm['mac']) for vm in vms ]
    dhcp_lease = 'dhcp-lease-max=10000\n'
    dhcp_range = 'dhcp-range='+ip_mac[0][0]+','+ip_mac[len(vms)-1][0]+',12h\n'
    dhcp_router = 'dhcp-option=option:router,'+get_server_ip(server)+'\n'
    dhcp_hosts = ''+'\n'.join( [ 'dhcp-host='+':'+ip_mac[i][1]+','+vms[i]['id']+','+ip_mac[i][0]
                                for i in range(len(vms)) ])
    dhcp_option = 'dhcp-option=option:domain-search,grid5000.fr,'+\
            ','.join( [site+'.grid5000.fr' for site in get_g5k_sites()])+'\n'
    fd, dnsmasq = mkstemp(dir = '/tmp/', prefix='dnsmasq_')
    f = fdopen(fd, 'w')
    f.write(dhcp_lease+dhcp_range+dhcp_router+dhcp_hosts+'\n'+dhcp_option)
    f.close()
    Put([server], [dnsmasq], remote_location='/etc/').run()
    SshProcess('cd /etc && cp '+dnsmasq.split('/')[-1]+' dnsmasq.conf', server).run()



def dnsmasq_server(server, clients, vms, dhcp = True):
    """Configure a DHCP server with dnsmasq

    :param server: host where the server will be installed

    :param clients: list of hosts that will be declared in dnsmasq

    :param vms: list of virtual machines

     """
    logger.debug('Installing and configuring a DNS/DHCP server on %s', server)
    cmd ='export DEBIAN_MASTER=noninteractive ; apt-get update ; apt-get -y purge dnsmasq-base ; '+\
         'apt-get install -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confnew" '+\
         '-y dnsmasq; echo 1 > /proc/sys/net/ipv4/ip_forward '
    SshProcess(cmd, server).run()

    vms_lists(vms, server)
    resolv_conf(server, clients)
    if dhcp is not None:
        dhcp_conf(server, vms)

    logger.debug('Restarting service ...')
    cmd = 'service dnsmasq stop ; rm /var/lib/misc/dnsmasq.leases ; service dnsmasq start',
    SshProcess( cmd, server).run()






