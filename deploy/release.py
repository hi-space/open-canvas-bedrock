"""Deploy immutable release images to the live Canvas stacks.

Used by .github/workflows/deploy.yml after tests and image builds pass. Only the
ECS task definition (and the service that references it), AgentCore runtime
and the existing HTTPS listener's authentication duration may change. Other
listener/authentication properties must remain identical. The log is
public on GitHub, so this prints resource names and status only, never template
contents or configuration values.

  python deploy/release.py --frontend-image REPO@sha256:... \
      --backend-image REPO@sha256:... --agent-image REPO@sha256:... --source-commit SHA
"""
import argparse
import copy
import json
import re
import sys
import time
import urllib.error
import urllib.request

REGION = "ap-northeast-2"
ACCOUNT = "913524902871"
REPOSITORY = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/cdk-hnb659fds-container-assets-{ACCOUNT}-{REGION}"
APPLICATION_STACK = "HtmlCanvasStack"
WORKSPACE_STACK = "CanvasWorkspaceStack"
CLUSTER = "html-canvas"
DOMAIN = "canvas.hi-yoo.com"
# The CDK bootstrap execution role; CloudFormation assumes it, so the GitHub
# deploy role needs only change-set access and permission to pass this role.
EXECUTION_ROLE = f"arn:aws:iam::{ACCOUNT}:role/cdk-hnb659fds-cfn-exec-role-{ACCOUNT}-{REGION}"
# Keep in sync with deploy/agentcore/prepare.py: the 60 s idle timeout requires
# /ping to report HealthyBusy, and 900 s covers the agent's 720 s job limit.
RUNTIME_LIFECYCLE = {"IdleRuntimeSessionTimeout": 60, "MaxLifetime": 900}
# ALB refreshes the short-lived Cognito access token within this login session.
# Keep cookie identity and the Cognito client unchanged across deployments.
AUTH_SESSION_SECONDS = 7 * 24 * 60 * 60
MAX_TEMPLATE_BYTES = 51200
ALLOWED_CHANGES = {
    APPLICATION_STACK: {
        "AWS::ECS::TaskDefinition": None, "AWS::ECS::Service": "False",
        "AWS::ElasticLoadBalancingV2::Listener": "False",
    },
    WORKSPACE_STACK: {"AWS::BedrockAgentCore::Runtime": "False"},
}


class ReleaseError(RuntimeError):
    pass


def immutable(image: str) -> str:
    if not re.fullmatch(re.escape(REPOSITORY) + r"@sha256:[a-f0-9]{64}", image):
        raise ReleaseError("Release images must be digests in the CDK assets repository.")
    return image


def only(template: dict, kind: str) -> str:
    names = [name for name, resource in template["Resources"].items() if resource["Type"] == kind]
    if len(names) != 1:
        raise ReleaseError(f"Expected one {kind}, found {len(names)}.")
    return names[0]


def authentication_configuration(template: dict) -> tuple[str, dict]:
    found = []
    for name, resource in template["Resources"].items():
        properties = resource.get("Properties") or {}
        if resource["Type"] != "AWS::ElasticLoadBalancingV2::Listener" or properties.get("Protocol") != "HTTPS":
            continue
        for action in properties.get("DefaultActions", []):
            if action.get("Type") == "authenticate-cognito":
                found.append((name, action.get("AuthenticateCognitoConfig") or {}))
    if len(found) != 1:
        raise ReleaseError("Expected one Cognito-authenticated HTTPS listener.")
    configuration = found[0][1]
    if (
        configuration.get("OnUnauthenticatedRequest", "authenticate") != "authenticate"
        or any(not configuration.get(key) for key in ("UserPoolArn", "UserPoolClientId", "UserPoolDomain"))
    ):
        raise ReleaseError("The existing HTTPS listener must require Cognito authentication.")
    return found[0]


def session_seconds(value) -> int:
    # CloudFormation returns both numeric and decimal-string representations.
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        value = int(value)
    if type(value) is not int or not 1 <= value <= AUTH_SESSION_SECONDS:
        raise ReleaseError("The authentication session duration is invalid.")
    return value


