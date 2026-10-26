"""Release changes are restricted to images, runtime lifecycle and login duration."""
import ast
import json
from pathlib import Path
import unittest

import release


DIGEST = release.REPOSITORY + "@sha256:" + "a" * 64
OTHER = release.REPOSITORY + "@sha256:" + "b" * 64


def application():
    return {"AWSTemplateFormatVersion": "2010-09-09", "Resources": {
        "TaskDef": {"Type": "AWS::ECS::TaskDefinition", "Properties": {"ContainerDefinitions": [
            {"Name": "app", "Image": "old-app"}, {"Name": "backend", "Image": "old-backend"},
        ]}},
        "Service": {"Type": "AWS::ECS::Service", "Properties": {"TaskDefinition": {"Ref": "TaskDef"}}},
        "Table": {"Type": "AWS::DynamoDB::Table", "Properties": {"TableName": "keep"}},
        "HttpsListener": {"Type": "AWS::ElasticLoadBalancingV2::Listener", "Properties": {
            "Protocol": "HTTPS", "Port": 443, "DefaultActions": [
                {"Type": "authenticate-cognito", "Order": 1, "AuthenticateCognitoConfig": {
                    "UserPoolArn": {"Fn::GetAtt": ["Pool", "Arn"]},
                    "UserPoolClientId": {"Ref": "Client"},
                    "UserPoolDomain": {"Ref": "Domain"},
                    "OnUnauthenticatedRequest": "authenticate",
                    "SessionCookieName": "AWSELBAuthSessionCookie",
                    "SessionTimeout": 3600, "Scope": "openid email profile",
                    "AuthenticationRequestExtraParams": {"lang": "ko"},
                }},
                {"Type": "forward", "Order": 2, "TargetGroupArn": {"Ref": "Target"}},
            ],
        }},
    }}


def workspace():
    return {"Resources": {
        "Runtime": {"Type": "AWS::BedrockAgentCore::Runtime", "Properties": {
            "AgentRuntimeArtifact": {"ContainerConfiguration": {"ContainerUri": "old-agent"}},
            "LifecycleConfiguration": {"IdleRuntimeSessionTimeout": 60, "MaxLifetime": 600},
        }},
        "Bucket": {"Type": "AWS::S3::Bucket", "Properties": {}},
    }}


def change(kind, logical, action="Modify", replacement="False"):
    return {"Type": "Resource", "ResourceChange": {
        "Action": action, "ResourceType": kind, "LogicalResourceId": logical, "Replacement": replacement,
    }}


