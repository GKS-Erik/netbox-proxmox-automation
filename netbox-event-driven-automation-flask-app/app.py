import os
import logging
import json
import yaml

from datetime import datetime

# adapted from: https://majornetwork.net/2019/10/webhook-listener-for-netbox/

from helpers.netbox_proxmox import NetBoxProxmoxHelper, NetBoxProxmoxHelperVM, NetBoxProxmoxHelperLXC, NetBoxProxmoxHelperMigrate

from flask import Flask, Response, request, jsonify
from flask_restx import Api, Resource, fields

VERSION = '2025.11.01'

app_config_file = 'app_config.yml'

with open(app_config_file) as yaml_cfg:
    try:
        app_config = yaml.safe_load(yaml_cfg)
    except yaml.YAMLError as exc:
        print(exc)

if not 'netbox_webhook_name' in app_config:
    raise ValueError(f"'netbox_webhook_name' missing in {app_config_file}")

app = Flask(__name__)
api = Api(app, version=VERSION, title="NetBox-Proxmox Webhook Listener",
        description="NetBox-Proxmox Webhook Listener")
ns = api.namespace(app_config['netbox_webhook_name'])

APP_NAME = "netbox-proxmox-webhook-listener"

DEBUG = app.debug

logger = logging.getLogger(APP_NAME)
if DEBUG:
    logger.setLevel(logging.DEBUG)
else:
  logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
file_logging = logging.FileHandler("{}.log".format(APP_NAME))
file_logging.setFormatter(formatter)
logger.addHandler(file_logging)

stream_logging = logging.StreamHandler()
stream_logging.setFormatter(formatter)
logger.addHandler(stream_logging)

logger.debug("Pew pew")

webhook_request = api.model("Webhook request from NetBox", {
    'username': fields.String,
    'data': fields.Raw(description="Object data from NetBox"),
    'event': fields.String,
    'timestamp': fields.String,
    'model': fields.String,
    'request_id': fields.String,
})

# For session logging, c/o sol1
session = {
  'name': "netbox-webhook-flask-app",
  'version': VERSION,
  'version_lastrun': VERSION,
  'server_start': "",
  'status': {
    'requests': 0,
    'last_called': ""
  },
}


@ns.route("/status/", methods=['GET'])
class WebhookListener(Resource):
    @ns.expect(webhook_request)

    def get(self):
        _session = session.copy()
        _session['version_lastrun'] = VERSION
        _session['status']['requests'] += 1
        _session['status']['last_called'] = datetime.now()
        sanitized_full_path = request.full_path.replace('\r\n', '').replace('\n', '')
        sanitized_remote_addr = request.remote_addr.replace('\r\n', '').replace('\n', '') if request.remote_addr else 'Unknown'
        sanitized_data = request.get_data(as_text=True).replace('\r\n', '').replace('\n', '') if request.get_data() else ''
        logger.info(f"{sanitized_full_path}, {sanitized_remote_addr}, Status request with data {sanitized_data}")
        return jsonify(_session)


