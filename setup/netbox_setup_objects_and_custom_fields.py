#!/usr/bin/env python3
import argparse
import yaml

# adapted from sol1 implementation
from helpers.netbox_objects import __netbox_make_slug, NetBoxCustomFields, NetBoxCustomFieldChoiceSets, NetBoxClusterTypes, NetBoxClusters

from helpers.netbox_proxmox_api import NetBoxProxmoxAPIHelper


def get_arguments():
    # Initialize the parser
    parser = argparse.ArgumentParser(description="Import NetBox and Proxmox Configurations")

    # Add arguments for URL and Token
    parser.add_argument("--config", required=True, help="YAML file containing the configuration")
    parser.add_argument("--debug", action='store_true', default=False, help="Enable debug (verbose) output")

    # Parse the arguments
    args = parser.parse_args()

    # Return the parsed arguments
    return args


def create_custom_field_choice_sets_proxmox_vm_templates(proxmox_api_obj, nb_options: dict):
    proxmox_vm_templates = proxmox_api_obj.proxmox_get_vm_templates()
    extra_choices = []

    if proxmox_vm_templates:
        for k, v in proxmox_vm_templates.items():
            extra_choices.append([str(k), v])
    else:
        extra_choices.append([str(-1), 'proxmox-vm-template-stub'])

    ncfcs = NetBoxCustomFieldChoiceSets(netbox_url, netbox_api_token, nb_options, {'name': 'proxmox-vm-templates', 'extra_choices': extra_choices})
    return dict(ncfcs.obj)['id']


def create_custom_field_choice_sets_proxmox_vm_storage(proxmox_api_obj, nb_options: dict):
    proxmox_api_obj.proxmox_get_vm_storage_volumes()
    print(proxmox_api_obj.proxmox_storage_volumes)

    extra_choices = []

    for psv in proxmox_api_obj.proxmox_storage_volumes:
        extra_choices.append([psv, psv])

    ncfcs = NetBoxCustomFieldChoiceSets(netbox_url, netbox_api_token, nb_options, {'name': 'proxmox-vm-storage', 'extra_choices': extra_choices})
    return dict(ncfcs.obj)['id']


def create_custom_field_choice_sets_proxmox_lxc_templates(proxmox_api_obj):
    extra_choices = []

    for proxmox_node in proxmox_api_obj.proxmox_nodes:
        proxmox_api_obj.proxmox_get_lxc_templates(proxmox_node)

    proxmox_lxc_templates = proxmox_api_obj.proxmox_lxc_templates

    if proxmox_lxc_templates:
        for psv in proxmox_lxc_templates:
            extra_choices.append([psv, proxmox_lxc_templates[psv]])

    else:
        extra_choices.append(['placeholder-lxc-template', 'proxmox-lxc-templates-stub'])

    ncfcs = NetBoxCustomFieldChoiceSets(netbox_url, netbox_api_token, {'name': 'proxmox-lxc-templates', 'extra_choices': extra_choices})
    return dict(ncfcs.obj)['id']


def create_custom_field_choice_sets_proxmox_vm_cluster_nodes(proxmox_api_obj, nb_options: dict):
    extra_choices = []

    # get proxmox nodes
    # proxmox_api_obj.get_proxmox_nodes()
    proxmox_cluster_nodes = proxmox_api_obj.proxmox_nodes

    for pcn in proxmox_cluster_nodes:
        extra_choices.append([pcn, pcn])

    ncfcs = NetBoxCustomFieldChoiceSets(netbox_url, netbox_api_token, nb_options, {'name': 'proxmox-cluster-nodes', 'extra_choices': extra_choices})
    return dict(ncfcs.obj)['id']


def create_custom_field_choice_sets_proxmox_vm_type(proxmox_api_obj, nb_options: dict):
    extra_choices = []

    proxmox_vm_types = {
        'vm': 'Virtual Machine',
        'lxc': 'LXC Container'
    }

    for proxmox_vm_type in proxmox_vm_types:
        extra_choices.append([proxmox_vm_type, proxmox_vm_types[proxmox_vm_type]])

    ncfcs = NetBoxCustomFieldChoiceSets(netbox_url, netbox_api_token, nb_options, {'name': 'proxmox-vm-type', 'extra_choices': extra_choices})
    return dict(ncfcs.obj)['id']


