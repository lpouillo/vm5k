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


from deployment import distribute_vms, prettify, vm5k_deployment, \
    get_oar_job_vm5k_resources, get_kavlan_ip_mac, get_max_vms, \
    get_oargrid_job_vm5k_resources, get_vms_slot, print_step
from actions import default_vm, define_vms, install_vms, create_disks, destroy_vms, list_vm, \
    start_vms, wait_vms_have_started, create_disks_on_hosts, show_vms

