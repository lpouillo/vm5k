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

import re
import copy
from os import fdopen
from tempfile import mkstemp
from pprint import pformat
from xml.dom import minidom
from random import randint
from itertools import cycle
from math import floor
from execo import logger, Host, Process, Timer, Remote, sleep
from execo.log import style
from execo_g5k import get_oar_job_nodes, get_oargrid_job_oar_jobs, \
    get_oar_job_subnets, get_oar_job_kavlan, wait_oar_job_start, \
    wait_oargrid_job_start, distribute_hosts, get_planning, \
    OarSubmission
from execo.time_utils import get_seconds
from execo_g5k.api_utils import get_host_cluster, get_g5k_clusters, \
    get_host_attributes, get_resource_attributes, get_cluster_site, \
    get_g5k_sites, get_site_clusters, get_host_site
from execo_g5k.planning import _slots_limits

from xml.etree.ElementTree import tostring

__host_longname_regex = re.compile("^([^.]*)(\.([^.]+))?")
def get_host_longname(host):
    """Convert, if needed, the host name to a grid5000 fully qualified name"""
    if isinstance(host, Host):
        host = host.address
    mo = __host_longname_regex.match(host)
    host_shortname = mo.group(1)
    if mo.group(3):
        host_site = mo.group(3)
    else:
        host_site = get_host_site(host_shortname)
    return host_shortname + "." + host_site + ".grid5000.fr"

def hosts_list(hosts, separator=' '):
    """Return a formatted string from a list of hosts"""
    tmp_hosts = copy.deepcopy(hosts)
    for i, host in enumerate(tmp_hosts):
        if isinstance(host, Host):
            tmp_hosts[i] = host.address

    return separator.join([style.host(host.split('.')[0])
                           for host in sorted(tmp_hosts)])


def reboot_hosts(hosts, timeout=300):
    """ """
    reboot = Remote('reboot', hosts).run()
    if not reboot.ok:
        return False
    wait_hosts_down(hosts, timeout)
    wait_hosts_up(hosts, timeout)


def wait_hosts_down(hosts, timeout=300):
    """ """
    up_hosts = map(lambda x: x.address if isinstance(x, Host) else x,
                   hosts)
    fd, hosts_file = mkstemp(dir='/tmp/', prefix='hosts_')
    f = fdopen(fd, 'w')
    f.write('\n' + '\n'.join(up_hosts))
    f.close()
    timer = Timer()
    while len(up_hosts) > 0 and timer.elapsed() < timeout:
        nmap = Process("nmap -v -oG - -i %s -p 22 |grep Host|grep Status" %
                       (hosts_file, ), shell=True).run()
        logger.debug('timer: %s \nnmap output: \n%s', timer.elapsed(),
                     nmap.stdout.strip())
        for line in nmap.stdout.strip().split('\n'):
            if 'Down' in line:
                ip = line.split()[1]
                get_host = Process('host ' + ip + '| cut -f 5 -d " "',
                                   shell=True).run()
                host = get_host.stdout.strip()[0:-1]
                if host in up_hosts:
                    logger.detail(host + ' is down')
                    up_hosts.remove(host)
    Process('rm ' + hosts_file).run()

    return len(up_hosts) == 0


def wait_hosts_up(hosts, timeout=300):
    """ """
    down_hosts = map(lambda x: x.address if isinstance(x, Host) else x,
                     hosts)
    fd, hosts_file = mkstemp(dir='/tmp/', prefix='hosts_')
    f = fdopen(fd, 'w')
    f.write('\n' + '\n'.join(down_hosts))
    f.close()
    timer = Timer()
    while len(down_hosts) > 0 and timer.elapsed() < timeout:
        nmap = Process("nmap -v -oG - -i %s -p 22 |grep Host|grep Status" %
                       (hosts_file, ), shell=True).run()
        logger.debug('timer: %s \nnmap output: \n%s', timer.elapsed(),
                     nmap.stdout.strip())
        for line in nmap.stdout.strip().split('\n'):
            s = line.split()[2]
            host = s[s.find("(") + 1:s.find(")")]
            if host in down_hosts:
                logger.detail('%s is up', host)
                down_hosts.remove(host)
    Process('rm ' + hosts_file).run()
    sleep(3)
    return len(down_hosts) == 0


def get_oar_job_vm5k_resources(jobs):
    """Retrieve the hosts list and (ip, mac) list from a list of oar_job and
    return the resources dict needed by vm5k_deployment """
    resources = {}
    for oar_job_id, site in jobs:
        logger.info('Retrieving resources from %s:%s',
                    style.emph(site), oar_job_id)
        oar_job_id = int(oar_job_id)
        wait_oar_job_start(oar_job_id, site)
        logger.debug('Retrieving hosts')
        hosts = [host.address for host in get_oar_job_nodes(oar_job_id, site)]
        logger.debug('Retrieving subnet')
        ip_mac, _ = get_oar_job_subnets(oar_job_id, site)
        kavlan = None
        if len(ip_mac) == 0:
            logger.debug('Retrieving kavlan')
            kavlan = get_oar_job_kavlan(oar_job_id, site)
            if kavlan:
                ip_mac = get_kavlan_ip_mac(kavlan, site)
        resources[site] = {'hosts': hosts,
                           'ip_mac': ip_mac[300:],
                           'kavlan': kavlan}
    return resources