def check_listener_change(before: dict, after: dict):
    """Only the duration can change, including when restoring a previous release."""
    original = {"Resources": {"Listener": copy.deepcopy(before)}}
    updated = {"Resources": {"Listener": copy.deepcopy(after)}}
    for template in (original, updated):
        _, configuration = authentication_configuration(template)
        session_seconds(configuration.pop("SessionTimeout", AUTH_SESSION_SECONDS))
    if original != updated:
        raise ReleaseError("A release cannot change login identity, cookies or listener routing.")


def patch_application(template: dict, frontend: str, backend: str) -> dict:
    updated = copy.deepcopy(template)
    task = updated["Resources"][only(updated, "AWS::ECS::TaskDefinition")]
    containers = task["Properties"]["ContainerDefinitions"]
    if sorted(item["Name"] for item in containers) != ["app", "backend"]:
        raise ReleaseError("The task definition must contain exactly the app and backend containers.")
    for item in containers:
        item["Image"] = frontend if item["Name"] == "app" else backend
    _, authentication = authentication_configuration(updated)
    if session_seconds(authentication.get("SessionTimeout", AUTH_SESSION_SECONDS)) != AUTH_SESSION_SECONDS:
        authentication["SessionTimeout"] = AUTH_SESSION_SECONDS
    return updated


def patch_workspace(template: dict, agent: str) -> dict:
    updated = copy.deepcopy(template)
    runtime = updated["Resources"][only(updated, "AWS::BedrockAgentCore::Runtime")]["Properties"]
    runtime["AgentRuntimeArtifact"]["ContainerConfiguration"]["ContainerUri"] = agent
    runtime["LifecycleConfiguration"] = dict(RUNTIME_LIFECYCLE)
    return updated


def changed_resources(before: dict, after: dict) -> list[str]:
    if set(before["Resources"]) != set(after["Resources"]) or {
        key: value for key, value in before.items() if key != "Resources"
    } != {key: value for key, value in after.items() if key != "Resources"}:
        raise ReleaseError("A release may change only resource properties.")
    names = sorted(name for name, resource in before["Resources"].items() if resource != after["Resources"][name])
    for name in names:
        if before["Resources"][name]["Type"] == "AWS::ElasticLoadBalancingV2::Listener":
            check_listener_change(before["Resources"][name], after["Resources"][name])
    return names


def check_changes(stack: str, changes: list[dict]) -> list[str]:
    """Return the changed logical IDs, or raise when a change is outside the release scope."""
    allowed = ALLOWED_CHANGES[stack]
    resources = [change.get("ResourceChange", {}) for change in changes]
    if any(change.get("Type") != "Resource" for change in changes):
        raise ReleaseError(f"{stack}: unexpected non-resource change.")
    released = {item.get("LogicalResourceId") for item in resources if item.get("ResourceType") in allowed}
    names = []
    for resource in resources:
        kind = resource.get("ResourceType")
        if resource.get("Action") != "Modify":
            raise ReleaseError(f"{stack}: unexpected {resource.get('Action')} of {kind}.")
        if kind in allowed:
            if allowed[kind] is not None and resource.get("Replacement") != allowed[kind]:
                raise ReleaseError(f"{stack}: {kind} would be replaced.")
        # Resources that reference a released one (for example a policy naming
        # the runtime ARN) are listed for re-evaluation although their template
        # is unchanged; changed_resources() already rejected direct edits.
        elif not reevaluated_only(resource, released):
            raise ReleaseError(f"{stack}: unexpected Modify of {kind}.")
        names.append(resource["LogicalResourceId"])
    return sorted(names)


def reevaluated_only(resource: dict, released: set[str]) -> bool:
    details = resource.get("Details") or []
    return resource.get("Replacement") == "False" and bool(details) and all(
        detail.get("ChangeSource") in {"ResourceAttribute", "ResourceReference"}
        and detail.get("Evaluation") == "Dynamic"
        and str(detail.get("CausingEntity", "")).split(".", 1)[0] in released
        for detail in details
    )


