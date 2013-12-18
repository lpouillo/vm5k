from config import default_vm
from deployment import distribute_vms, prettify, vm5k_deployment, \
    get_oar_job_vm5k_resources, get_kavlan_ip_mac, get_max_vms, \
    get_oargrid_job_vm5k_resources, get_vms_slot, print_step
from actions import  define_vms, install_vms, create_disks, destroy_vms, list_vm, \
    start_vms, wait_vms_have_started, create_disks_on_hosts, show_vms

