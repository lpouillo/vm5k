#!/usr/bin/env python
#-*- coding: utf-8 -*-

from pprint import pprint, pformat
from operator import itemgetter
from execo import configuration, logger
from execo.log import set_style
from execo_g5k.oar import format_oar_date
from execo_g5k import OarSubmission, oargridsub, get_oargrid_job_nodes, wait_oargrid_job_start, get_oargrid_job_oar_jobs, get_oar_job_kavlan, oargriddel
from execo_g5k.api_utils import get_cluster_site, get_g5k_sites, get_g5k_clusters, get_resource_attributes, get_host_attributes, get_cluster_attributes, get_site_clusters
from execo_g5k.planning import *
from execo_g5k.vmutils import *
from execo_g5k.vmutils.setup_cluster import G5K_Virsh_Deployment

logger.setLevel('INFO')

walltime = '3:00:00'
n_nodes = 2
oargridsub_opts = '-t deploy'

clusters = [ 'pastel', 'sol', 'suno', 'graphene',  'paradent', 'granduc' ]
print clusters
sites =[]
for cluster in clusters:
    cl_site = get_cluster_site(cluster)
    if cl_site not in sites:
        sites.append(cl_site)
print sites
resources = { cluster: n_nodes for cluster in clusters }
subs = []
for site in sites:
    sub_resources=''
    if site == 'sophia':
        sub_resources="{type=\\'kavlan-global\\'}/vlan=1+"
        getkavlan = False
    for cluster in get_site_clusters(site):
        if resources.has_key(cluster):
            sub_resources += "{cluster=\\'"+cluster+"\\'}/nodes="+str(resources[cluster])+'+'
    subs.append((OarSubmission(resources=sub_resources[:-1]),site))

(oargrid_job_id, _) = oargridsub(subs, walltime = walltime, additional_options = oargridsub_opts)


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
