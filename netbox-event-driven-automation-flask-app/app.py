import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

import requests
from flask import Flask, jsonify, request
from flask_restx import Api, Resource, fields
from proxmoxer import ResourceException
from pynetbox.core.query import RequestError as NetBoxRequestError
from pydantic import ValidationError

from backends import BackendFactory
from backends.base import UnsupportedOperationError
from clients import GuestNotFoundError, NetBoxClient, ProxmoxClient, ProxmoxTaskError
from config import AppConfig, load_config
from logging_utils import log_payload
from models import parse_webhook
from services import NoTemplatesFoundError, StorageSyncService, TemplateSyncService
from services.vm_service import AutomationService

VERSION = "2026.08.20"
APP_NAME = "netbox-proxmox-webhook-listener"


def build_services(
    config: AppConfig,
    debug=False,
) -> tuple[AutomationService, TemplateSyncService, StorageSyncService]:
    proxmox = ProxmoxClient(config.proxmox_api_config, debug=debug)
    netbox = NetBoxClient(config.netbox_api_config, debug=debug)
    backends = BackendFactory(proxmox, netbox, config.proxmox_api_config)
    return (
        AutomationService(backends, netbox),
        TemplateSyncService(proxmox, netbox),
        StorageSyncService(proxmox, netbox),
    )


def build_service(config: AppConfig, debug=False) -> AutomationService:
    service, _, _ = build_services(config, debug)
    return service


def create_app(
    config: AppConfig | None = None,
    service: AutomationService | None = None,
    template_service: TemplateSyncService | None = None,
    storage_service: StorageSyncService | None = None,
) -> Flask:
    config_path = Path(
        os.environ.get("APP_CONFIG_FILE", Path(__file__).with_name("app_config.yml"))
    )
    config = config or load_config(config_path)
    flask_app = Flask(__name__)
    if service is None or template_service is None or storage_service is None:
        built_service, built_template_service, built_storage_service = build_services(
            config,
            debug=lambda: flask_app.debug,
        )
        service = service or built_service
        template_service = template_service or built_template_service
        storage_service = storage_service or built_storage_service
    api = Api(
        flask_app,
        version=VERSION,
        title="NetBox-Proxmox Webhook Listener",
        description="NetBox-Proxmox Webhook Listener",
    )
    namespace = api.namespace(config.netbox_webhook_name)
    logger = _configure_logging(config.log_level, flask_app.debug)

    template_service.sync_on_startup(
        config.netbox_api_config.proxmox_template_choice_set_name,
        logger,
    )
    storage_service.sync_on_startup(
        config.netbox_api_config.proxmox_vm_storage_choice_set_name,
        config.netbox_api_config.proxmox_lxc_storage_choice_set_name,
        logger,
    )

    @flask_app.before_request
    def apply_effective_log_level():
        # Flask CLI may enable debug after the application object is created.
        logger.setLevel(logging.DEBUG if flask_app.debug else getattr(logging, config.log_level))

    state = {
        "server_start": datetime.now(UTC),
        "requests": 0,
        "last_called": None,
    }
    state_lock = Lock()

    webhook_request = api.model(
        "Webhook request from NetBox",
        {
            "data": fields.Raw(required=True, description="Object data from NetBox"),
            "event": fields.String(required=True),
            "model": fields.String,
            "object_type": fields.String,
            "snapshots": fields.Raw,
        },
    )

    @namespace.route("/status/")
    class StatusResource(Resource):
        def get(self):
            with state_lock:
                state["requests"] += 1
                state["last_called"] = datetime.now(UTC)
                response = {
                    "name": APP_NAME,
                    "version": VERSION,
                    "server_start": state["server_start"].isoformat(),
                    "status": {
                        "requests": state["requests"],
                        "last_called": state["last_called"].isoformat(),
                    },
                }
            return jsonify(response)

    @namespace.route("/templates/sync/")
    class TemplateSyncResource(Resource):
        def post(self):
            choice_set_name = config.netbox_api_config.proxmox_template_choice_set_name
            logger.info("Synchronizing Proxmox templates to NetBox choice set %s", choice_set_name)
            try:
                result = template_service.sync(choice_set_name)
            except NoTemplatesFoundError as exc:
                logger.warning("Template synchronization skipped: %s", exc)
                return {"result": str(exc)}, 409
            except ResourceException as exc:
                message = getattr(exc, "content", str(exc))
                logger.exception("Proxmox API request failed during template synchronization")
                return {"result": message}, 502
            except (NetBoxRequestError, requests.RequestException) as exc:
                logger.exception("API request failed during template synchronization")
                return {"result": f"Template synchronization failed: {exc}"}, 502
            except Exception:
                logger.exception("Unexpected template synchronization error")
                return {"result": "Unexpected template synchronization error"}, 500

            action = "created" if result.created else "updated"
            return {
                "result": (
                    f"Choice set {result.choice_set_name} {action} with "
                    f"{result.template_count} Proxmox templates"
                ),
                "choice_set": result.choice_set_name,
                "template_count": result.template_count,
                "created": result.created,
            }, 200

    @namespace.route("/")
    class WebhookResource(Resource):
        @namespace.expect(webhook_request)
        def post(self):
            payload = request.get_json(silent=True)
            if payload is None:
                return {"result": "Request body must contain JSON"}, 400

            logger.info(
                "NetBox webhook received",
                extra={
                    "event": payload.get("event"),
                    "object_type": payload.get("object_type") or payload.get("model"),
                    "request_id": payload.get("request_id"),
                },
            )
            log_payload(
                logger,
                flask_app.debug and config.netbox_api_config.debug_payloads,
                "NetBox webhook payload",
                payload,
            )

            event = None
            try:
                event = parse_webhook(payload)
                results = service.handle(event)
            except ValidationError as exc:
                logger.warning("Invalid NetBox webhook: %s", exc)
                return {"result": "Invalid NetBox webhook", "errors": exc.errors()}, 400
            except (ValueError, LookupError, UnsupportedOperationError) as exc:
                logger.warning("Unable to process NetBox webhook: %s", exc)
                return {"result": str(exc)}, 409
            except (GuestNotFoundError, ProxmoxTaskError, TimeoutError) as exc:
                _mark_event_failed(service, event, logger)
                logger.error("Proxmox task failed: %s", exc)
                return {"result": str(exc)}, 502
            except ResourceException as exc:
                _mark_event_failed(service, event, logger)
                message = getattr(exc, "content", str(exc))
                logger.exception("Proxmox API request failed")
                return {"result": message}, 502
            except requests.RequestException as exc:
                _mark_event_failed(service, event, logger)
                logger.exception("API connection failed")
                return {"result": f"API connection failed: {exc}"}, 502
            except Exception:
                logger.exception("Unexpected webhook processing error")
                return {"result": "Unexpected webhook processing error"}, 500

            if not results:
                return {"result": "No operation required"}, 200
            return {
                "result": results[-1].message,
                "operations": [
                    {"operation": result.operation.value, "message": result.message}
                    for result in results
                ],
            }, 200

    return flask_app


def _configure_logging(configured_level: str, debug: bool) -> logging.Logger:
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG if debug else getattr(logging, configured_level))
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s"))
        logger.addHandler(handler)
    return logger


def _mark_event_failed(service: AutomationService, event, logger: logging.Logger) -> None:
    if event is None:
        return
    try:
        service.mark_failed(event)
    except Exception:
        logger.exception("Unable to mark NetBox VM as failed after Proxmox error")


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0")
