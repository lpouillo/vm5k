#!/usr/bin/env python



from xml.etree.ElementTree import parse
from execo_g5k.api_utils import get_g5k_sites, get_g5k_clusters
from execo import logger, sleep
try:
    import networkx as nx
    import matplotlib.pyplot as plt
except:
    pass


oargrid_job_id = 48206


def init_live_plot(xml):
    """Create  """
    print xml
    logger.info('Initializing Live plot')
    plt.figure(figsize=(15, 15))
    plt.ion()
    plt.show()
    sleep(10)

    exit()



tree = parse('/home/lolo/SRC/git/vm5k/examples/lyon_nancy_stremi.xml')
vm5k = tree.getroot()

#sites = [ site.id for site in vm5k.findall('./site') ]
#clusters = [ cluster.id for cluster in vm5k.findall('.//cluster') ]
#hosts = [ host.id for host in vm5k.findall('.//host') ]
#
#def _default_xml_value(key):
#    return default_vm[key] if key not in vm.attrib else vm.get(key)
#vms = []
#for vm in findall('.//vm'):
#    vms.append( {'id': vm.get('id'),
#            'n_cpu': _default_xml_value['n_cpu'],
#            'cpuset': _default_xml_value['cpuset'],
#            'mem': _default_xml_value['mem'],
#            'hdd': _default_xml_value['hdd'],
#            'backing_file': _default_xml_value['backing_file'],
#            'host': _default_xml_value['host'] } )

G=nx.Graph(name='deployment')

G.add_node('vm5k', attr_dict = dict(size=1400, color='blue'))
site_nodes = []
cluster_nodes = []
host_nodes = []
vm_nodes = []
job_nodes = []
for site in vm5k.findall('site'):
    site_nodes.append(site.get('id').upper())
    G.add_node(site.get('id').upper())
    G.add_edge('vm5k', site.get('id').upper())
    for cluster in site.findall('cluster'):
        cluster_nodes.append(cluster.get('id').title())
        G.add_nodes_from([(cluster.get('id'), dict(size=11,color='blue'))])
        G.add_edge(site.get('id'),cluster.get('id').title())
        for host in cluster.findall('host'):
            host_nodes.append(host.get('id'))
            G.add_node(host.get('id'))
            G.add_edge(cluster.get('id'),host.get('id'))
            for vm in host.findall('vm'):
                vm_nodes.append(vm.get('id'))
                G.add_node(vm.get('id'))
                G.add_edge(host.get('id'),vm.get('id'))

mapping = {}
sites = get_g5k_sites()
clusters = get_g5k_clusters()


for name in G.nodes():
    if name in sites:
        mapping[name] = name.upper()
    elif name in clusters:
        mapping[name] = name.title()
    elif 'vm' in name:
        mapping[name] = name
    else:
        mapping[name] = name

#     print labels
#     print pos
#     nx.draw_networkx_labels(G, pos, labels, font_size = 16)


G = nx.relabel_nodes(G, mapping)
pos = nx.graphviz_layout(G, prog='twopi')
#pos = nx.graphviz_layout(G, prog='neato')

#plt.figure(figsize=(len(vm_nodes)/4, len(vm_nodes)/4))
plt.figure(figsize=(15, 15))
plt.subplots_adjust(left=0, right=1, bottom=0, top=1)
plt.axis('equal')


nx.draw_networkx_nodes(G, pos,
                   node_size = 2000,
                   nodelist = ['vm5k'],
                   node_color = '#FF6363')
nx.draw_networkx_nodes(G, pos,
                   node_size = 1000,
                   nodelist = site_nodes,
                   node_color = '#9CF7BC')
nx.draw_networkx_nodes(G, pos,
                   node_size = 500,
                   nodelist = cluster_nodes,
                   node_color = '#BFDFF2')
nx.draw_networkx_nodes(G, pos,
                   node_size = 250,
                   nodelist = host_nodes,
                   node_color = '#F0F7BE')
nx.draw_networkx_nodes(G, pos,
                   node_size = 125,
                   nodelist = vm_nodes,
                   node_color = '#F5C9CD')
nx.draw_networkx_edges(G, pos, alpha=0.5, width=2)


labels = { n: n for n in ['vm5k'] + site_nodes + cluster_nodes + host_nodes }

nx.draw_networkx_labels(G, pos = pos, fontsize=2,
    labels = labels)

#pos = nx.graphviz_layout(G, prog="twopi")
#nx.draw_networkx_nodes(G,pos,node_size=1200,node_shape='o',node_color='0.75')
#nx.draw_networkx_edges(G,pos, width=2,edge_color='b')

## LABELS
#max_x = 0
#max_y = 0
#for x,y in pos.itervalues():
#    if max_x < x:
#        max_x = x
#    if max_y < y:
#        max_y = y
#offset = len(vm_nodes)/3
#pos_labels = {}
#for key in pos.keys():
#    x, y = pos[key]
#    print key, x, y
#    if key != 'vm5k':
#        if y > max_y/2:
#            pos_labels[key] = (x, y+offset)
#        else:
#            pos_labels[key] = (x, y-offset)
#    else:
#        pos_labels[key] = (x, y)
#



plt.savefig('test.png')