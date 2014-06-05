#!/usr/bin/env python
from xml.etree.ElementTree import parse
from json import dump

tree = parse('state.xml')
state = tree.getroot()

def get_load_color(load):
    """ """
    print load
    print type(load)
    n = load // 10
    R = 255 * n / 10
    G = (255 * (10-n))/10; 
    B=0
    print R, G, B
    return '#%02x%02x%02x' % (int(R), int(G), int(B))
    
vm5k = {"name": 'vm5k', "children": [], "color": "#FFA08D", "size": 20}

for el_site in state.findall('./site'):
    site = {"name": el_site.get('id'), 
            "children": [], 
            "color": "#FFFDBB",
            "size": 10}
    for el_cluster in el_site.findall('./cluster'):
        cluster = {"name": el_cluster.get('id'), 
                   "children": [],
                   "color": "#BBBDFF", 
                   "size": 5}
        for el_host in el_cluster.findall('./host'):
            host = {"name": el_host.get('id').split('-', 2)[1], 
                    "children": [],
                    "color": "pink",
                    "size": 4}
            cluster['children'].append(host)
            for el_vm in el_host.findall('./vm'):
                load = el_vm.get('load')
                host['children'].append({"name": "", 
                            "color": get_load_color(float(load)), 
                            "size": 2.5})
        site['children'].append(cluster)
        
    vm5k['children'].append(site)


from pprint import pprint
pprint(vm5k)


with open('vm5k.json', 'w') as outfile:
  dump(vm5k, outfile)