"""Behavioral checks for the review-only AgentCore template generator."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("prepare.py")
if MODULE_PATH.exists():
    SPEC = importlib.util.spec_from_file_location("workspace_infrastructure", MODULE_PATH)
    PREPARE = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(PREPARE)
else:
    PREPARE = None

REGISTRY = "913524902871.dkr.ecr.ap-northeast-2.amazonaws.com/canvas-images"
IMAGES = {
    "frontendImage": f"{REGISTRY}@sha256:{'1' * 64}",
    "backendImage": f"{REGISTRY}@sha256:{'2' * 64}",
}
AGENT_IMAGE = f"{REGISTRY}@sha256:{'3' * 64}"


def baseline():
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Parameters": {"ExistingParameter": {"Type": "String", "Default": "preserved"}},
        "Resources": {
            "TaskDef54694570": {
                "Type": "AWS::ECS::TaskDefinition",
                "Properties": {
                    "Cpu": "512",
                    "Memory": "1024",
                    "RequiresCompatibilities": ["FARGATE"],
                    "NetworkMode": "awsvpc",
                    "TaskRoleArn": {"Fn::GetAtt": ["TaskDefTaskRole1EDB4A67", "Arn"]},
                    "Volumes": [{"Name": "existing-volume", "Host": {}}],
                    "ContainerDefinitions": [
                        {
                            "Name": "app",
                            "Image": "old-frontend",
                            "Environment": [{"Name": "API_URL", "Value": "http://127.0.0.1:9000"}],
                            "HealthCheck": {"Command": ["CMD", "existing-health-check"]},
                        },
                        {
                            "Name": "backend",
                            "Image": "old-backend",
                            "Environment": [
                                {"Name": "STORAGE_TABLE_NAME", "Value": {"Ref": "WritingStore"}},
                                {"Name": "BEDROCK_REGION", "Value": "us-east-1"},
                            ],
                            "Secrets": [{
                                "Name": "FIRECRAWL_API_KEY",
                                "ValueFrom": "arn:aws:secretsmanager:ap-northeast-2:913524902871:secret:canvas-writing/reference-abc123",
                            }],
                        },
                    ],
                },
            },
            "TaskDefTaskRole1EDB4A67": {"Type": "AWS::IAM::Role"},
            "ServiceD69D759B": {
                "Type": "AWS::ECS::Service",
                "Properties": {"DesiredCount": 1, "TaskDefinition": {"Ref": "TaskDef54694570"}},
            },
            "Alb16C2F182": {"Type": "AWS::ElasticLoadBalancingV2::LoadBalancer"},
            "WritingAlbClient": {"Type": "AWS::Cognito::UserPoolClient"},
            "WritingStore": {"Type": "AWS::DynamoDB::Table", "DeletionPolicy": "Retain"},
            "UnrelatedResource": {
                "Type": "AWS::S3::Bucket",
                "Properties": {"BucketName": "existing-data"},
                "DeletionPolicy": "Retain",
            },
        },
        "Outputs": {"ExistingOutput": {"Value": "preserved"}},
    }


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(PREPARE, "The review-only infrastructure generator is missing.")

    def test_application_update_preserves_original_resources_and_secret_references(self):
        original = baseline()
        before = copy.deepcopy(original)
        result = PREPARE.application_template(original, IMAGES)
        self.assertEqual(original, before, "Generating a release must not mutate its baseline.")
        self.assertEqual(result["Parameters"], before["Parameters"])
        self.assertEqual(result["Outputs"], before["Outputs"])
        for name, resource in before["Resources"].items():
            if name != "TaskDef54694570":
                self.assertEqual(result["Resources"][name], resource, name)
        task = result["Resources"]["TaskDef54694570"]["Properties"]
        self.assertEqual((task["Cpu"], task["Memory"]), ("512", "1024"))
        self.assertIn({"Name": "existing-volume", "Host": {}}, task["Volumes"])
        containers = {item["Name"]: item for item in task["ContainerDefinitions"]}
        self.assertEqual(containers["backend"]["Secrets"],
                         before["Resources"]["TaskDef54694570"]["Properties"]["ContainerDefinitions"][1]["Secrets"])
        self.assertEqual(containers["app"]["HealthCheck"],
                         before["Resources"]["TaskDef54694570"]["Properties"]["ContainerDefinitions"][0]["HealthCheck"])

    def test_native_backend_mount_uses_support_stack_exports_and_verified_identity(self):
        result = PREPARE.application_template(baseline(), IMAGES)
        task = result["Resources"]["TaskDef54694570"]["Properties"]
        mount = next(volume for volume in task["Volumes"] if volume["Name"] == "workspace")
        self.assertEqual(mount["S3FilesVolumeConfiguration"], {
            "FileSystemArn": {"Fn::ImportValue": "CanvasWorkspaceStack:FileSystemArn"},
            "AccessPointArn": {"Fn::ImportValue": "CanvasWorkspaceStack:ApiAccessPointArn"},
        })
        containers = {item["Name"]: item for item in task["ContainerDefinitions"]}
        self.assertEqual(containers["backend"]["MountPoints"], [{
            "SourceVolume": "workspace", "ContainerPath": "/mnt/workspace", "ReadOnly": False,
        }])
        self.assertNotIn("MountPoints", containers["app"])
        environment = {item["Name"]: item["Value"] for item in containers["backend"]["Environment"]}
        self.assertEqual(environment["WORKSPACE_AUTH_MODE"], "alb")
        self.assertEqual(environment["ALB_SIGNER_ARN"], {"Ref": "Alb16C2F182"})
        self.assertEqual(environment["COGNITO_CLIENT_ID"], {"Ref": "WritingAlbClient"})
        self.assertEqual(environment["AGENTCORE_RUNTIME_ARN"],
                         {"Fn::ImportValue": "CanvasWorkspaceStack:RuntimeArn"})
        self.assertEqual(environment["WORKSPACE_TABLE_NAME"],
                         {"Fn::ImportValue": "CanvasWorkspaceStack:MetadataTableName"})
        self.assertEqual(environment["STORAGE_TABLE_NAME"], {"Ref": "WritingStore"})
        self.assertEqual(environment["BEDROCK_REGION"], "us-east-1",
                         "Existing writing endpoints keep their existing model configuration.")

    def test_repeated_generation_does_not_duplicate_volumes_mounts_or_environment(self):
        first = PREPARE.application_template(baseline(), IMAGES)
        second = PREPARE.application_template(first, IMAGES)
        self.assertEqual(first, second)

    def test_rejects_unknown_baseline_before_producing_an_update(self):
        for mutate in (
            lambda value: value["Resources"].pop("WritingAlbClient"),
            lambda value: value["Resources"]["TaskDef54694570"]["Properties"].update(
                {"RequiresCompatibilities": ["EC2"]}),
        ):
            with self.subTest(mutate=mutate):
                original = baseline()
                mutate(original)
                with self.assertRaises(ValueError):
                    PREPARE.application_template(original, IMAGES)

    def test_mutable_and_foreign_images_are_rejected(self):
        for image in (
            f"{REGISTRY}:latest",
            "public.ecr.aws/example/agent@sha256:" + "a" * 64,
            "000000000000.dkr.ecr.ap-northeast-2.amazonaws.com/agent@sha256:" + "a" * 64,
            REGISTRY + "@sha256:" + "g" * 64,
        ):
            with self.subTest(image=image):
                with self.assertRaises(ValueError):
                    PREPARE.support_template(image)
                with self.assertRaises(ValueError):
                    PREPARE.application_template(baseline(), {**IMAGES, "backendImage": image})

    def test_agent_can_mount_only_read_access_point_and_has_explicit_write_denials(self):
        resources = PREPARE.support_template(AGENT_IMAGE)["Resources"]
        role = resources["AgentRole"]["Properties"]
        statements = [statement for policy in role["Policies"]
                      for statement in policy["PolicyDocument"]["Statement"]]
        allowed = [statement for statement in statements if statement["Effect"] == "Allow"]
        allowed_actions = {action for statement in allowed
                           for action in (statement["Action"] if isinstance(statement["Action"], list)
                                          else [statement["Action"]])}
        self.assertNotIn("s3files:ClientWrite", allowed_actions)
        self.assertNotIn("s3:PutObject", allowed_actions)
        self.assertNotIn("sts:AssumeRole", allowed_actions)
        read_mount = next(statement for statement in allowed
                          if "s3files:ClientMount" in statement["Action"])
        self.assertEqual(read_mount["Condition"]["ArnEquals"]["s3files:AccessPointArn"],
                         {"Fn::GetAtt": ["AgentAccessPoint", "AccessPointArn"]})
        denied = [statement for statement in statements if statement["Effect"] == "Deny"]
        self.assertTrue(any("s3files:ClientWrite" in item["Action"] for item in denied))
        self.assertTrue(any("s3:PutObject*" in item["Action"] for item in denied))
        policy = resources["WorkspaceFileSystemPolicy"]["Properties"]["Policy"]["Statement"]
        self.assertTrue(any(item["Effect"] == "Deny" and "s3files:ClientWrite" in item["Action"]
                            for item in policy))
        runtime = resources["Runtime"]["Properties"]
        self.assertEqual(runtime["FilesystemConfigurations"], [{
            "S3FilesAccessPoint": {
                "AccessPointArn": {"Fn::GetAtt": ["AgentAccessPoint", "AccessPointArn"]},
                "MountPath": "/mnt/workspace",
            },
        }])
        self.assertNotIn("AuthorizerConfiguration", runtime, "Use IAM authentication.")
        self.assertNotIn("PlatformVersion", runtime,
                         "This account rejects explicit platformVersion; omission uses its default.")
        self.assertEqual(runtime["EnvironmentVariables"]["BEDROCK_REGION"], "ap-northeast-2")

    def test_runtime_can_discover_mount_targets_without_an_access_point_condition(self):
        role = PREPARE.support_template(AGENT_IMAGE)["Resources"]["AgentRole"]["Properties"]
        statements = [statement for policy in role["Policies"]
                      for statement in policy["PolicyDocument"]["Statement"]]
        discovery = [statement for statement in statements
                     if "s3files:ListMountTargets" in statement["Action"]]
        self.assertEqual(len(discovery), 1, "AgentCore validates mount targets when creating its runtime.")
        self.assertEqual(discovery[0]["Effect"], "Allow")
        self.assertEqual(discovery[0]["Resource"], {"Fn::GetAtt": ["WorkspaceFileSystem", "FileSystemArn"]})
        self.assertNotIn("Condition", discovery[0],
                         "ListMountTargets does not supply the NFS AccessPointArn condition key.")

    def test_logs_listing_uses_its_supported_scope_without_account_policy_write_access(self):
        role = PREPARE.support_template(AGENT_IMAGE)["Resources"]["AgentRole"]["Properties"]
        statements = [statement for policy in role["Policies"]
                      for statement in policy["PolicyDocument"]["Statement"]]
        listing = next(statement for statement in statements
                       if "logs:DescribeLogGroups" in statement["Action"])
        self.assertEqual(listing["Resource"], "*")
        self.assertEqual(listing["Condition"], {"StringEquals": {"aws:RequestedRegion": "ap-northeast-2"}})
        self.assertFalse(any("logs:PutResourcePolicy" in statement["Action"] for statement in statements))

    def test_single_az_private_runtime_and_both_fargate_mount_targets(self):
        resources = PREPARE.support_template(AGENT_IMAGE)["Resources"]
        interfaces = [resource["Properties"] for resource in resources.values()
                      if resource["Type"] == "AWS::EC2::VPCEndpoint"
                      and resource["Properties"]["VpcEndpointType"] == "Interface"]
        self.assertEqual(len(interfaces), 4)
        for endpoint in interfaces:
            self.assertEqual(endpoint["SubnetIds"], ["subnet-0aa7db5ae7c4b351f"])
            self.assertTrue(endpoint["PrivateDnsEnabled"])
        targets = [resource["Properties"]["SubnetId"] for resource in resources.values()
                   if resource["Type"] == "AWS::S3Files::MountTarget"]
        self.assertCountEqual(targets, ["subnet-0aa7db5ae7c4b351f", "subnet-05746e68f8479cdd3"])
        types = {resource["Type"] for resource in resources.values()}
        self.assertNotIn("AWS::EC2::NatGateway", types)
        runtime = resources["Runtime"]["Properties"]
        self.assertEqual(runtime["NetworkConfiguration"]["NetworkModeConfig"]["Subnets"],
                         ["subnet-0aa7db5ae7c4b351f"])

    def test_foundation_can_deploy_without_a_runtime_image_or_forward_references(self):
        result = getattr(PREPARE, "foundation_template", lambda: None)()
        self.assertIsInstance(result, dict, "A foundation stage is needed before the runtime image exists.")
        resources = result["Resources"]
        self.assertNotIn("Runtime", resources)
        self.assertIn("WorkspaceFileSystem", resources)
        self.assertIn("ApiWorkspacePolicy", resources)
        self.assertNotIn("RuntimeArn", result["Outputs"])
        self.assertNotIn('"Runtime"', json.dumps(result))
        self.assertNotIn("bedrock-agentcore:InvokeAgentRuntime", json.dumps(resources["ApiWorkspacePolicy"]))
        self.assertNotIn("WorkspaceMetadataTable", resources)

    def test_permissions_stage_settles_iam_and_metadata_before_runtime_creation(self):
        result = getattr(PREPARE, "permissions_template", lambda image: None)(AGENT_IMAGE)
        self.assertIsInstance(result, dict, "IAM updates must be deployable before runtime validation.")
        full = PREPARE.support_template(AGENT_IMAGE)
        self.assertIn("WorkspaceMetadataTable", result["Resources"])
        self.assertIn("MetadataTableName", result["Outputs"])
        self.assertNotIn("Runtime", result["Resources"])
        self.assertNotIn("RuntimeArn", result["Outputs"])
        self.assertNotIn('"Runtime"', json.dumps(result))
        for name, resource in result["Resources"].items():
            if name != "ApiWorkspacePolicy":
                self.assertEqual(resource, full["Resources"][name])
        statements = result["Resources"]["ApiWorkspacePolicy"]["Properties"]["PolicyDocument"]["Statement"]
        self.assertFalse(any(item["Sid"] == "InvokeWorkspaceAgent" for item in statements))
        self.assertTrue(any("dynamodb:Query" in item["Action"] for item in statements))

    def test_security_metadata_is_isolated_from_the_legacy_arbitrary_namespace_store(self):
        result = PREPARE.support_template(AGENT_IMAGE)
        resources = result["Resources"]
        table = resources.get("WorkspaceMetadataTable")
        self.assertIsNotNone(table, "Legacy namespace CRUD must not expose workspace security metadata.")
        self.assertEqual(table["Properties"]["TableName"], "canvas-writing-workspaces")
        self.assertEqual(table["Properties"]["BillingMode"], "PAY_PER_REQUEST")
        self.assertEqual(table["Properties"]["KeySchema"], [
            {"AttributeName": "namespace", "KeyType": "HASH"},
            {"AttributeName": "key", "KeyType": "RANGE"},
        ])
        self.assertEqual(table["DeletionPolicy"], "Retain")
        self.assertTrue(table["Properties"]["DeletionProtectionEnabled"])
        self.assertTrue(table["Properties"]["PointInTimeRecoverySpecification"]["PointInTimeRecoveryEnabled"])
        statements = resources["ApiWorkspacePolicy"]["Properties"]["PolicyDocument"]["Statement"]
        permissions = [item for item in statements if any(action.startswith("dynamodb:") for action in item["Action"])]
        self.assertEqual(len(permissions), 1)
        self.assertEqual(permissions[0]["Resource"], {"Fn::GetAtt": ["WorkspaceMetadataTable", "Arn"]})
        self.assertNotIn("dynamodb:", json.dumps(resources["AgentRole"]))
        self.assertEqual(result["Outputs"]["MetadataTableName"]["Value"], {"Ref": "WorkspaceMetadataTable"})

    def test_canonical_storage_is_encrypted_versioned_and_retained(self):
        resources = PREPARE.support_template(AGENT_IMAGE)["Resources"]
        bucket = resources["WorkspaceBucket"]
        self.assertEqual(bucket["Properties"]["VersioningConfiguration"]["Status"], "Enabled")
        self.assertEqual(bucket["Properties"]["BucketEncryption"]
                         ["ServerSideEncryptionConfiguration"][0]
                         ["ServerSideEncryptionByDefault"]["SSEAlgorithm"], "AES256")
        self.assertTrue(all(bucket["Properties"]["PublicAccessBlockConfiguration"].values()))
        for name in ["WorkspaceBucket", "WorkspaceFileSystem", "FileSystemSyncRole"]:
            self.assertEqual(resources[name]["DeletionPolicy"], "Retain")
            self.assertEqual(resources[name]["UpdateReplacePolicy"], "Retain")
        self.assertEqual(resources["FileSystemSyncRole"]["Properties"]["AssumeRolePolicyDocument"]
                         ["Statement"][0]["Principal"]["Service"], "elasticfilesystem.amazonaws.com")

    def test_private_output_overwrites_permissive_files_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "template.json"
            target.write_text("{}")
            os.chmod(target, 0o644)
            PREPARE.write_private(target, {"data": "review"})
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(target.read_text()), {"data": "review"})


if __name__ == "__main__":
    unittest.main()
