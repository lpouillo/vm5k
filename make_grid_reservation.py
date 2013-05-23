#!/usr/bin/env python
#-*- coding: utf-8 -*-

import time as T, datetime as DT, execo.time_utils as EXT
from pprint import pprint, pformat
from operator import itemgetter
from execo import configuration, logger
from itertools import cycle
from execo.log import set_style
import xml.etree.ElementTree as ET
from execo_g5k.oar import format_oar_date, oar_duration_to_seconds
from execo_g5k import OarSubmission, oargridsub, get_oargrid_job_nodes, wait_oargrid_job_start, get_oargrid_job_oar_jobs, get_oar_job_kavlan, oargriddel 
from execo_g5k.oargrid import get_oargridsub_commandline
from execo_g5k.api_utils import get_cluster_site, get_g5k_sites, get_g5k_clusters, get_resource_attributes, get_host_attributes, get_cluster_attributes, get_site_clusters
from execo_g5k.planning import Planning
#from execo_g5k.vmutils import *
from setup_cluster import get_clusters

logger.setLevel('INFO')

n_vm = 1000
walltime = '3:00:00'
oargridsub_opts = '-t deploy'
kavlan_site = 'toulouse'

tree = ET.parse('vm_default_template.xml')
root = tree.getroot()

vm_ram_size = int(root.get('mem'))

required_ram = n_vm * vm_ram_size

logger.info('Gathering the list of clusters with virtualization technology and kavlan')
clusters = get_clusters(virt = True, kavlan = True)
logger.warn('REMOVNG STREMI BECAUSE KAVLAN GLOBAL DOESN\'T WORK, see https://intranet.grid5000.fr/bugzilla/show_bug.cgi?id=4634')
clusters.remove('stremi')
logger.warn('REMOVNG LILLE CLUSTERS BECAUSE DEPLOYMENT DOESN\'T WORK IN KAVLAN')
clusters.remove('chinqchint')
clusters.remove('chimint')
clusters.remove('chirloute')

logger.info('Gathering the RAM size of a node for each cluster')
clusters_ram = { cluster: get_host_attributes(cluster+'-1')['main_memory']['ram_size']/10**6 for cluster in clusters  }
logger.info(' '.join( [ cluster+': '+str(ram)+'MB' for cluster, ram in clusters_ram.iteritems() ] ))

logger.info('Finding the free resources for the clusters %s', ', '.join([cluster for cluster in clusters]))
starttime = T.time()
endtime = starttime + EXT.timedelta_to_seconds(DT.timedelta(days = 2))

planning = Planning( clusters, starttime, endtime )

planning.compute_slots()
planning.draw_max_nodes(save = True)

slots_ok = []
for slot, resources in planning.slots.iteritems():
    slot_ram = 0
    slot_node = 0 
    for resource, n_node in resources.iteritems():
        if resource in clusters:
            slot_ram += n_node * clusters_ram[resource]
            slot_node += n_node    
    if required_ram < slot_ram and slot[1]-slot[0] > oar_duration_to_seconds(walltime):
        slots_ok.append(slot)

slots_ok.sort()

slot = {}
tmp_slot = planning.slots[slots_ok[0]]
for res, n_nodes in tmp_slot.iteritems():
    if res in clusters and n_nodes > 0:
        slot[res] = n_nodes



cluster_nodes = { cluster:0 for cluster in slot.iterkeys()}

iter_cluster = cycle(slot.iterkeys())

cluster = iter_cluster.next()
node_ram = 0
for i_vm in range(n_vm):
    node_ram += vm_ram_size
    if node_ram + vm_ram_size > clusters_ram[cluster]:            
        node_ram = 0
        cluster_nodes[cluster] += 1
        cluster = iter_cluster.next()
        while cluster_nodes[cluster] >= slot[cluster]:
            cluster = iter_cluster.next()
        


print 'slot', slot    
print 'ram', clusters_ram

slot_ram = 0
for cluster, n_nodes in cluster_nodes.iteritems():
    slot_ram += n_nodes * clusters_ram[cluster]
print required_ram, slot_ram

print cluster_nodes

sites =[]
total_nodes = 0
for cluster, n_node in cluster_nodes.iteritems():
    total_nodes += n_node
    site = get_cluster_site(cluster)
    if site not in sites:
        sites.append(get_cluster_site(cluster))
print total_nodes
print sites