class ReleaseTests(unittest.TestCase):
    def test_release_preserves_authentication_identity_while_extending_the_login_session(self):
        before = application()
        after = release.patch_application(before, DIGEST, OTHER)
        self.assertEqual(release.changed_resources(before, after), ["HttpsListener", "TaskDef"])
        images = {item["Name"]: item["Image"] for item in after["Resources"]["TaskDef"]["Properties"]["ContainerDefinitions"]}
        self.assertEqual(images, {"app": DIGEST, "backend": OTHER})
        configuration = after["Resources"]["HttpsListener"]["Properties"]["DefaultActions"][0]["AuthenticateCognitoConfig"]
        self.assertEqual(configuration["SessionTimeout"], 604800)
        old_configuration = before["Resources"]["HttpsListener"]["Properties"]["DefaultActions"][0]["AuthenticateCognitoConfig"]
        self.assertEqual({k: v for k, v in configuration.items() if k != "SessionTimeout"},
                         {k: v for k, v in old_configuration.items() if k != "SessionTimeout"})
        self.assertEqual(before, application())

    def test_future_image_releases_do_not_reconfigure_an_existing_seven_day_session(self):
        before = release.patch_application(application(), DIGEST, DIGEST)
        after = release.patch_application(before, OTHER, OTHER)
        self.assertEqual(release.changed_resources(before, after), ["TaskDef"])

    def test_cloudformation_string_durations_and_rollback_preserve_the_session_identity(self):
        before = application()
        configuration = before["Resources"]["HttpsListener"]["Properties"]["DefaultActions"][0]["AuthenticateCognitoConfig"]
        configuration["SessionTimeout"] = "3600"
        after = release.patch_application(before, DIGEST, OTHER)
        self.assertEqual(release.changed_resources(before, after), ["HttpsListener", "TaskDef"])
        self.assertEqual(release.changed_resources(after, before), ["HttpsListener", "TaskDef"])
        configuration["SessionTimeout"] = "604800"
        after = release.patch_application(before, DIGEST, OTHER)
        self.assertEqual(release.changed_resources(before, after), ["TaskDef"])

    def test_release_refuses_changes_to_auth_identity_cookie_or_routing(self):
        for field, value in (
            ("UserPoolClientId", {"Ref": "DifferentClient"}),
            ("SessionCookieName", "DifferentCookie"),
            ("OnUnauthenticatedRequest", "allow"),
            ("Scope", "openid"),
        ):
            before = application()
            after = application()
            after["Resources"]["HttpsListener"]["Properties"]["DefaultActions"][0]["AuthenticateCognitoConfig"][field] = value
            with self.subTest(field=field), self.assertRaises(release.ReleaseError):
                release.changed_resources(before, after)
        before, after = application(), application()
        after["Resources"]["HttpsListener"]["Properties"]["Port"] = 8443
        with self.assertRaises(release.ReleaseError):
            release.changed_resources(before, after)

    def test_bootstrap_uses_the_same_login_duration(self):
        import prepare_template

        template = {"Resources": {
            name: {"Type": kind, "Properties": {}} for name, kind in prepare_template.REQUIRED.items()
        }}
        template["Resources"]["AlbHttpsB7CA700A"]["Properties"] = {"Protocol": "HTTPS"}
        configured = prepare_template.support_template(template)
        auth = configured["Resources"]["AlbHttpsB7CA700A"]["Properties"]["DefaultActions"][0]["AuthenticateCognitoConfig"]
        self.assertEqual(auth["SessionTimeout"], 604800)
        self.assertEqual(auth["SessionCookieName"], "AWSELBAuthSessionCookie")

    def test_runtime_gets_the_agent_image_and_the_long_request_lifecycle(self):
        before = workspace()
        after = release.patch_workspace(before, DIGEST)
        self.assertEqual(release.changed_resources(before, after), ["Runtime"])
        runtime = after["Resources"]["Runtime"]["Properties"]
        self.assertEqual(runtime["AgentRuntimeArtifact"]["ContainerConfiguration"]["ContainerUri"], DIGEST)
        self.assertEqual(runtime["LifecycleConfiguration"], {"IdleRuntimeSessionTimeout": 60, "MaxLifetime": 900})

    def test_lifecycle_matches_the_agentcore_template_generator(self):
        source = Path(__file__).with_name("agentcore").joinpath("prepare.py").read_text()
        values = [
            ast.literal_eval(value)
            for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Dict)
            for key, value in zip(node.keys, node.values)
            if isinstance(key, ast.Constant) and key.value == "LifecycleConfiguration"
        ]
        self.assertEqual(values, [release.RUNTIME_LIFECYCLE])

    def test_unexpected_task_shapes_are_refused(self):
        template = application()
        template["Resources"]["TaskDef"]["Properties"]["ContainerDefinitions"].append({"Name": "sidecar"})
        with self.assertRaises(release.ReleaseError):
            release.patch_application(template, DIGEST, OTHER)
        template = application()
        template["Resources"]["Second"] = dict(template["Resources"]["TaskDef"])
        with self.assertRaises(release.ReleaseError):
            release.patch_application(template, DIGEST, OTHER)

    def test_change_sets_may_touch_only_release_resources_without_replacement(self):
        self.assertEqual(release.check_changes(release.APPLICATION_STACK, [
            change("AWS::ECS::TaskDefinition", "TaskDef", replacement="True"),
            change("AWS::ECS::Service", "Service"),
        ]), ["Service", "TaskDef"])
        self.assertEqual(release.check_changes(release.WORKSPACE_STACK, [
            change("AWS::BedrockAgentCore::Runtime", "Runtime"),
        ]), ["Runtime"])
        self.assertEqual(release.check_changes(release.APPLICATION_STACK, [
            change("AWS::ElasticLoadBalancingV2::Listener", "HttpsListener"),
        ]), ["HttpsListener"])
        for stack, bad in (
            (release.APPLICATION_STACK, change("AWS::DynamoDB::Table", "Table")),
            (release.APPLICATION_STACK, change("AWS::ECS::Service", "Service", replacement="True")),
            (release.APPLICATION_STACK, change("AWS::ECS::TaskDefinition", "TaskDef", action="Remove")),
            (release.APPLICATION_STACK, change("AWS::ElasticLoadBalancingV2::Listener", "HttpsListener", replacement="True")),
            (release.WORKSPACE_STACK, change("AWS::BedrockAgentCore::Runtime", "Runtime", replacement="Conditional")),
            (release.WORKSPACE_STACK, change("AWS::S3::Bucket", "Bucket")),
        ):
            with self.subTest(bad=bad), self.assertRaises(release.ReleaseError):
                release.check_changes(stack, [bad])

    def test_references_reevaluated_from_a_release_resource_are_allowed(self):
        # ApiWorkspacePolicy references Runtime.AgentRuntimeArn, so CloudFormation
        # lists it whenever the runtime changes, although its template is unchanged.
        reevaluated = change("AWS::IAM::Policy", "ApiWorkspacePolicy")
        reevaluated["ResourceChange"]["Details"] = [{
            "ChangeSource": "ResourceAttribute", "Evaluation": "Dynamic",
            "CausingEntity": "Runtime.AgentRuntimeArn", "Target": {"Attribute": "Properties", "Name": "PolicyDocument"},
        }]
        runtime = change("AWS::BedrockAgentCore::Runtime", "Runtime")
        self.assertEqual(release.check_changes(release.WORKSPACE_STACK, [reevaluated, runtime]),
                         ["ApiWorkspacePolicy", "Runtime"])

        def variant(**detail):
            item = json.loads(json.dumps(reevaluated))
            item["ResourceChange"]["Details"][0].update(detail)
            return item

        direct = variant(ChangeSource="DirectModification", Evaluation="Static", CausingEntity=None)
        other_cause = variant(CausingEntity="Bucket.Arn")
        replaced = json.loads(json.dumps(reevaluated))
        replaced["ResourceChange"]["Replacement"] = "Conditional"
        mixed = json.loads(json.dumps(reevaluated))
        mixed["ResourceChange"]["Details"].append(direct["ResourceChange"]["Details"][0])
        for bad in (direct, other_cause, replaced, mixed):
            with self.subTest(bad=bad["ResourceChange"]["Details"]), self.assertRaises(release.ReleaseError):
                release.check_changes(release.WORKSPACE_STACK, [bad, runtime])
        # A reevaluation without the release resource changing is not expected either.
        with self.assertRaises(release.ReleaseError):
            release.check_changes(release.WORKSPACE_STACK, [reevaluated])

    def test_templates_cannot_gain_or_lose_resources_or_sections(self):
        before = application()
        for mutate in (
            lambda t: t["Resources"].pop("Table"),
            lambda t: t["Resources"].__setitem__("Extra", {"Type": "AWS::S3::Bucket"}),
            lambda t: t.__setitem__("Outputs", {"X": {"Value": "y"}}),
        ):
            after = application()
            mutate(after)
            with self.assertRaises(release.ReleaseError):
                release.changed_resources(before, after)

    def test_only_immutable_images_in_the_assets_repository_are_released(self):
        self.assertEqual(release.immutable(DIGEST), DIGEST)
        for image in (release.REPOSITORY + ":latest", "public.ecr.aws/x@sha256:" + "a" * 64, DIGEST + "\n"):
            with self.subTest(image=image), self.assertRaises(release.ReleaseError):
                release.immutable(image)

    def test_oversized_templates_are_refused(self):
        template = application()
        template["Resources"]["Table"]["Properties"]["TableName"] = "x" * release.MAX_TEMPLATE_BYTES
        with self.assertRaises(release.ReleaseError):
            release.template_body(template)


if __name__ == "__main__":
    unittest.main()