# For handling event rules
@ns.route("/")
class WebhookListener(Resource):
    @ns.expect(webhook_request)
    def post(self):
        try:
            webhook_json_data = request.json
        except:
            webhook_json_data = {}

        sanitized_data = json.dumps(webhook_json_data, separators = (',', ':'))
        logger.info("User-provided data: %s", sanitized_data)

        if not webhook_json_data or "event" not in webhook_json_data or "data" not in webhook_json_data:
            logger.error("Invalid input")
            return {"result":"invalid input"}, 400

        event = webhook_json_data["event"]
        data = webhook_json_data["data"]

        if "snapshots" in webhook_json_data:
            snapshots = webhook_json_data["snapshots"]

        if "model" in webhook_json_data:
            model = webhook_json_data["model"]
        else:
            try:
                object_type = webhook_json_data["object_type"]
            except:
                logger.error("Attributes model or object_type missing from input")
                return {"result": "missing model/object_type"}, 400

            model = object_type.rsplit(".", 1)[-1]

        results = (500, {'result': 'Default error message (obviously something has gone wrong)'})

        if model == 'virtualmachine':
            if not 'device' in data:
                logger.error("Attribute device missing from input")
                return {"result":"Missing device (Proxmox node)"}, 400

            proxmox_node = data['device']

            if 'cluster' in data:
                cluster = data['cluster']

            if not 'proxmox_vm_type' in data['custom_fields'] or data['custom_fields']['proxmox_vm_type'] == 'vm':
                tc = NetBoxProxmoxHelperVM(app_config, proxmox_node, DEBUG)

                if data['status']['value'] == 'staged':
                    if event == 'created':
                        results = tc.proxmox_clone_vm(webhook_json_data)
                    elif event == 'updated':
                        results = tc.proxmox_update_vm_vcpus_and_memory(webhook_json_data)

                        if data['primary_ip'] and data['primary_ip']['address']:
                            results = tc.proxmox_set_ipconfig0(webhook_json_data)

                        if 'proxmox_public_ssh_key' in data['custom_fields'] and data['custom_fields']['proxmox_public_ssh_key']:
                            results = tc.proxmox_set_ssh_public_key(webhook_json_data)
                    elif event == 'deleted':
                        results = tc.proxmox_delete_vm(webhook_json_data)

                elif event == 'updated':
                    if data['status']['value'] == 'offline':
                        logger.debug('Stoppen met dat ding')
                        if (data['status']['value'] != snapshots['prechange']['status']) and (proxmox_node['id'] == snapshots['prechange']['device']):
                            results = tc.proxmox_stop_vm(webhook_json_data)

                        if proxmox_node['id'] != snapshots['prechange']['device']:
                            proxmox_vmid = int(data['serial'])
                            source_node = snapshots['prechange']['device']
                            target_node = proxmox_node

                            pxmx_migrate = NetBoxProxmoxHelperMigrate(app_config, None, DEBUG)

                            results = pxmx_migrate.migrate_vm(proxmox_vmid, source_node, target_node)

                    elif data['status']['value'] == 'active':
                        if (data['status']['value'] != snapshots['prechange']['status']) and (proxmox_node['id'] == snapshots['prechange']['device']):
                            results = tc.proxmox_start_vm(webhook_json_data)

                        if proxmox_node['id'] != snapshots['prechange']['device']:
                            proxmox_vmid = int(data['serial'])
                            source_node = snapshots['prechange']['device']
                            target_node = proxmox_node['id']

                            pxmx_migrate = NetBoxProxmoxHelperMigrate(app_config, None, DEBUG)

                            results = pxmx_migrate.migrate_vm(proxmox_vmid, source_node, target_node)
                    else:
                        results = (500, {'result': f"Unknown value {data['status']['value']}"})

                elif event == 'deleted':
                    results = tc.proxmox_delete_vm(webhook_json_data)

            elif data['custom_fields']['proxmox_vm_type'] == 'lxc':
                tc = NetBoxProxmoxHelperLXC(app_config, proxmox_node, DEBUG)

                if data['status']['value'] == 'staged':
                    logger.debug(f"LXC STAGED INPUT {data}", event)

                    if event == 'created':
                        results = tc.proxmox_create_lxc(webhook_json_data)

                    elif event == 'updated':
                        if data['primary_ip'] and data['primary_ip']['address']:
                            results = tc.proxmox_lxc_set_net0(webhook_json_data)

                        if (snapshots['prechange']['vcpus'] != snapshots['postchange']['vcpus']) or (snapshots['prechange']['memory'] != snapshots['postchange']['memory']):
                            results = tc.proxmox_update_lxc_vpus_and_memory(webhook_json_data)
                        else:
                            results = (200, {'result': 'No resources to change'})

                    elif event == 'deleted':
                        results = tc.proxmox_delete_lxc(webhook_json_data)

                elif event == 'updated':
                    if data['status']['value'] == 'offline':
                        results = tc.proxmox_stop_lxc(webhook_json_data)
                    elif data['status']['value'] == 'active':
                        results = tc.proxmox_start_lxc(webhook_json_data)
                    else:
                        results = (500, {'result': f"Unknown value {data['status']['value']}"})

                elif event == 'deleted':
                    results = tc.proxmox_delete_lxc(webhook_json_data)

                else:
                    results = (500, {'result': f"Unknown event: {event}"})

        elif model == 'virtualdisk':
            results = 500, {'result': 'Something has gone wrong with virtualdisk management'}
            is_lxc = False

            if data['name'] == 'rootfs':
                is_lxc = True

            logger.debug("HERE VIRTUALDISK", is_lxc)

            tcall = NetBoxProxmoxHelper(app_config, None, DEBUG)
            proxmox_node = tcall.netbox_get_proxmox_node_from_vm_id(data['virtual_machine']['id'])

            if is_lxc:
                logger.debug("change disk lxc")

                if event == 'updated':
                    if snapshots['prechange']['size'] != snapshots['postchange']['size']:
                        tc = NetBoxProxmoxHelperLXC(app_config, proxmox_node, DEBUG)
                        results = tc.proxmox_lxc_resize_disk(webhook_json_data)

                elif event == 'deleted':
                    results = 200, {'result': 'All good'}

            else:
                tc = NetBoxProxmoxHelperVM(app_config, proxmox_node, DEBUG)

                if event == 'created':
                    results = tc.proxmox_add_disk(webhook_json_data)
                elif event == 'updated':
                    results = tc.proxmox_resize_disk(webhook_json_data)
                elif event == 'deleted':
                    results = tc.proxmox_delete_disk(webhook_json_data)

        logger.debug("Results: %s", json.dumps(results))

        response = Response(
            json.dumps(results[1]),
            status = results[0],
            mimetype = 'application/json'
        )
        logger.debug(response)

        return response


if __name__ == "__main__":
    app.run(host="0.0.0.0")
