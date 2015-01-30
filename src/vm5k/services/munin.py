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
from os import fdopen
from tempfile import mkstemp
from execo import logger, SshProcess, Process, Put, TaktukRemote
from execo.log import style


def setup_munin(server, clients, plugins=['cpu', 'memory', 'iostat']):
    """Install a munin server on one host and configure it  """


def get_munin_stats(server, destination_directory='.'):
    """Retrieve the munin statistics """


def _munin_clients(server, clients, plugins):
    """ """


def _munin_server(server, clients):
    """Install the monitoring service munin. Must be executed inside Grid'5000
    to be able to resolve the server and clients IP.

    :param server: a execo.Host

    :param clients: a list of execo.Hosts

    :param plugins: a list of munin plugins

    """
    logger.info('Munin monitoring service installation, server = %s, clients = \n %s',
                server.address, [host.address for host in clients])

    logger.debug('Configuring munin server %s', style.host('server'))
    cmd = 'export DEBIAN_MASTER=noninteractive ; apt-get update && apt-get install -y munin'
    inst_munin_server = SshProcess(cmd, server).run()

    logger.debug('Creating configuration files for server')
    fd, server_conf = mkstemp(dir='/tmp/', prefix='munin-nodes_')
    f = fdopen(fd, 'w')
    for host in clients:
        get_ip = Process('host '+host.address).run()
        ip = get_ip.stdout.strip().split(' ')[3]
        f.write('['+host.address+']\n    address '+ip+'\n   use_node_name yes\n\n')
    f.close()

    Put([server], [server_conf], remote_location='/etc/').run()
    SshProcess('cd /etc && cp '+server_conf.split('/')[-1]+' munin.conf', server).run()
    Process('rm '+server_conf).run()


def add_munin_plugins(hosts, plugins):
    """Create a symbolic link to activate plugins  """
    cmd = '; '.join([ 'ln -s /usr/share/munin/plugins/ /etc/munin/plugins' + plugin for plugin in plugins])
    TaktukRemote(cmd, hosts)