def template_body(template: dict) -> str:
    body = json.dumps(template, separators=(",", ":"))
    if len(body.encode()) > MAX_TEMPLATE_BYTES:
        raise ReleaseError("The template exceeds the inline CloudFormation limit.")
    return body


def log(message: str):
    print(f"[release] {message}", flush=True)


class Release:
    def __init__(self, session, commit: str):
        self.cloudformation = session.client("cloudformation", region_name=REGION)
        self.ecs = session.client("ecs", region_name=REGION)
        self.elb = session.client("elbv2", region_name=REGION)
        self.agentcore = session.client("bedrock-agentcore-control", region_name=REGION)
        self.name = f"release-{commit[:12]}-{int(time.time())}"

    def template(self, stack: str) -> dict:
        body = self.cloudformation.get_template(StackName=stack, TemplateStage="Original")["TemplateBody"]
        return json.loads(body) if isinstance(body, str) else json.loads(json.dumps(body))

    def stack(self, stack: str) -> dict:
        return self.cloudformation.describe_stacks(StackName=stack)["Stacks"][0]

    def update(self, stack: str, before: dict, after: dict, description: str) -> bool:
        details = self.stack(stack)
        if not details["StackStatus"].endswith("_COMPLETE") or "IN_PROGRESS" in details["StackStatus"]:
            raise ReleaseError(f"{stack} is {details['StackStatus']}.")
        if not changed_resources(before, after):
            log(f"{stack}: already up to date")
            return False
        request = {
            "StackName": stack, "ChangeSetName": self.name, "ChangeSetType": "UPDATE",
            "TemplateBody": template_body(after), "Description": description[:1024],
            "Parameters": [{"ParameterKey": item["ParameterKey"], "UsePreviousValue": True}
                           for item in details.get("Parameters", [])],
            "Capabilities": details.get("Capabilities", []), "RoleARN": EXECUTION_ROLE,
        }
        identifier = self.cloudformation.create_change_set(**request)["Id"]
        while True:
            result = self.cloudformation.describe_change_set(ChangeSetName=identifier)
            if result["Status"] in {"CREATE_COMPLETE", "FAILED"}:
                break
            time.sleep(5)
        if result["Status"] == "FAILED":
            if "didn't contain changes" in result.get("StatusReason", ""):
                self.cloudformation.delete_change_set(ChangeSetName=identifier)
                log(f"{stack}: no changes")
                return False
            raise ReleaseError(f"{stack}: change set failed ({result.get('StatusReason', '')[:200]}).")
        changes = result["Changes"]
        while result.get("NextToken"):
            result = self.cloudformation.describe_change_set(ChangeSetName=identifier, NextToken=result["NextToken"])
            changes += result["Changes"]
        try:
            names = check_changes(stack, changes)
        except ReleaseError:
            self.cloudformation.delete_change_set(ChangeSetName=identifier)
            raise
        log(f"{stack}: executing {', '.join(names)}")
        self.cloudformation.execute_change_set(ChangeSetName=identifier)
        self.cloudformation.get_waiter("stack_update_complete").wait(
            StackName=stack, WaiterConfig={"Delay": 15, "MaxAttempts": 160},
        )
        log(f"{stack}: UPDATE_COMPLETE")
        return True

    def verify(self, frontend: str, backend: str, agent: str):
        _, authentication = authentication_configuration(self.template(APPLICATION_STACK))
        if session_seconds(authentication.get("SessionTimeout", AUTH_SESSION_SECONDS)) != AUTH_SESSION_SECONDS:
            raise ReleaseError("The HTTPS listener does not have the intended login session duration.")
        service = self.ecs.list_services(cluster=CLUSTER)["serviceArns"]
        if len(service) != 1:
            raise ReleaseError("Expected one ECS service.")
        self.ecs.get_waiter("services_stable").wait(
            cluster=CLUSTER, services=service, WaiterConfig={"Delay": 15, "MaxAttempts": 80},
        )
        details = self.ecs.describe_services(cluster=CLUSTER, services=service)["services"][0]
        if details["runningCount"] != details["desiredCount"] or len(details["deployments"]) != 1:
            raise ReleaseError("The ECS service did not settle on one deployment.")
        task = self.ecs.describe_task_definition(taskDefinition=details["taskDefinition"])["taskDefinition"]
        images = {item["name"]: item["image"] for item in task["containerDefinitions"]}
        if images != {"app": frontend, "backend": backend}:
            raise ReleaseError("The running task definition does not use the release images.")
        for balancer in details["loadBalancers"]:
            health = self.elb.describe_target_health(TargetGroupArn=balancer["targetGroupArn"])
            states = [item["TargetHealth"]["State"] for item in health["TargetHealthDescriptions"]]
            if not states or any(state != "healthy" for state in states):
                raise ReleaseError(f"Load balancer targets are {states}.")
        runtimes = [item for item in self.agentcore.list_agent_runtimes()["agentRuntimes"]
                    if item["agentRuntimeName"].startswith("canvas_writing_workspace")]
        if len(runtimes) != 1:
            raise ReleaseError("Expected one workspace runtime.")
        runtime = self.agentcore.get_agent_runtime(agentRuntimeId=runtimes[0]["agentRuntimeId"])
        uri = runtime["agentRuntimeArtifact"]["containerConfiguration"]["containerUri"]
        lifecycle = runtime.get("lifecycleConfiguration") or {}
        if runtime["status"] != "READY" or uri != agent or lifecycle.get("maxLifetime") != RUNTIME_LIFECYCLE["MaxLifetime"]:
            raise ReleaseError("The AgentCore runtime is not READY with the release image and lifecycle.")
        for path in ("/", "/api/workspaces"):
            location = redirect_location(f"https://{DOMAIN}{path}")
            if not re.match(r"https://[a-z0-9-]+\.auth\.[a-z0-9-]+\.amazoncognito\.com/oauth2/authorize\?", location):
                raise ReleaseError(f"{path} is not protected by the Cognito login redirect.")
        log("verified: ECS rollout, target health, runtime READY, Cognito redirects and session duration")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def redirect_location(url: str) -> str:
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(urllib.request.Request(url, method="GET"), timeout=20)
    except urllib.error.HTTPError as error:
        if error.code in {301, 302, 303, 307, 308}:
            return error.headers.get("Location", "")
        raise ReleaseError(f"Unexpected HTTP {error.code} from the service.") from None
    raise ReleaseError("The service answered without requiring login.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("frontend-image", "backend-image", "agent-image", "source-commit"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    frontend, backend, agent = map(immutable, (args.frontend_image, args.backend_image, args.agent_image))
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise ReleaseError("The source commit must be a full SHA.")

    import boto3

    release = Release(boto3.Session(), args.source_commit)
    workspace_before = release.template(WORKSPACE_STACK)
    application_before = release.template(APPLICATION_STACK)
    workspace_after = patch_workspace(workspace_before, agent)
    application_after = patch_application(application_before, frontend, backend)
    description = f"Release {args.source_commit[:12]} from GitHub Actions"
    updated = []
    try:
        # The new agent accepts the old backend's requests, so update it first.
        if release.update(WORKSPACE_STACK, workspace_before, workspace_after, description):
            updated.append((WORKSPACE_STACK, workspace_before, workspace_after))
        if release.update(APPLICATION_STACK, application_before, application_after, description):
            updated.append((APPLICATION_STACK, application_before, application_after))
        release.verify(frontend, backend, agent)
    except Exception:
        # CloudFormation already rolled back a failed update; restore stacks
        # whose update completed but whose release failed verification.
        for stack, before, after in reversed(updated):
            log(f"{stack}: restoring the previous images")
            release.name += "-rollback"
            release.update(stack, after, before, f"Rollback of {args.source_commit[:12]}")
        raise
    log(f"released {args.source_commit[:12]}")


if __name__ == "__main__":
    try:
        main()
    except ReleaseError as error:
        log(f"failed: {error}")
        sys.exit(1)