subs = []
for site in sites:
    sub_resources=''
    if site == kavlan_site:
        sub_resources="{type=\\'kavlan-global\\'}/vlan=1+"
        getkavlan = False
    for cluster in get_site_clusters(site):
        if cluster_nodes.has_key(cluster):
            sub_resources += "{cluster=\\'"+cluster+"\\'}/nodes="+str(cluster_nodes[cluster])+'+'
    if sub_resources != '':
        subs.append((OarSubmission(resources=sub_resources[:-1]),site))

print format_oar_date(slots_ok[0][0])
#print subs


print get_oargridsub_commandline(subs, walltime = walltime, additional_options = oargridsub_opts,
                                 reservation_date = format_oar_date(slots_ok[0][0]))


(oargrid_job_id, _) = oargridsub(subs, walltime = walltime, additional_options = oargridsub_opts,
                                 reservation_date = format_oar_date(slots_ok[0][0]))


print oargrid_job_id
exit()

#if oargrid_job_id is not None:
#    try:
#        logger.info('Waiting the job to start')
#        wait_oargrid_job_start( oargrid_job_id )
#        
#        logger.info('Getting the network parameters')
#        subjobs = get_oargrid_job_oar_jobs(oargrid_job_id)
#        for subjob in subjobs:
#            logger.info('Looking for KaVLAN on site: %s ', subjob[1])
#            test_vlan = get_oar_job_kavlan(subjob[0], subjob[1])
#            if test_vlan is not None: 
#                kavlan_id = test_vlan
#                kavlan_frontend = subjob[1]+'.grid5000.fr'
#                kavlan_job = subjob[0]
#                logger.info('KaVLAN found on site: %s with id %s',kavlan_frontend,kavlan_id)
#                break
#       
#        
#        logger.info('Getting the list of hosts')
#        hosts = get_oargrid_job_nodes( oargrid_job_id )
#        logger.info(' %s', ", ".join( [set_style(host.address, 'host') for host in hosts] ))
#        logger.info(hosts)
#        
#
#        setup_hosts = G5K_Virsh_Deployment(hosts = hosts, kavlan = kavlan_id)
#        #setup_hosts.deploy_hosts()
#        setup_hosts.upgrade_hosts()
#        #setup_hosts.install_packages()
#        
#
#    finally:        
#        for host in hosts:
#            print list_vm(host)
##        logger.info('Deleting job ...'+str(oargrid_job_id))
##        oargriddel( [oargrid_job_id] )
##    
##logger.setLevel('INFO')
##logger.info('Determining clusters with %s and %s from G5K API:',
##             set_style('Virtualization', 'user3'), set_style('KaVLAN', 'user3'))
##clusters = get_clusters( virt = True, kavlan = True)
##logger.info('%s', ', '.join([set_style(cluster,  'user1') for cluster in clusters] ))
##
##
##logger.info('Finding the first slot with %s nodes available on the selected clusters', set_style(n_nodes, 'user3'), )
##resources = { cluster: 0 for cluster in clusters }
##starttime = T.time()+ ET.timedelta_to_seconds(DT.timedelta(minutes = 1))
##endtime = starttime + ET.timedelta_to_seconds(DT.timedelta(days = 1))
##planning = Planning(clusters, starttime, endtime)
##planning.compute_slots()
##planning.draw_max_nodes(save = True)
##
##slots_ok = []
##for slot, value in planning.slots.iteritems():
##    if value['grid5000.fr'] > n_nodes and int(slot[1])-int(slot[0]) > 7200:
##        slots_ok.append( [slot[0], slot[1], value ])
##slots_ok = sorted(slots_ok, key = itemgetter(0))
##starttime = slots_ok[0][0]
##g5k_clusters = get_g5k_clusters()
##
##nodes_available = {}
##for cluster, cl_nodes in slots_ok[0][2].iteritems(): 
##    if cluster in g5k_clusters:
##        nodes_available[cluster] = cl_nodes
##logger.info('%s \n%s', format_oar_date(starttime), ', '.join([set_style(cluster,  'user1')+': '+str(n_nodes) for cluster, n_nodes in nodes_available.iteritems()] ))
#
#    
#    
#    
#
#
#exit()
#
#
#logger.info('Distributing the %s nodes on the clusters:', set_style(n_nodes, 'user3'))
#total_nodes = 0
#
#while total_nodes < n_nodes:
#    for cluster in clusters:
#        resources[cluster] += 1
#        total_nodes +=1
#        if total_nodes == n_nodes:
#            break
#logger.info('%s', ', '.join([ set_style(cluster,  'user1')+': '+str(n_nodes) for cluster, n_nodes in resources.iteritems()] ))
#    
#
#    
#
#
#
#
# 
