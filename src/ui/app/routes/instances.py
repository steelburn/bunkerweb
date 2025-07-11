from concurrent.futures import ThreadPoolExecutor, as_completed
from re import compile as re_compile
from threading import Thread
from time import time
from typing import Literal
from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app.dependencies import BW_CONFIG, BW_INSTANCES_UTILS, DATA, DB
from app.utils import flash

from app.models.instance import Instance
from app.routes.utils import handle_error, verify_data_in_form


instances = Blueprint("instances", __name__)

ACTIONS = {
    "reload": {"present": "Reloading", "past": "Reloaded"},
    "stop": {"present": "Stopping", "past": "Stopped"},
    "delete": {"present": "Deleting", "past": "Deleted"},
}


@instances.route("/instances", methods=["GET"])
@login_required
def instances_page():
    return render_template("instances.html", instances=BW_INSTANCES_UTILS.get_instances())


@instances.route("/instances/new", methods=["POST"])
@login_required
def instances_new():
    if DB.readonly:
        return handle_error("Database is in read-only mode", "instances")
    verify_data_in_form(
        data={"hostname": None},
        err_message="Missing instance hostname parameter on /instances/new.",
        redirect_url="instances",
        next=True,
    )
    verify_data_in_form(
        data={"name": None},
        err_message="Missing instance name parameter on /instances/new.",
        redirect_url="instances",
        next=True,
    )

    db_config = BW_CONFIG.get_config(global_only=True, methods=False, filtered_settings=("API_HTTP_PORT", "API_SERVER_NAME"))

    port = None
    hostname = request.form["hostname"].replace("http://", "").replace("https://", "").lower().split(":", 1)
    if len(hostname) == 2:
        port = hostname[1]
    hostname = hostname[0]

    domain_pattern = re_compile(r"^(?!.*\.\.)[^\s\/:]{1,256}$")
    if not domain_pattern.match(hostname):
        return handle_error(f"Invalid hostname: {hostname}. Please enter a valid domain.", "instances", True)

    instance = {
        "hostname": hostname,
        "name": request.form["name"],
        "port": port or db_config.get("API_HTTP_PORT", "5000"),
        "server_name": db_config.get("API_SERVER_NAME", "bwapi"),
        "method": "ui",
    }

    for db_instance in BW_INSTANCES_UTILS.get_instances():
        if db_instance.hostname == instance["hostname"]:
            return handle_error(f"The hostname {instance['hostname']} is already in use.", "instances", True)

    ret = DB.add_instance(**instance)
    if ret:
        return handle_error(f"Couldn't create the instance in the database: {ret}", "instances", True)

    flash(f"Instance {instance['hostname']} created successfully.")

    return redirect(url_for("loading", next=url_for("instances.instances_page"), message=f"Creating new instance {instance['hostname']}"))


@instances.route("/instances/<string:action>", methods=["POST"])
@login_required
def instances_action(action: Literal["ping", "reload", "stop", "delete"]):  # TODO: see if we can support start and restart
    if DB.readonly:
        return handle_error("Database is in read-only mode", "instances")

    verify_data_in_form(
        data={"instances": None},
        err_message=f"Missing instances parameter on /instances/{action}.",
        redirect_url="instances",
        next=True,
    )
    instances = request.form["instances"].split(",")
    if not instances:
        return handle_error(f"No instance{'s' if len(instances) > 1 else ''} selected.", "instances", True)
    DATA.load_from_file()

    if action == "ping":
        succeed = []
        failed = []

        def ping_instance(instance):
            ret = Instance.from_hostname(instance, DB)
            if not ret:
                return {"hostname": instance, "message": f"The instance {instance} does not exist."}
            ret = ret.ping()
            if ret[0].startswith("Can't"):
                return {"hostname": instance, "message": ret[0]}
            return instance

        with ThreadPoolExecutor() as executor:
            future_to_instance = {executor.submit(ping_instance, instance): instance for instance in instances}
            for future in as_completed(future_to_instance):
                instance = future.result()
                if isinstance(instance, dict):
                    failed.append(instance)
                    continue
                succeed.append(instance)

        return jsonify({"succeed": succeed, "failed": failed}), 200
    elif action == "delete":
        delete_instances = set()
        non_ui_instances = set()
        for instance in DB.get_instances():
            if instance["hostname"] in instances:
                if instance["method"] != "ui":
                    non_ui_instances.add(instance["hostname"])
                    continue
                delete_instances.add(instance["hostname"])

        for non_ui_instance in non_ui_instances:
            flash(f"Instance {non_ui_instance} is not a UI instance and will not be deleted.", "error")

        if not delete_instances:
            return handle_error(
                f"{'All selected instances' if len(delete_instances) > 1 else 'Selected instance'} could not be found or {'are not UI instances' if len(delete_instances) > 1 else 'is not an UI instance'}.",
                "instances",
                True,
            )

        ret = DB.delete_instances(delete_instances)
        if ret:
            return handle_error(f"Couldn't delete the instance{'s' if len(delete_instances) > 1 else ''} in the database: {ret}", "instances", True)
        flash(f"Instance{'s' if len(delete_instances) > 1 else ''} {', '.join(delete_instances)} Deleted successfully.")
    else:

        def execute_action(instance):
            ret = Instance.from_hostname(instance, DB)
            if not ret:
                DATA["TO_FLASH"].append({"content": f"The instance {instance} does not exist.", "type": "error"})
                return

            method = getattr(ret, action, None)
            if method is None or not callable(method):
                DATA["TO_FLASH"].append({"content": f"The instance {instance} does not have a {action} method.", "type": "error"})
                return

            ret = method()
            if ret.startswith("Can't"):
                DATA["TO_FLASH"].append({"content": ret, "type": "error"})
                return
            DATA["TO_FLASH"].append({"content": f"Instance {instance} {ACTIONS[action]['past']} successfully.", "type": "success"})

        def execute_actions(instances):
            DATA["RELOADING"] = True
            DATA["LAST_RELOAD"] = time()
            with ThreadPoolExecutor() as executor:
                executor.map(execute_action, instances)
            DATA["RELOADING"] = False

        Thread(target=execute_actions, args=(instances,)).start()

    return redirect(
        url_for(
            "loading",
            next=url_for("instances.instances_page"),
            message=(f"{ACTIONS[action]['present']} instance{'s' if len(instances) > 1 else ''} {', '.join(instances)}"),
        )
    )
