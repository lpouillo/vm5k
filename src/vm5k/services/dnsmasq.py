# Copyright 2009-2013 INRIA Rhone-Alpes, Service Experimentation et
# Developpement
#
from os import fdopen
from tempfile import mkstemp
from math import ceil, log
from execo import logger, SshProcess, Put, Remote, Host, TaktukRemote, \
    Process, TaktukPut
from execo.log import style
from execo_g5k import get_host_site


def add_vms(vms, server):
    """Generate the list of virtual machines """
    logger.debug('Adding the VM in /etc/hosts ...')
    fd, vms_list = mkstemp(dir='/tmp/', prefix='vms_')
    f = fdopen(fd, 'w')
    f.write('\n' + '\n'.join([vm['ip'] + ' \t ' + vm['id'] for vm in vms]))
    f.close()
    Put([server], [vms_list], remote_location='/etc/').run()
    SshProcess('[ -f /etc/hosts.bak ] && cp /etc/hosts.bak /etc/hosts || ' +
               ' cp /etc/hosts /etc/hosts.bak', server).run()
    Remote('cat /etc/' + vms_list.split('/')[-1] + ' >> /etc/hosts',
           [server]).run()
    Process('rm ' + vms_list).run()


def get_server_ip(host):
    """Get the server IP"""
    if isinstance(host, Host):
        host = host.address
    logger.debug('Retrieving IP from %s', style.host(host))
    get_ip = Process('host ' + host + ' |cut -d \' \' -f 4')
    get_ip.shell = True
    get_ip.run()
    ip = get_ip.stdout.strip()
    return ip


def get_server_iface(server):
    """Get the default network interface of the serve """
    logger.debug('Retrieving default interface from %s',
                 style.host(server.address))
    get_if = SshProcess('ip route |grep default |cut -d " " -f 5',
                        server).run()
    return get_if.stdout.strip()


def resolv_conf(server, clients, sites):
    """Generate the resolv.conf with dhcp parameters and put it on the server
    """
    fd, resolv = mkstemp(dir='/tmp/', prefix='resolv_')
    f = fdopen(fd, 'w')
    f.write('domain grid5000.fr\nsearch grid5000.fr ' +
            ' '.join([site + '.grid5000.fr' for site in sites]) +
            '\nnameserver ' + get_server_ip(server))
    f.close()
    TaktukPut(clients, [resolv], remote_location='/etc/').run()
    TaktukRemote('cd /etc && cp ' + resolv.split('/')[-1] + ' resolv.conf',
                 clients).run()
    Process('rm ' + resolv).run()


def dhcp_conf(server, vms, sites):
    """Generate the dnsmasq.conf with dhcp parameters and
    put it on the server"""
    logger.debug('Creating dnsmasq.conf')
    ip_mac = [(vm['ip'], vm['mac']) for vm in vms]
    dhcp_lease = 'dhcp-lease-max=10000\n'
    dhcp_range = 'dhcp-range=' + ip_mac[0][0] + ',' + ip_mac[len(vms) - 1][0] + ',12h\n'
    dhcp_router = 'dhcp-option=option:router,' + get_server_ip(server) + '\n'
    dhcp_hosts = '' + '\n'.join(['dhcp-host=' + ':' + ip_mac[i][1] + ',' +
                               vms[i]['id'] + ',' + ip_mac[i][0]
                               for i in range(len(vms))])
    dhcp_option = 'dhcp-option=option:domain-search,grid5000.fr,' + \
        ','.join([site + '.grid5000.fr' for site in sites]) + '\n'
    fd, dnsmasq = mkstemp(dir='/tmp/', prefix='dnsmasq_')
    f = fdopen(fd, 'w')
    f.write(dhcp_lease + dhcp_range + dhcp_router + dhcp_hosts + '\n' + dhcp_option)
    f.close()
    Put([server], [dnsmasq], remote_location='/etc/').run()
    SshProcess('cd /etc && cp ' + dnsmasq.split('/')[-1]+' dnsmasq.conf',
               server).run()
    Process('rm ' + dnsmasq).run()


def sysctl_conf(server, vms):
    """Change the default value of net.ipv4.neigh.default.gc_thresh*
    to handle large number of IP"""
    val = int(2 ** ceil(log(len(vms), 2)))
    conf = "\nnet.ipv4.neigh.default.gc_thresh3 = " + str(3*val) + \
        "\nnet.ipv4.neigh.default.gc_thresh2 = " + str(2*val) + \
        "\nnet.ipv4.neigh.default.gc_thresh1 = " + str(val)
    fd, sysctl = mkstemp(dir='/tmp/', prefix='sysctl_')
    f = fdopen(fd, 'w')
    f.write(conf)
    f.close()
    Put([server], [sysctl], remote_location='/etc/').run()
    SshProcess('cd /etc && cat ' + sysctl.split('/')[-1] +
               ' >> sysctl.conf && sysctl -p', server).run()
    Process('rm '+sysctl).run()


def dnsmasq_server(server, clients=None, vms=None, dhcp=True):
    """Configure a DHCP server with dnsmasq

    :param server: host where the server will be installed

    :param clients: list of hosts that will be declared in dnsmasq

    :param vms: list of virtual machines

    """
    logger.debug('Installing and configuring a DNS/DHCP server on %s', server)

    test_running = Process('nmap ' + server + ' -p 53 | grep domain')
    test_running.shell = True
    test_running.run()
    if 'open' in test_running.stdout:
        logger.info('DNS server already running, updating configuration')
    else:
        cmd = 'killall dnsmasq; export DEBIAN_MASTER=noninteractive ; ' + \
            'apt-get update ; apt-get -y purge dnsmasq-base ; ' + \
            'apt-get install -t wheezy -o Dpkg::Options::="--force-confdef" ' + \
            '-o Dpkg::Options::="--force-confnew" ' + \
            '-y dnsmasq; echo 1 > /proc/sys/net/ipv4/ip_forward '
        SshProcess(cmd, server).run()

    sites = list(set([get_host_site(client) for client in clients
                      if get_host_site(client)] + [get_host_site(server)]))
    add_vms(vms, server)
    if clients:
        kill_dnsmasq = TaktukRemote('killall dnsmasq', clients)
        for p in kill_dnsmasq.processes:
            p.ignore_exit_code = p.nolog_exit_code = True
        kill_dnsmasq.run()
        resolv_conf(server, clients, sites)

    if dhcp:
        sysctl_conf(server, vms)
        dhcp_conf(server, vms, sites)

    logger.debug('Restarting service ...')
    cmd = 'service dnsmasq stop ; rm /var/lib/misc/dnsmasq.leases ; ' + \
        'service dnsmasq start',
    SshProcess(cmd, server).run()
