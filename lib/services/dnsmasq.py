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
from tempfile import mkstemp
from execo import logger, SshProcess, Put
from execo_g5k import get_g5k_sites

def dns_dhcp_server(server, clients, ip_mac, netmask):
    """Configure a DNS/DHCP server with dnsmasq
    
    :param server: host where the server will be installed
    
    :param clients: list of hosts that will be declared in dnsmasq
    
    :param ip_mac: list of tuples containing the (ip, mac) for the clients
    
    :param netmask: the network mask (255.255.255.255)
     """
    logger.info('Installing and configuring a DNS/DHCP server on %s', server)
    cmd ='export DEBIAN_MASTER=noninteractive ; apt-get update ; apt-get -y purge dnsmasq-base ; '+\
         'apt-get install -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confnew" '+\
         '-y dnsmasq'
    SshProcess(cmd, server).run()
    logger.debug('Creating dnsmasq.conf')

    dhcp_range = 'dhcp-range='+ip_mac[0][0]+','+ip_mac[len(clients)-1][0]+','+netmask+',12h\n'
    dhcp_router = 'dhcp-option=option:router,'+ip_mac[len(clients)-1][0]+'\n'
    dhcp_hosts = ''+'\n'.join( [ 'dhcp-host='+':'+ip_mac[i][1]+','+clients[i]+','+ip_mac[i][0] 
                                for i in range(len(clients)) ])
    dhcp_option = 'dhcp-option=option:domain-search,grid5000.fr,'+\
            ','.join( [site+'.grid5000.fr' for site in get_g5k_sites()])+'\n'
    _, tmpfile = mkstemp(dir = '/tmp/', prefix='dnsmasq.conf_')
    f = open(tmpfile, 'w')
    f.write(dhcp_range+dhcp_router+dhcp_hosts+'\n'+dhcp_option)
    f.close()
    Put([server], [tmpfile], remote_location='/etc/').run()
    SshProcess('cd /etc && cp '+tmpfile.split('/')[-1]+' dnsmasq.conf', server).run()

    logger.debug('Restarting service ...')
    cmd = 'service dnsmasq stop ; rm /var/lib/misc/dnsmasq.leases ; service dnsmasq start',
    SshProcess( cmd, server).run()