def get_oargrid_job_vm5k_resources(oargrid_job_id):
    """Retrieve the hosts list and (ip, mac) list by sites from an
    oargrid_job_id and return the resources dict needed by vm5k_deployment,
    with kavlan-global if used in the oargrid job """
    oargrid_job_id = int(oargrid_job_id)
    logger.info('Waiting job start')
    wait_oargrid_job_start(oargrid_job_id)
    resources = get_oar_job_vm5k_resources([(oar_job_id, site)
                                            for oar_job_id, site in
                                            get_oargrid_job_oar_jobs(oargrid_job_id)])
    kavlan_global = None
    for site, res in resources.iteritems():
        if res['kavlan'] >= 10:
            kavlan_global = {'kavlan': res['kavlan'],
                             'ip_mac': resources[site]['ip_mac'],
                             'site': site}
            break
    if kavlan_global:
        resources['global'] = kavlan_global

    return resources


def get_kavlan_network(kavlan, site):
    """Retrieve the network parameters for a given kavlan from the API"""
    logger.debug(str(kavlan) + ' on site ' + site)
    network, mask_size = None, None
    equips = get_resource_attributes('/sites/' + site + '/network_equipments/')
    for equip in equips['items']:
        if 'vlans' in equip and len(equip['vlans']) > 2:
            all_vlans = equip['vlans']
            break
    for info in all_vlans.itervalues():
        if isinstance(info, dict) and 'name' in info \
                and info['name'] == 'kavlan-' + str(kavlan):
            network, _, mask_size = info['addresses'][0].partition('/',)
    logger.debug('network=%s, mask_size=%s', network, mask_size)
    return network, mask_size


def get_kavlan_ip_mac(kavlan, site):
    """Retrieve the network parameters for a given kavlan from the API"""
    network, mask_size = get_kavlan_network(kavlan, site)
    min_2 = (kavlan - 4) * 64 + 2 if kavlan < 8 \
        else (kavlan - 8) * 64 + 2 if kavlan < 10 \
        else 216
    ips = [".".join([str(part) for part in ip]) for ip in
           [ip for ip in get_ipv4_range(tuple([int(part)
            for part in network.split('.')]), int(mask_size))
           if ip[3] not in [0, 254, 255] and ip[2] >= min_2]]
    macs = get_mac_addresses(len(ips))

    return zip(ips, macs)


def get_mac_addresses(n):
    """ """
    macs = []
    for i in range(n):
        mac = _random_mac()
        while mac in macs:
            mac = _random_mac()
        macs.append(mac)
    return macs


def _random_mac():
    return ':'.join(map(lambda x: "%02x" % x, [0x00, 0x020, 0x4e,
                                                  randint(0x00, 0xff),
                                                  randint(0x00, 0xff),
                                                  randint(0x00, 0xff)]))


def get_ipv4_range(network, mask_size):
    """Get the ipv4 range from a network and a mask_size"""
    net = (network[0] << 24
           | network[1] << 16
           | network[2] << 8
           | network[3])
    mask = ~(2 ** (32 - mask_size) - 1)
    ip_start = net & mask
    ip_end = net | ~mask
    return [((ip & 0xff000000) >> 24,
            (ip & 0xff0000) >> 16,
            (ip & 0xff00) >> 8,
            ip & 0xff)
            for ip in xrange(ip_start, ip_end + 1)]


def print_step(step_desc=None):
    """Print an on_magenta coloured string"""
    logger.info(style.step('* ' + step_desc).ljust(45))


def prettify(elem):
    """Return a pretty-printed XML string for the Element.  """
    rough_string = tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ").replace(
                    '<?xml version="1.0" ?>\n', '')


def get_CPU_RAM_FLOPS(hosts):
    """Return the number of CPU and amount RAM for a host list """
    hosts_attr = {'TOTAL': {'CPU': 0, 'RAM': 0}}
    cluster_attr = {}
    for host in hosts:
        if isinstance(host, Host):
            host = host.address
        cluster = get_host_cluster(host)
        if cluster not in cluster_attr:
            attr = get_host_attributes(host)
            cluster_attr[cluster] = {
                 'CPU': attr['architecture']['smt_size'],
                 'RAM': int(attr['main_memory']['ram_size'] / 10 ** 6),
                 'flops': attr['performance']['node_flops']}
        hosts_attr[host] = cluster_attr[cluster]
        hosts_attr['TOTAL']['CPU'] += attr['architecture']['smt_size']
        hosts_attr['TOTAL']['RAM'] += int(attr['main_memory']['ram_size'] \
                                          / 10 ** 6)

    logger.debug(hosts_list(hosts_attr))
    return hosts_attr


