from config import default_vm
from deployment import vm5k_deployment
from actions import define_vms, install_vms, create_disks, destroy_vms, \
    list_vm, start_vms, wait_vms_have_started, create_disks_all_hosts, \
    show_vms, rm_qcow2_disks, distribute_vms, activate_vms
from services import dnsmasq_server
from utils import prettify, get_max_vms, get_vms_slot, print_step, \
    get_oargrid_job_vm5k_resources, get_oar_job_vm5k_resources, \
    get_CPU_RAM_FLOPS
