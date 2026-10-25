"""The release script changes only images and the runtime lifecycle, and refuses anything else."""
import ast
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
    def test_only_the_task_definition_changes_in_the_application_stack(self):
        before = application()
        after = release.patch_application(before, DIGEST, OTHER)
        self.assertEqual(release.changed_resources(before, after), ["TaskDef"])
        images = {item["Name"]: item["Image"] for item in after["Resources"]["TaskDef"]["Properties"]["ContainerDefinitions"]}
        self.assertEqual(images, {"app": DIGEST, "backend": OTHER})
        self.assertEqual(before, application())

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
        for stack, bad in (
            (release.APPLICATION_STACK, change("AWS::DynamoDB::Table", "Table")),
            (release.APPLICATION_STACK, change("AWS::ECS::Service", "Service", replacement="True")),
            (release.APPLICATION_STACK, change("AWS::ECS::TaskDefinition", "TaskDef", action="Remove")),
            (release.WORKSPACE_STACK, change("AWS::BedrockAgentCore::Runtime", "Runtime", replacement="Conditional")),
            (release.WORKSPACE_STACK, change("AWS::S3::Bucket", "Bucket")),
        ):
            with self.subTest(bad=bad), self.assertRaises(release.ReleaseError):
                release.check_changes(stack, [bad])

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