def create_custom_field(netbox_url=None, netbox_api_token=None, nb_options = {}, name=None, label=None, choice_set_id=0, default=None):
    weight = 100
    description = ''

    if name in ['proxmox_lxc_template']:
        group_name = 'Proxmox LXC'
    elif name in ['proxmox_node', 'proxmox_vmid', 'proxmox_vm_storage', 'proxmox_vm_type', 'proxmox_public_ssh_key']:
        group_name = 'Proxmox (common)'

        if name == 'proxmox_vm_type':
            weight = 200
        elif name == 'proxmox_vmid':
            weight = 300
        elif name == 'proxmox_vm_storage':
            weight = 400
        elif name == 'proxmox_public_ssh_key':
            weight = 500
    else:
        group_name = 'Proxmox VM'

    if name in ['proxmox_node', 'proxmox_vm_storage', 'proxmox_vm_template', 'proxmox_lxc_template', 'proxmox_vm_type']:
        object_types = ['virtualization.virtualmachine']
        input_type = {'value': 'select', 'label': 'Selection'}
    elif name in ['proxmox_disk_storage_volume']:
        object_types = ['virtualization.virtualdisk']
        input_type = {'value': 'select', 'label': 'Selection'}
    elif name in ['proxmox_public_ssh_key']:
        object_types = ['virtualization.virtualmachine']
        input_type = {'value': 'longtext', 'label': 'Text (long)'}
        description = 'For LXC (containers), you MUST add a SSH public key BEFORE you create the VM in NetBox'
    elif name in ['proxmox_vmid']:
        object_types = ['virtualization.virtualmachine']
        input_type = {'value': 'text', 'label': 'Text'}
    elif name in ['proxmox_is_lxc_container']:
        object_types = ['virtualization.virtualmachine']
        input_type = {'value': "boolean", 'label': 'Boolean (true/false)'}

    if input_type['value'] == 'select':
        nbcf = NetBoxCustomFields(netbox_url, netbox_api_token, nb_options,
                                {'weight': weight, 
                                 #'filter_logic': {'value': 'loose', 'label': 'Loose'},
                                 'filter_logic': 'disabled',
                                 'search_weight': 1000,
                                'object_types': object_types,
                                'type': input_type['value'],
                                'group_name': group_name,
                                'name': name,
                                'label': label,
                                'choice_set': choice_set_id,
                                'default': default})
    elif input_type['value'] == 'text':
        nbcf = NetBoxCustomFields(netbox_url, netbox_api_token, nb_options,
                                {'weight': weight,
                                 'filter_logic': 'disabled',
                                 'search_weight': 1000,
                                'object_types': object_types,
                                'type': input_type['value'],
                                'group_name': group_name,
                                'name': name,
                                'label': label})
    elif input_type['value'] == 'longtext':
        nbcf = NetBoxCustomFields(netbox_url, netbox_api_token, nb_options,
                                {'weight': weight,
                                 'filter_logic': 'disabled',
                                 'search_weight': 1000,
                                'object_types': object_types,
                                'type': input_type['value'],
                                'group_name': group_name,
                                'name': name,
                                'label': label,
                                'description': description})
    elif input_type['value'] == 'boolean':
        nbcf = NetBoxCustomFields(netbox_url, netbox_api_token, nb_options,
                                {'weight': weight,
                                 'filter_logic': 'disabled',
                                 'search_weight': 1000,
                                'object_types': object_types,
                                'type': input_type['value'],
                                'group_name': group_name,
                                'name': name,
                                'label': label,
                                'required': True,
                                'default': False,
                                'label': label})
    
    return dict(nbcf.obj)['id']


