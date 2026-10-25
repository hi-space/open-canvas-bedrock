"""Generate reviewable AgentCore/S3 Files CloudFormation templates.

This module has no AWS client and never deploys resources. Input baselines and
output templates belong in a private release directory outside the repository.
"""

import argparse
import copy
import json
import os
from pathlib import Path
import re


ACCOUNT = "913524902871"
REGION = "ap-northeast-2"
SUPPORT_STACK = "CanvasWorkspaceStack"
RUNTIME_NAME = "canvas_writing_workspace"
WORKSPACE_ROOT = "/mnt/workspace"
POSIX_ID = "10001"
VPC = "vpc-0e7115c004865d8c5"
PRIMARY_SUBNET = "subnet-0aa7db5ae7c4b351f"
SECONDARY_SUBNET = "subnet-05746e68f8479cdd3"
ROUTE_TABLES = ["rtb-0d1988977bbf51e9f", "rtb-061ba295855757b41"]
TASK_SECURITY_GROUP = "sg-08a06e457305400a0"
TASK_ROLE_NAME = "HtmlCanvasStack-TaskDefTaskRole1EDB4A67-g0WbLPDIjDLS"
TASK_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/{TASK_ROLE_NAME}"
BUCKET_NAME = f"canvas-writing-workspaces-{ACCOUNT}-apne2"
BUCKET_ARN = f"arn:aws:s3:::{BUCKET_NAME}"
EXISTING_ECR_REPOSITORY = f"cdk-hnb659fds-container-assets-{ACCOUNT}-{REGION}"
REQUIRED_RESOURCES = {
    "TaskDef54694570": "AWS::ECS::TaskDefinition",
    "TaskDefTaskRole1EDB4A67": "AWS::IAM::Role",
    "ServiceD69D759B": "AWS::ECS::Service",
    "Alb16C2F182": "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "WritingAlbClient": "AWS::Cognito::UserPoolClient",
    "WritingStore": "AWS::DynamoDB::Table",
}
TAGS = [{"Key": "Application", "Value": "canvas-writing-workspace"}]


def attribute(resource, name):
    return {"Fn::GetAtt": [resource, name]}


def document(statements):
    return {"Version": "2012-10-17", "Statement": statements}


def permission(sid, actions, resources, *, effect="Allow", condition=None, principal=None):
    statement = {"Sid": sid, "Effect": effect, "Action": actions, "Resource": resources}
    if condition:
        statement["Condition"] = condition
    if principal:
        statement["Principal"] = principal
    return statement


def retained(resource):
    return {**resource, "DeletionPolicy": "Retain", "UpdateReplacePolicy": "Retain"}


def image_repository(image):
    pattern = (
        rf"^{ACCOUNT}\.dkr\.ecr\.{REGION}\.amazonaws\.com/"
        r"(?P<repository>[a-z0-9]+(?:[._/-][a-z0-9]+)*)@sha256:[a-f0-9]{64}$"
    )
    match = re.fullmatch(pattern, image or "")
    if not match:
        raise ValueError("Use an immutable ECR image digest in the existing Seoul account.")
    return f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{match['repository']}"


def mount_permissions(access_point, *, writable):
    actions = ["s3files:ClientMount"]
    if writable:
        actions.append("s3files:ClientWrite")
    return [
        permission(
            "MountWorkspaceAccessPoint", actions,
            attribute("WorkspaceFileSystem", "FileSystemArn"),
            condition={"ArnEquals": {
                "s3files:AccessPointArn": attribute(access_point, "AccessPointArn"),
            }},
        ),
        permission(
            "InspectWorkspaceAccessPoint", ["s3files:GetAccessPoint"],
            [
                attribute("WorkspaceFileSystem", "FileSystemArn"),
                attribute(access_point, "AccessPointArn"),
            ],
        ),
        permission(
            "ReadBackingObjects", ["s3:GetObject", "s3:GetObjectVersion"],
            f"{BUCKET_ARN}/workspace/*",
        ),
        permission("ListBackingBucket", ["s3:ListBucket"], BUCKET_ARN),
    ]


