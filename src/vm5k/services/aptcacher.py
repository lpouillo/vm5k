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
from execo import logger, TaktukRemote, Host, ParallelActions
from execo.log import style


def setup_aptcacher_server(hosts, base_dir='/tmp/apt-cacher-ng'):
    """Install and configure apt-cacher on one server"""
    hosts = map(Host, hosts)
    logger.info('Installing apt-cacher on %s',
                ','.join([style.host(host.address) for host in hosts]))
    logger.detail('Package')
    package = TaktukRemote('export DEBIAN_MASTER=noninteractive ; apt-get update ; ' +
                           'apt-get install -o Dpkg::Options::="--force-confdef" -o ' +
                           'Dpkg::Options::="--force-confnew" -y apt-cacher-ng',
                           hosts).run()
    if not package.ok:
        logger.error('Unable to install apt-cacher-ng on %s')
        return

    logger.detail('Directory creation')
    log_dir = base_dir + '/log'
    cache_dir = base_dir + '/cache'
    mkdirs = TaktukRemote('mkdir -p ' + log_dir + '; mkdir -p ' + cache_dir +
                          '; chown -R apt-cacher-ng:apt-cacher-ng ' + base_dir,
                          hosts).run()
    if not mkdirs.ok:
        logger.error('Unable to create the directories')
        return
    cmd = 'sed -i "s#/var/cache/apt-cacher-ng#' + cache_dir + \
          '#g" /etc/apt-cacher-ng/acng.conf ;' + \
          'sed -i "s#/var/log/apt-cacher-ng#' + log_dir + '#g" ' + \
          '/etc/apt-cacher-ng/acng.conf ;' + \
          'sed -i "s/3142/9999/g" /etc/apt-cacher-ng/acng.conf ; ' + \
          'sed -i "s?#Proxy: http://www-proxy.example.net:80?Proxy: ' + \
          'http://proxy:3128?g" /etc/apt-cacher-ng/acng.conf ; ' + \
          'service apt-cacher-ng restart'
    configure = TaktukRemote(cmd, hosts).run()
    if not configure.ok:
        logger.error('Unable to configure and restart the service')
        return

    logger.info('apt-cacher-ng up and running on %s',
                ','.join([style.host(host.address) for host in hosts]))


def configure_apt_proxy(vms):
    """Override apt proxy-guess with server as proxy"""
    hosts_vms = {}
    for vm in vms:
        if not vm['host'] in hosts_vms:
            hosts_vms[vm['host']] = []
        hosts_vms[vm['host']].append(vm['ip'])
    conf = []
    for server, clients in hosts_vms.iteritems():
        server = Host(server)
        logger.detail('Configuring %s as APT proxy for %s',
                      style.host(server.address), ','.join(clients))
        conf.append(TaktukRemote(' echo \'Acquire::http::Proxy \"http://' + 
                                 server.address + ':9999" ; \' > /etc/apt/apt.conf.d/proxy-guess', 
                                 clients))
    ParallelActions(conf).run()

