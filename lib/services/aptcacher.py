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
from execo import logger, SshProcess, Process, Put
from execo.log import style


def apt_cacher_server(server, clients, ):
    """Install and configure apt-cacher on one server and configure APT proxy on clients"""
    logger.info('Apt-cacher installation on %s to be used on \n %s',
                [host.address for host in clients])
    logger.debug('Installing apt-cacher on '+style.host(server.address))
    base_dir  = '/tmp/apt-cacher-ng'
    log_dir   = base_dir+'/log'
    cache_dir = base_dir+'/cache'
    
    logger.debug('Service installation')
    SshProcess('export DEBIAN_MASTER=noninteractive ; apt-get update ; '+\
              'apt-get install -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confnew" -y apt-cacher-ng', 
              server).run()
    logger.debug('Directory creation')
    SshProcess('mkdir -p '+log_dir+'; mkdir -p '+cache_dir+'; chown -R apt-cacher-ng:apt-cacher-ng '+base_dir,
              server).run()
    logger.debug('Service configuration and start')
    SshProcess('sed -i "s/\/var\/cache\/apt-cacher-ng/'+cache_dir+'/g" /etc/apt-cacher-ng/acng.conf ;'+\
              'sed -i "s/\/var\/log\/apt-cacher-ng/'+log_dir+'/g" /etc/apt-cacher-ng/acng.conf ;'+\
              'sed -i "s/3142/9999/g" /etc/apt-cacher-ng/acng.conf ; service apt-cacher-ng restart',
              server).run()     
    logger.info('apt-cacher-ng up and running on '+style.host(server.address))
    