def get_hosts_jobs(hosts, walltime, out_of_chart=False):
    """Find the first slot when the hosts are available and return a
     list of jobs_specs

    :param hosts: list of hosts

    :param walltime: duration of reservation
    """
    hosts = map(lambda x: x.address if isinstance(x, Host) else x, hosts)
    planning = get_planning(elements=hosts, out_of_chart=out_of_chart)
    limits = _slots_limits(planning)
    walltime = get_seconds(walltime)
    for limit in limits:
        all_host_free = True
        for site_planning in planning.itervalues():
            for cluster, cluster_planning in site_planning.iteritems():
                if cluster in get_g5k_clusters():
                    for host_planning in cluster_planning.itervalues():
                        host_free = False
                        for free_slot in host_planning['free']:
                            if free_slot[0] <= limit and free_slot[1] >= limit + walltime:
                                host_free = True
                        if not host_free:
                            all_host_free = False
        if all_host_free:
            startdate = limit
            break
    else:
        logger.error('Unable to find a slot for %s', hosts)
        return None

    jobs_specs = []
    for site in planning.keys():
        site_hosts = map(get_host_longname,
                         filter(lambda h: get_host_site(h) == site,
                                hosts))
        sub_res = "{host in ('" + "','".join(site_hosts) + "')}/nodes=" + str(len(site_hosts))
        jobs_specs.append((OarSubmission(resources=sub_res,
                                         reservation_date=startdate), site))

    return jobs_specs


def get_fastest_host(hosts):
        """ Use the G5K api to have the fastest node"""
        attr = get_CPU_RAM_FLOPS(hosts)
        max_flops = -1
        for host in hosts:
            if isinstance(host, Host):
                host = host.address
            flops = attr[host]['flops']
            if flops > max_flops:
                max_flops = flops
                fastest_host = host
        return fastest_host


def get_max_vms(hosts, mem=512):
    """Return the maximum number of virtual machines that can be
    created on the hosts"""
    total_vm = 0
    attr = get_CPU_RAM_FLOPS(hosts)
    for host in hosts:
        if isinstance(host, Host):
            host = host.address
        total_vm += floor(attr[host]['RAM'] / mem)
    return int(total_vm)


def get_vms_slot(vms, elements, slots, excluded_elements=None):
    """Return a slot with enough RAM and CPU """
    chosen_slot = None
    mem = vms[0]['mem']
    cpu = vms[0]['n_cpu']
    req_ram = sum([vm['mem'] for vm in vms])
    req_cpu = sum([vm['n_cpu'] for vm in vms]) / 3
    logger.debug('RAM %s CPU %s', req_ram, req_cpu)

    for element in excluded_elements:
        if element in get_g5k_sites():
            excluded_elements += [cluster for cluster
                                  in get_site_clusters(element)
                                  if cluster not in excluded_elements]

    if 'grid5000' in elements:
        clusters = [cluster for cluster in get_g5k_clusters()
                    if cluster not in excluded_elements
                    and get_cluster_site not in excluded_elements]
    else:
        clusters = [element for element in elements
                    if element in get_g5k_clusters()
                    and element not in excluded_elements]
        for element in elements:
            if element in get_g5k_sites():
                clusters += [cluster
                    for cluster in get_site_clusters(element)
                        if cluster not in clusters
                        and cluster not in excluded_elements]

    for slot in slots:
        hosts = []
        for element in slot[2]:
            if str(element) in clusters:
                n_hosts = slot[2][element]
                for i in range(n_hosts):
                    hosts.append(Host(str(element + '-1.' + \
                            get_cluster_site(element) + '.grid5000.fr')))
        attr = get_CPU_RAM_FLOPS(hosts)['TOTAL']

        if attr['CPU'] > req_cpu and attr['RAM'] > req_ram:
            chosen_slot = slot
            break
        del hosts[:]

    if chosen_slot is None:
        return None, None

    resources_needed = {}
    resources_available = chosen_slot[2]
    logger.debug('resources available' + pformat(resources_available))
    iter_clusters = cycle(clusters)
    while req_ram > 0 or req_cpu > 0:
        cluster = iter_clusters.next()
        if resources_available[cluster] == 0:
            clusters.remove(cluster)
            iter_clusters = cycle(clusters)
        else:
            host = cluster + '-1'
            attr = get_CPU_RAM_FLOPS([host])
            resources_available[cluster] -= 1
            req_ram -= float(attr[host]['RAM'] / mem) * mem
            req_cpu -= float(attr[host]['CPU'] / cpu) * cpu

            if cluster not in resources_needed:
                resources_needed[cluster] = 0
            resources_needed[cluster] += 1

    if 'kavlan' in elements:
        resources_needed['kavlan'] = 1

    logger.debug('resources needed' + pformat(resources_needed))
    return chosen_slot[0], distribute_hosts(chosen_slot[2], resources_needed,
                                            excluded_elements)
