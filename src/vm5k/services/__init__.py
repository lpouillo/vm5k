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

from dnsmasq import dnsmasq_server
from munin import setup_munin
from aptcacher import setup_aptcacher_server, configure_apt_proxy