def access_point():
    return {
        "Type": "AWS::S3Files::AccessPoint",
        "Properties": {
            "FileSystemId": {"Ref": "WorkspaceFileSystem"},
            "PosixUser": {"Uid": POSIX_ID, "Gid": POSIX_ID},
            "RootDirectory": {
                "Path": "/workspace",
                "CreationPermissions": {
                    "OwnerUid": POSIX_ID, "OwnerGid": POSIX_ID, "Permissions": "0750",
                },
            },
            "Tags": copy.deepcopy(TAGS),
        },
    }


def support_template(agent_image, *, include_runtime=True):
    """Create a separate, one-AZ runtime stack; retain the durable source data."""
    repository_arn = (
        image_repository(agent_image) if include_runtime
        else f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{EXISTING_ECR_REPOSITORY}"
    )
    resources = {}
    resources["WorkspaceBucket"] = retained({
        "Type": "AWS::S3::Bucket",
        "Properties": {
            "BucketName": BUCKET_NAME,
            "VersioningConfiguration": {"Status": "Enabled"},
            "BucketEncryption": {"ServerSideEncryptionConfiguration": [{
                "ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
            }]},
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True, "BlockPublicPolicy": True,
                "IgnorePublicAcls": True, "RestrictPublicBuckets": True,
            },
            "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
            "NotificationConfiguration": {
                "EventBridgeConfiguration": {"EventBridgeEnabled": True},
            },
            "Tags": copy.deepcopy(TAGS),
        },
    })
    resources["WorkspaceBucketPolicy"] = {
        "Type": "AWS::S3::BucketPolicy",
        "Properties": {
            "Bucket": {"Ref": "WorkspaceBucket"},
            "PolicyDocument": document([
                permission(
                    "RequireTransportEncryption", ["s3:*"],
                    [BUCKET_ARN, f"{BUCKET_ARN}/*"], effect="Deny", principal="*",
                    condition={"Bool": {"aws:SecureTransport": "false"}},
                ),
            ]),
        },
    }
    resources["FileSystemSyncRole"] = retained({
        "Type": "AWS::IAM::Role",
        "Properties": {
            "AssumeRolePolicyDocument": document([{
                "Effect": "Allow",
                "Principal": {"Service": "elasticfilesystem.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": ACCOUNT},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:s3files:{REGION}:{ACCOUNT}:file-system/*",
                    },
                },
            }]),
            "Policies": [{
                "PolicyName": "SynchronizeWorkspaceBucket",
                "PolicyDocument": document([
                    permission(
                        "ListVersionedSource", ["s3:ListBucket", "s3:ListBucketVersions"],
                        BUCKET_ARN, condition={"StringEquals": {"aws:ResourceAccount": ACCOUNT}},
                    ),
                    permission(
                        "SynchronizeSourceVersions",
                        [
                            "s3:AbortMultipartUpload", "s3:DeleteObject*", "s3:GetObject*",
                            "s3:List*", "s3:PutObject*",
                        ],
                        f"{BUCKET_ARN}/*",
                        condition={"StringEquals": {"aws:ResourceAccount": ACCOUNT}},
                    ),
                    permission(
                        "ManageFileSynchronizationEvents",
                        [
                            "events:DeleteRule", "events:DisableRule", "events:EnableRule",
                            "events:PutRule", "events:PutTargets", "events:RemoveTargets",
                        ],
                        f"arn:aws:events:{REGION}:{ACCOUNT}:rule/DO-NOT-DELETE-S3-Files*",
                        condition={"StringEquals": {
                            "events:ManagedBy": "elasticfilesystem.amazonaws.com",
                        }},
                    ),
                    permission(
                        "ReadFileSynchronizationEvents",
                        [
                            "events:DescribeRule", "events:ListRuleNamesByTarget",
                            "events:ListRules", "events:ListTargetsByRule",
                        ],
                        f"arn:aws:events:{REGION}:{ACCOUNT}:rule/*",
                    ),
                ]),
            }],
            "Tags": copy.deepcopy(TAGS),
        },
    })
    resources["WorkspaceFileSystem"] = retained({
        "Type": "AWS::S3Files::FileSystem",
        "DependsOn": ["WorkspaceBucketPolicy"],
        "Properties": {
            "Bucket": attribute("WorkspaceBucket", "Arn"),
            "RoleArn": attribute("FileSystemSyncRole", "Arn"),
            "Tags": copy.deepcopy(TAGS),
        },
    })
    resources["ApiAccessPoint"] = access_point()
    resources["AgentAccessPoint"] = access_point()
    resources["AgentSecurityGroup"] = {
        "Type": "AWS::EC2::SecurityGroup",
        "Properties": {
            "GroupDescription": "Canvas AgentCore access to workspace NFS and private AWS endpoints",
            "VpcId": VPC,
            "SecurityGroupEgress": [
                {
                    "IpProtocol": "tcp", "FromPort": 2049, "ToPort": 2049,
                    "DestinationSecurityGroupId": {"Ref": "FileSystemSecurityGroup"},
                    "Description": "Encrypted workspace filesystem",
                },
                {
                    "IpProtocol": "tcp", "FromPort": 443, "ToPort": 443,
                    "DestinationSecurityGroupId": {"Ref": "EndpointSecurityGroup"},
                    "Description": "Private AWS APIs",
                },
                {
                    "IpProtocol": "tcp", "FromPort": 443, "ToPort": 443,
                    "DestinationPrefixListId": {"Ref": "S3PrefixListId"},
                    "Description": "S3 backing objects and ECR image layers",
                },
            ],
            "Tags": copy.deepcopy(TAGS),
        },
    }
    # Ingress rules are separate resources to avoid security group dependency cycles.
    resources["FileSystemSecurityGroup"] = {
        "Type": "AWS::EC2::SecurityGroup",
        "Properties": {
            "GroupDescription": "Canvas S3 Files mount targets",
            "VpcId": VPC,
            "SecurityGroupEgress": [{
                "IpProtocol": "-1", "CidrIp": "127.0.0.1/32",
                "Description": "No initiated outbound connections",
            }],
            "Tags": copy.deepcopy(TAGS),
        },
    }
    resources["EndpointSecurityGroup"] = {
        "Type": "AWS::EC2::SecurityGroup",
        "Properties": {
            "GroupDescription": "Canvas private AWS endpoints",
            "VpcId": VPC,
            "SecurityGroupEgress": [{
                "IpProtocol": "-1", "CidrIp": "127.0.0.1/32",
                "Description": "No initiated outbound connections",
            }],
            "Tags": copy.deepcopy(TAGS),
        },
    }
    for name, group, port, source in [
        ("AgentNfsIngress", "FileSystemSecurityGroup", 2049, {"Ref": "AgentSecurityGroup"}),
        ("ApiNfsIngress", "FileSystemSecurityGroup", 2049, TASK_SECURITY_GROUP),
        ("AgentEndpointIngress", "EndpointSecurityGroup", 443, {"Ref": "AgentSecurityGroup"}),
        ("ApiEndpointIngress", "EndpointSecurityGroup", 443, TASK_SECURITY_GROUP),
    ]:
        resources[name] = {
            "Type": "AWS::EC2::SecurityGroupIngress",
            "Properties": {
                "GroupId": {"Ref": group},
                "IpProtocol": "tcp", "FromPort": port, "ToPort": port,
                "SourceSecurityGroupId": source,
            },
        }
    for name, subnet in [("PrimaryMountTarget", PRIMARY_SUBNET),
                         ("SecondaryMountTarget", SECONDARY_SUBNET)]:
        resources[name] = {
            "Type": "AWS::S3Files::MountTarget",
            "DependsOn": ["AgentNfsIngress", "ApiNfsIngress"],
            "Properties": {
                "FileSystemId": {"Ref": "WorkspaceFileSystem"},
                "SubnetId": subnet,
                "SecurityGroups": [{"Ref": "FileSystemSecurityGroup"}],
                "IpAddressType": "IPV4_ONLY",
            },
        }
    for name, service in [
        ("EcrApiEndpoint", "ecr.api"), ("EcrDockerEndpoint", "ecr.dkr"),
        ("LogsEndpoint", "logs"), ("BedrockRuntimeEndpoint", "bedrock-runtime"),
    ]:
        resources[name] = {
            "Type": "AWS::EC2::VPCEndpoint",
            "DependsOn": ["AgentEndpointIngress", "ApiEndpointIngress"],
            "Properties": {
                "VpcId": VPC,
                "VpcEndpointType": "Interface",
                "ServiceName": f"com.amazonaws.{REGION}.{service}",
                "PrivateDnsEnabled": True,
                "SubnetIds": [PRIMARY_SUBNET],
                "SecurityGroupIds": [{"Ref": "EndpointSecurityGroup"}],
                "Tags": copy.deepcopy(TAGS),
            },
        }
    resources["S3GatewayEndpoint"] = {
        "Type": "AWS::EC2::VPCEndpoint",
        "Properties": {
            "VpcId": VPC,
            "VpcEndpointType": "Gateway",
            "ServiceName": f"com.amazonaws.{REGION}.s3",
            "RouteTableIds": copy.deepcopy(ROUTE_TABLES),
            # Existing tasks retain their S3 access. Identity and bucket policies
            # continue to govern permissions through this routing-only endpoint.
            "Tags": copy.deepcopy(TAGS),
        },
    }
    agent_log_prefix = (
        f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:"
        f"/aws/bedrock-agentcore/runtimes/{RUNTIME_NAME}-*"
    )
    resources["AgentRole"] = {
        "Type": "AWS::IAM::Role",
        "Properties": {
            "AssumeRolePolicyDocument": document([{
                "Effect": "Allow", "Action": "sts:AssumeRole",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": ACCOUNT},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:*"},
                },
            }]),
            "Policies": [{
                "PolicyName": "ReadWorkspaceAndPropose",
                "PolicyDocument": document([
                    *mount_permissions("AgentAccessPoint", writable=False),
                    # Runtime creation validates the target VPC/AZ through this
                    # control-plane action. Unlike ClientMount, it has no
                    # s3files:AccessPointArn condition key.
                    permission(
                        "DiscoverWorkspaceMountTargets", ["s3files:ListMountTargets"],
                        attribute("WorkspaceFileSystem", "FileSystemArn"),
                    ),
                    permission(
                        "DenyCanonicalFileWrites",
                        ["s3files:ClientWrite", "s3files:ClientRootAccess"],
                        attribute("WorkspaceFileSystem", "FileSystemArn"), effect="Deny",
                    ),
                    permission(
                        "DenyCanonicalObjectWrites",
                        ["s3:PutObject*", "s3:DeleteObject*", "s3:AbortMultipartUpload"],
                        f"{BUCKET_ARN}/*", effect="Deny",
                    ),
                    permission(
                        "ReadRuntimeImage",
                        ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
                         "ecr:BatchCheckLayerAvailability"],
                        repository_arn,
                    ),
                    permission("ReadRegistryToken", ["ecr:GetAuthorizationToken"], "*"),
                    permission(
                        "RuntimeLogs", [
                            "logs:CreateLogGroup", "logs:DescribeLogStreams",
                        ], agent_log_prefix,
                    ),
                    permission(
                        "ListRuntimeLogs", ["logs:DescribeLogGroups"], "*",
                        condition={"StringEquals": {"aws:RequestedRegion": REGION}},
                    ),
                    permission(
                        "WriteRuntimeLogs", ["logs:CreateLogStream", "logs:PutLogEvents"],
                        f"{agent_log_prefix}:log-stream:*",
                    ),
                    permission(
                        "InvokeSelectedModels",
                        ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        [
                            "arn:aws:bedrock:*::foundation-model/*",
                            f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/*",
                            f"arn:aws:bedrock:{REGION}:{ACCOUNT}:application-inference-profile/*",
                            f"arn:aws:bedrock:{REGION}:{ACCOUNT}:project/default",
                        ],
                    ),
                ]),
            }],
            "Tags": copy.deepcopy(TAGS),
        },
    }
    resources["WorkspaceFileSystemPolicy"] = {
        "Type": "AWS::S3Files::FileSystemPolicy",
        "Properties": {
            "FileSystemId": {"Ref": "WorkspaceFileSystem"},
            "Policy": document([
                permission(
                    "ApiApprovedWrites", ["s3files:ClientMount", "s3files:ClientWrite"],
                    attribute("WorkspaceFileSystem", "FileSystemArn"),
                    principal={"AWS": TASK_ROLE_ARN},
                    condition={"ArnEquals": {
                        "s3files:AccessPointArn": attribute("ApiAccessPoint", "AccessPointArn"),
                    }},
                ),
                permission(
                    "AgentReads", ["s3files:ClientMount"],
                    attribute("WorkspaceFileSystem", "FileSystemArn"),
                    principal={"AWS": attribute("AgentRole", "Arn")},
                    condition={"ArnEquals": {
                        "s3files:AccessPointArn": attribute("AgentAccessPoint", "AccessPointArn"),
                    }},
                ),
                permission(
                    "DenyAgentWrites", ["s3files:ClientWrite", "s3files:ClientRootAccess"],
                    attribute("WorkspaceFileSystem", "FileSystemArn"), effect="Deny",
                    principal="*",
                    condition={"ArnEquals": {"aws:PrincipalArn": attribute("AgentRole", "Arn")}},
                ),
            ]),
        },
    }
    resources["Runtime"] = {
        "Type": "AWS::BedrockAgentCore::Runtime",
        "DependsOn": [
            "WorkspaceFileSystemPolicy", "PrimaryMountTarget", "SecondaryMountTarget",
            "EcrApiEndpoint", "EcrDockerEndpoint", "LogsEndpoint", "BedrockRuntimeEndpoint",
            "S3GatewayEndpoint",
        ],
        "Properties": {
            "AgentRuntimeName": RUNTIME_NAME,
            "Description": "Canvas workspace reader and review proposal agent",
            "AgentRuntimeArtifact": {"ContainerConfiguration": {"ContainerUri": agent_image}},
            "RoleArn": attribute("AgentRole", "Arn"),
            # Explicit platformVersion is account-gated, including "V1".
            # Omit the optional field and use the supported account default.
            "ProtocolConfiguration": "HTTP",
            "NetworkConfiguration": {
                "NetworkMode": "VPC",
                "NetworkModeConfig": {
                    "Subnets": [PRIMARY_SUBNET],
                    "SecurityGroups": [{"Ref": "AgentSecurityGroup"}],
                },
            },
            "FilesystemConfigurations": [{
                "S3FilesAccessPoint": {
                    "AccessPointArn": attribute("AgentAccessPoint", "AccessPointArn"),
                    "MountPath": WORKSPACE_ROOT,
                },
            }],
            "EnvironmentVariables": {
                "WORKSPACE_ROOT": WORKSPACE_ROOT,
                "BEDROCK_REGION": REGION,
                "BEDROCK_MODEL_ID": "global.anthropic.claude-opus-5-5",
                "PYTHONUNBUFFERED": "1",
            },
            "LifecycleConfiguration": {"IdleRuntimeSessionTimeout": 60, "MaxLifetime": 900},
            "Tags": {"Application": "canvas-writing-workspace"},
        },
    }
    resources["ApiWorkspacePolicy"] = {
        "Type": "AWS::IAM::Policy",
        "Properties": {
            "PolicyName": "CanvasWorkspaceApprovedFileWrites",
            "Roles": [TASK_ROLE_NAME],
            "PolicyDocument": document([
                *mount_permissions("ApiAccessPoint", writable=True),
                permission(
                    "InvokeWorkspaceAgent",
                    ["bedrock-agentcore:InvokeAgentRuntime", "bedrock-agentcore:StopRuntimeSession"],
                    [
                        attribute("Runtime", "AgentRuntimeArn"),
                        {"Fn::Join": ["", [attribute("Runtime", "AgentRuntimeArn"), "/runtime-endpoint/*"]]},
                    ],
                ),
            ]),
        },
    }
    outputs = {}
    for name, value in [
        ("FileSystemArn", attribute("WorkspaceFileSystem", "FileSystemArn")),
        ("ApiAccessPointArn", attribute("ApiAccessPoint", "AccessPointArn")),
        ("RuntimeArn", attribute("Runtime", "AgentRuntimeArn")),
    ]:
        outputs[name] = {"Value": value, "Export": {"Name": {"Fn::Sub": f"${{AWS::StackName}}:{name}"}}}
    outputs.update({
        "BucketName": {"Value": {"Ref": "WorkspaceBucket"}},
        "AgentRoleArn": {"Value": attribute("AgentRole", "Arn")},
        "AgentAccessPointArn": {"Value": attribute("AgentAccessPoint", "AccessPointArn")},
        "RuntimeId": {"Value": attribute("Runtime", "AgentRuntimeId")},
        "RuntimeRegion": {"Value": REGION},
    })
    if not include_runtime:
        del resources["Runtime"]
        api_statements = resources["ApiWorkspacePolicy"]["Properties"]["PolicyDocument"]["Statement"]
        resources["ApiWorkspacePolicy"]["Properties"]["PolicyDocument"]["Statement"] = [
            statement for statement in api_statements if statement["Sid"] != "InvokeWorkspaceAgent"
        ]
        del outputs["RuntimeArn"]
        del outputs["RuntimeId"]
    else:
        # Legacy /store routes allow arbitrary namespaces in WritingStore. Keep
        # ownership, job and proposal state in a table those routes never use.
        resources["WorkspaceMetadataTable"] = retained({
            "Type": "AWS::DynamoDB::Table",
            "Properties": {
                "TableName": "canvas-writing-workspaces",
                "BillingMode": "PAY_PER_REQUEST",
                "AttributeDefinitions": [
                    {"AttributeName": "namespace", "AttributeType": "S"},
                    {"AttributeName": "key", "AttributeType": "S"},
                ],
                "KeySchema": [
                    {"AttributeName": "namespace", "KeyType": "HASH"},
                    {"AttributeName": "key", "KeyType": "RANGE"},
                ],
                "SSESpecification": {"SSEEnabled": True},
                "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
                "DeletionProtectionEnabled": True,
                "Tags": copy.deepcopy(TAGS),
            },
        })
        resources["ApiWorkspacePolicy"]["Properties"]["PolicyDocument"]["Statement"].append(
            permission(
                "WorkspaceSecurityMetadata",
                ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:Query"],
                attribute("WorkspaceMetadataTable", "Arn"),
            )
        )
        outputs["MetadataTableName"] = {
            "Value": {"Ref": "WorkspaceMetadataTable"},
            "Export": {"Name": {"Fn::Sub": "${AWS::StackName}:MetadataTableName"}},
        }
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Retained S3 Files workspace and a read-only Seoul AgentCore runtime",
        "Parameters": {
            "S3PrefixListId": {
                "Type": "String",
                "AllowedPattern": "^pl-[0-9a-f]+$",
                "Description": "AWS-managed com.amazonaws.ap-northeast-2.s3 prefix list ID",
            },
        },
        "Resources": resources,
        "Outputs": outputs,
    }


def foundation_template():
    """Provision mounts/networking and API access before an agent image exists."""
    return support_template(None, include_runtime=False)


def permissions_template(agent_image):
    """Settle execution permissions and metadata before runtime validation."""
    result = support_template(agent_image)
    del result["Resources"]["Runtime"]
    statements = result["Resources"]["ApiWorkspacePolicy"]["Properties"]["PolicyDocument"]["Statement"]
    result["Resources"]["ApiWorkspacePolicy"]["Properties"]["PolicyDocument"]["Statement"] = [
        statement for statement in statements if statement["Sid"] != "InvokeWorkspaceAgent"
    ]
    del result["Outputs"]["RuntimeArn"]
    del result["Outputs"]["RuntimeId"]
    return result


def application_template(original, images, support_stack=SUPPORT_STACK):
    """Extend only the existing task definition; preserve every other resource."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,127}", support_stack):
        raise ValueError("Invalid support stack name.")
    for key in ["frontendImage", "backendImage"]:
        image_repository(images.get(key))
    for name, resource_type in REQUIRED_RESOURCES.items():
        if original.get("Resources", {}).get(name, {}).get("Type") != resource_type:
            raise ValueError(f"Unexpected baseline resource {name}; inspect the live stack.")
    task = original["Resources"]["TaskDef54694570"]["Properties"]
    if task.get("RequiresCompatibilities") != ["FARGATE"] or task.get("NetworkMode") != "awsvpc":
        raise ValueError("The baseline must be the existing awsvpc Fargate task.")
    if {item["Name"] for item in task["ContainerDefinitions"]} != {"app", "backend"}:
        raise ValueError("The baseline must contain the existing app and backend containers.")

    result = copy.deepcopy(original)
    resource = result["Resources"]["TaskDef54694570"]
    resource["DeletionPolicy"] = "Retain"
    resource["UpdateReplacePolicy"] = "Retain"
    task = resource["Properties"]
    imported = lambda name: {"Fn::ImportValue": f"{support_stack}:{name}"}
    task["Volumes"] = [
        *[volume for volume in task.get("Volumes", []) if volume["Name"] != "workspace"],
        {
            "Name": "workspace",
            "S3FilesVolumeConfiguration": {
                "FileSystemArn": imported("FileSystemArn"),
                "AccessPointArn": imported("ApiAccessPointArn"),
            },
        },
    ]
    for container in task["ContainerDefinitions"]:
        container["Image"] = images["frontendImage" if container["Name"] == "app" else "backendImage"]
        if container["Name"] != "backend":
            continue
        container["MountPoints"] = [
            *[mount for mount in container.get("MountPoints", []) if mount["SourceVolume"] != "workspace"],
            {"SourceVolume": "workspace", "ContainerPath": WORKSPACE_ROOT, "ReadOnly": False},
        ]
        additions = {
            "WORKSPACE_ROOT": WORKSPACE_ROOT,
            "WORKSPACE_STORAGE_MODE": "cloud",
            "WORKSPACE_METADATA": "dynamodb",
            "WORKSPACE_TABLE_NAME": imported("MetadataTableName"),
            "WORKSPACE_AUTH_MODE": "alb",
            "ALB_SIGNER_ARN": {"Ref": "Alb16C2F182"},
            "COGNITO_CLIENT_ID": {"Ref": "WritingAlbClient"},
            "AGENTCORE_RUNTIME_ARN": imported("RuntimeArn"),
            "AGENTCORE_REGION": REGION,
        }
        container["Environment"] = [
            *[item for item in container.get("Environment", []) if item["Name"] not in additions],
            *[{"Name": name, "Value": value} for name, value in additions.items()],
        ]
    changed = {
        name for name, value in original["Resources"].items()
        if value != result["Resources"].get(name)
    }
    if changed - {"TaskDef54694570"}:
        raise ValueError(f"Unexpected existing-resource changes: {sorted(changed)}")
    return result


def write_private(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(value, output, indent=2)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-image", help="Immutable Seoul ARM64 ECR image URI")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--images", type=Path, help="JSON with frontendImage/backendImage digests")
    parser.add_argument("--support-stack", default=SUPPORT_STACK)
    args = parser.parse_args()
    if bool(args.baseline) != bool(args.images):
        parser.error("--baseline and --images must be supplied together.")
    if args.baseline and not args.agent_image:
        parser.error("Application template generation also requires --agent-image.")
    foundation = foundation_template()
    support = support_template(args.agent_image) if args.agent_image else None
    application = None
    if args.baseline:
        application = application_template(
            json.loads(args.baseline.read_text()), json.loads(args.images.read_text()),
            args.support_stack,
        )
    args.output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(args.output_directory, 0o700)
    write_private(args.output_directory / "workspace-foundation-template.json", foundation)
    if support is not None:
        write_private(args.output_directory / "permissions-template.json", permissions_template(args.agent_image))
        write_private(args.output_directory / "workspace-support-template.json", support)
    if application is not None:
        write_private(args.output_directory / "workspace-application-template.json", application)
    print("Generated private review templates. No AWS resource was created or changed.")
    print("Foundation: retained workspace storage, mounts, scoped roles, four interface endpoints.")
    if support is not None:
        print("Permissions: prepare metadata and runtime IAM before runtime creation.")
        print("Support: add the one-AZ read-only runtime to the foundation stack.")
    if application is not None:
        print("Application: existing ECS task definition only; native writable backend mount.")


if __name__ == "__main__":
    main()