if __name__ == "__main__":
    default_netbox_proxmox_name = 'Proxmox'
    default_netbox_cluster_role = default_netbox_proxmox_name
    default_netbox_cluster_name = 'proxmox-ve'
    default_netbox_vm_role = 'Proxmox VM'
    default_netbox_lxc_role = 'Proxmox LXC'
    create_vms_templates = False
    create_lxc_templates = False
    netbox_field_choice_sets_vms_templates_id = 0
    netbox_field_choice_sets_lxc_templates_id = 0

    args = get_arguments()

    app_config_file = args.config
    DEBUG = args.debug

    with open(app_config_file) as yaml_cfg:
        try:
            app_config = yaml.safe_load(yaml_cfg)
        except yaml.YAMLError as exc:
            raise ValueError(exc)
        except IOError as ioe:
            raise ValueError(ioe)

    netbox_url = f"{app_config['netbox_api_config']['api_proto']}://{app_config['netbox_api_config']['api_host']}:{app_config['netbox_api_config']['api_port']}/"
    netbox_api_token = f"{app_config['netbox_api_config']['api_token']}"
    nb_options = {}

    if 'verify_ssl' in app_config['netbox_api_config']:
        nb_options['verify_ssl'] = app_config['netbox_api_config']['verify_ssl']
    else:
        nb_options['verify_ssl'] = False

    if 'branch' in app_config['netbox']:
        branch_name = app_config['netbox']['branch']

        nb_options['branch'] = branch_name

        branch_timeout = 0
        if 'branch_timeout' in app_config['netbox']:
            branch_timeout = int(app_config['netbox']['branch_timeout'])

        nb_options['branch_timeout'] = branch_timeout

    nb_options['debug'] = DEBUG


    # init NetBox Proxmox API integration
    p = NetBoxProxmoxAPIHelper(app_config)
    p.debug = nb_options['debug']

    # setup defaults and override from config values later
    proxmox_cluster_name = default_netbox_cluster_name
    vm_cluster_role = default_netbox_cluster_role
    vm_role = default_netbox_vm_role
    lxc_role = default_netbox_lxc_role

    if 'proxmox' in app_config:
        if 'cluster_name' in app_config['proxmox']:
            proxmox_cluster_name = app_config['proxmox']['cluster_name']

        if 'create_vms_templates' in app_config['proxmox'] and app_config['proxmox']['create_vms_templates']:
            create_vms_templates = True

        if 'create_lxc_templates' in app_config['proxmox'] and app_config['proxmox']['create_lxc_templates']:
            create_lxc_templates = True

    if 'netbox' in app_config:
        if 'cluster_role' in app_config['netbox']:
            vm_cluster_role = app_config['netbox']['cluster_role']

        if 'vm_role' in app_config['netbox']:
            vm_role = app_config['netbox']['vm_role']

        if 'lxc_role' in app_config['netbox']:
            lxc_role = app_config['netbox']['lxc_role']

    # vm clusters and types
    nbct = NetBoxClusterTypes(netbox_url, netbox_api_token, nb_options, {'name': vm_cluster_role, 'slug': __netbox_make_slug(vm_cluster_role)})
    netbox_cluster_type_id = dict(nbct.obj)['id']

    nbc = NetBoxClusters(netbox_url, netbox_api_token, nb_options, {'name': proxmox_cluster_name, 'type': netbox_cluster_type_id, 'status': 'active'})
    netbox_cluster_id = dict(nbc.obj)['id']

    # custom field choice sets
    if create_vms_templates and len(p.proxmox_vm_templates.keys()) > 0:
        netbox_field_choice_sets_vms_templates_id = create_custom_field_choice_sets_proxmox_vm_templates(p, nb_options)

    netbox_field_choice_sets_vm_storage_volumes_id = create_custom_field_choice_sets_proxmox_vm_storage(p, nb_options)

    if create_lxc_templates:
        for n in p.proxmox_nodes:
            p.proxmox_get_lxc_templates(n)

        if len(p.proxmox_lxc_templates.keys()) > 0:
            netbox_field_choice_sets_lxc_templates_id = create_custom_field_choice_sets_proxmox_lxc_templates(p)

    netbox_field_choice_sets_proxmox_nodes_id = create_custom_field_choice_sets_proxmox_vm_cluster_nodes(p, nb_options)

    netbox_field_choice_sets_proxmox_vm_types_id = create_custom_field_choice_sets_proxmox_vm_type(p, nb_options)

    # custom fields

    # VM template id
    if create_vms_templates and len(p.proxmox_vm_templates.keys()) > 0:
        if netbox_field_choice_sets_vms_templates_id > 0:
            custom_field_vms_template_id = create_custom_field(netbox_url, netbox_api_token, nb_options, 'proxmox_vm_template', 'Proxmox VM Template', netbox_field_choice_sets_vms_templates_id, str(min(p.proxmox_vm_templates.keys())))

    # VM proxmox node id
    # NODES {'pxmx-n1': {'ip': '192.168.71.3', 'online': 1, 'version': 'Proxmox-8.4.1-2a5fa54a8503f96d'}, 'pxmx-n2': {'ip': '192.168.71.4', 'online': 1, 'version': 'Proxmox-8.4.1-2a5fa54a8503f96d'}}
    custom_field_proxmox_node_id = create_custom_field(netbox_url, netbox_api_token, nb_options, 'proxmox_node', 'Proxmox node', netbox_field_choice_sets_proxmox_nodes_id, list(p.proxmox_nodes.keys())[0])

    # proxmox_vmid
    custom_field_proxmox_vm_id = create_custom_field(netbox_url, netbox_api_token, nb_options, 'proxmox_vmid', 'Proxmox Virtual machine ID (vmid)')

    # proxmox_public_ssh_key
    custom_field_proxmox_public_ssh_key_id = create_custom_field(netbox_url, netbox_api_token, nb_options, 'proxmox_public_ssh_key', 'Proxmox public SSH key')

    # proxmox_disk_storage_volume
    custom_field_proxmox_disk_storage_volume_id = create_custom_field(netbox_url, netbox_api_token, nb_options, 'proxmox_disk_storage_volume', 'Proxmox Disk Storage Volume', netbox_field_choice_sets_vm_storage_volumes_id, p.proxmox_storage_volumes[0])

    # proxmox_vm_storage
    custom_field_proxmox_disk_storage_volume_id = create_custom_field(netbox_url, netbox_api_token, nb_options, 'proxmox_vm_storage', 'Proxmox VM Storage', netbox_field_choice_sets_vm_storage_volumes_id, p.proxmox_storage_volumes[0])

    # proxmox_vm_type
    custom_field_proxmox_vm_type = create_custom_field(netbox_url, netbox_api_token, nb_options, 'proxmox_vm_type', 'Proxmox VM Type', netbox_field_choice_sets_proxmox_vm_types_id, 'vm')

    # proxmox_lxc_template
    if create_lxc_templates and len(p.proxmox_lxc_templates.keys()) > 0:
        if netbox_field_choice_sets_lxc_templates_id > 0:
            custom_field_lxc_template_id = create_custom_field(netbox_url, netbox_api_token, nb_options, 'proxmox_lxc_template', 'Proxmox LXC Template', netbox_field_choice_sets_lxc_templates_id, str(min(p.proxmox_lxc_templates.keys())))
