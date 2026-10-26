"""Prepare reviewed CloudFormation updates from the live Canvas stack template.

This script does not deploy resources. Keep generated templates in a private
release directory and inspect CloudFormation change sets before executing them.
"""
import argparse
import copy
import json
import os
import re
from pathlib import Path
from release import AUTH_SESSION_SECONDS

DOMAIN = "canvas.hi-yoo.com"
REGION = "ap-northeast-2"
TABLES = {
    "WritingStore": ("store", [("namespace", "S"), ("key", "S")], "STORAGE_TABLE_NAME"),
    "WritingEntities": ("entities", [("entity_type", "S"), ("entity_id", "S")], "STORAGE_ENTITY_TABLE_NAME"),
    "WritingThreads": ("threads", [("thread_id", "S")], "STORAGE_THREADS_TABLE_NAME"),
    "WritingArtifacts": ("artifacts", [("thread_id", "S"), ("version_index", "N")], "STORAGE_ARTIFACTS_TABLE_NAME"),
}
REQUIRED = {
    "TableCD117FA1": "AWS::DynamoDB::Table",
    "Bucket83908E77": "AWS::S3::Bucket",
    "UserPool6BA7E5F2": "AWS::Cognito::UserPool",
    "UserPoolDomainD0EA232A": "AWS::Cognito::UserPoolDomain",
    "UserPoolWebClient4C9370B0": "AWS::Cognito::UserPoolClient",
    "TaskDefTaskRole1EDB4A67": "AWS::IAM::Role",
    "TaskDef54694570": "AWS::ECS::TaskDefinition",
    "ServiceD69D759B": "AWS::ECS::Service",
    "AlbHttpsB7CA700A": "AWS::ElasticLoadBalancingV2::Listener",
    "AlbHttpsAppGroup506BD4E7": "AWS::ElasticLoadBalancingV2::TargetGroup",
}


def support_template(original):
    result = copy.deepcopy(original)
    resources = result["Resources"]
    for name, resource_type in REQUIRED.items():
        if resources.get(name, {}).get("Type") != resource_type:
            raise ValueError(f"Unexpected stack resource {name}; inspect the live stack.")
    if resources["AlbHttpsB7CA700A"]["Properties"].get("Protocol") != "HTTPS":
        raise ValueError("The existing listener must use HTTPS.")

    for logical_id, (suffix, keys, _) in TABLES.items():
        resources[logical_id] = {
            "Type": "AWS::DynamoDB::Table",
            "DeletionPolicy": "Retain",
            "UpdateReplacePolicy": "Retain",
            "Properties": {
                "TableName": f"canvas-writing-{suffix}",
                "BillingMode": "PAY_PER_REQUEST",
                "AttributeDefinitions": [
                    {"AttributeName": name, "AttributeType": kind} for name, kind in keys
                ],
                "KeySchema": [
                    {"AttributeName": name, "KeyType": "HASH" if index == 0 else "RANGE"}
                    for index, (name, _) in enumerate(keys)
                ],
                "SSESpecification": {"SSEEnabled": True},
                "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
                "DeletionProtectionEnabled": True,
                "Tags": [{"Key": "Application", "Value": "open-canvas-writing"}],
            },
        }
    resources["WritingPersistencePolicy"] = {
        "Type": "AWS::IAM::Policy",
        "Properties": {
            "PolicyName": "WritingWorkspacePersistence",
            "Roles": [{"Ref": "TaskDefTaskRole1EDB4A67"}],
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:DescribeTable", "dynamodb:GetItem", "dynamodb:PutItem",
                        "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query",
                        "dynamodb:Scan", "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem",
                    ],
                    "Resource": [{"Fn::GetAtt": [name, "Arn"]} for name in TABLES],
                }],
            },
        },
    }
    resources["WritingAlbClient"] = {
        "Type": "AWS::Cognito::UserPoolClient",
        "Properties": {
            "ClientName": "canvas-writing-alb",
            "UserPoolId": {"Ref": "UserPool6BA7E5F2"},
            "GenerateSecret": True,
            "AllowedOAuthFlows": ["code"],
            "AllowedOAuthFlowsUserPoolClient": True,
            "AllowedOAuthScopes": ["openid", "email", "profile"],
            "CallbackURLs": [f"https://{DOMAIN}/oauth2/idpresponse"],
            "LogoutURLs": [f"https://{DOMAIN}/"],
            "SupportedIdentityProviders": ["COGNITO"],
            "ExplicitAuthFlows": ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
            "PreventUserExistenceErrors": "ENABLED",
        },
    }
    listener = resources["AlbHttpsB7CA700A"]["Properties"]
    previous_auth = next((
        action.get("AuthenticateCognitoConfig", {})
        for action in listener.get("DefaultActions", [])
        if action.get("Type") == "authenticate-cognito"
    ), {})
    listener["DefaultActions"] = [
        {
            "Type": "authenticate-cognito",
            "Order": 1,
            "AuthenticateCognitoConfig": {
                "UserPoolArn": {"Fn::GetAtt": ["UserPool6BA7E5F2", "Arn"]},
                "UserPoolClientId": {"Ref": "WritingAlbClient"},
                "UserPoolDomain": {"Ref": "UserPoolDomainD0EA232A"},
                "OnUnauthenticatedRequest": "authenticate",
                "Scope": "openid email profile",
                "SessionCookieName": "AWSELBAuthSessionCookie",
                "SessionTimeout": AUTH_SESSION_SECONDS,
            },
        },
        {"Type": "forward", "Order": 2, "TargetGroupArn": {"Ref": "AlbHttpsAppGroup506BD4E7"}},
    ]
    if previous_auth.get("AuthenticationRequestExtraParams"):
        listener["DefaultActions"][0]["AuthenticateCognitoConfig"]["AuthenticationRequestExtraParams"] = (
            copy.deepcopy(previous_auth["AuthenticationRequestExtraParams"])
        )
    resources["WritingLogoutRule"] = {
        "Type": "AWS::ElasticLoadBalancingV2::ListenerRule",
        "Properties": {
            "ListenerArn": {"Ref": "AlbHttpsB7CA700A"},
            "Priority": 1,
            "Conditions": [{"Field": "path-pattern", "Values": ["/auth/logout"]}],
            "Actions": [{"Type": "forward", "TargetGroupArn": {"Ref": "AlbHttpsAppGroup506BD4E7"}}],
        },
    }
    # The support stage does not switch tasks, remove data, or widen inbound access.
    changed_existing = [
        name for name, resource in original["Resources"].items()
        if result["Resources"].get(name) != resource
    ]
    if set(changed_existing) - {"AlbHttpsB7CA700A"}:
        raise ValueError(f"Unexpected support changes: {changed_existing}")
    return result


def application_template(support, images, reference_secret=None):
    for key in ["frontendImage", "backendImage"]:
        if not re.fullmatch(r"[^@\s]+@sha256:[a-f0-9]{64}", images[key]):
            raise ValueError(f"{key} must be an immutable image digest.")
    result = copy.deepcopy(support)
    resources = result["Resources"]
    resources["TaskDef54694570"]["UpdateReplacePolicy"] = "Retain"
    resources["TaskDef54694570"]["DeletionPolicy"] = "Retain"
    task = resources["TaskDef54694570"]["Properties"]
    original_app = next(item for item in task["ContainerDefinitions"] if item["Name"] == "app")
    log_configuration = original_app["LogConfiguration"]
    frontend = {
        "Name": "app",
        "Image": images["frontendImage"],
        "Essential": True,
        "PortMappings": [{"ContainerPort": 3000, "Protocol": "tcp"}],
        "DependsOn": [{"ContainerName": "backend", "Condition": "HEALTHY"}],
        "Environment": [
            {"Name": "NODE_ENV", "Value": "production"},
            {"Name": "HOSTNAME", "Value": "0.0.0.0"},
            {"Name": "PORT", "Value": "3000"},
            {"Name": "API_URL", "Value": "http://127.0.0.1:9000"},
            {"Name": "APP_URL", "Value": f"https://{DOMAIN}"},
            {"Name": "COGNITO_CLIENT_ID", "Value": {"Ref": "WritingAlbClient"}},
            {"Name": "COGNITO_DOMAIN", "Value": {
                "Fn::Join": ["", [{"Ref": "UserPoolDomainD0EA232A"}, f".auth.{REGION}.amazoncognito.com"]],
            }},
        ],
        "LogConfiguration": copy.deepcopy(log_configuration),
        "HealthCheck": {
            "Command": ["CMD", "node", "-e",
                        "fetch('http://127.0.0.1:3000/api/health',{signal:AbortSignal.timeout(4000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"],
            "Interval": 15, "Retries": 3, "StartPeriod": 30, "Timeout": 5,
        },
    }
    backend = {
        "Name": "backend",
        "Image": images["backendImage"],
        "Essential": True,
        "PortMappings": [{"ContainerPort": 9000, "Protocol": "tcp"}],
        "Environment": [
            {"Name": "STORAGE_TYPE", "Value": "dynamodb"},
            {"Name": "AWS_DEFAULT_REGION", "Value": REGION},
            {"Name": "AWS_REGION", "Value": REGION},
            {"Name": "BEDROCK_REGION", "Value": "us-east-1"},
            {"Name": "BEDROCK_MODEL_ID", "Value": "global.anthropic.claude-opus-5-5"},
            {"Name": "LANGCHAIN_TRACING_V2", "Value": "false"},
            {"Name": "LANGSMITH_TRACING", "Value": "false"},
            *[{"Name": environment, "Value": {"Ref": logical_id}}
              for logical_id, (_, _, environment) in TABLES.items()],
        ],
        "LogConfiguration": copy.deepcopy(log_configuration),
        "HealthCheck": {
            "Command": ["CMD", "python", "-c",
                        "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:9000/health',timeout=4).status == 200"],
            "Interval": 10, "Retries": 3, "StartPeriod": 30, "Timeout": 5,
        },
    }
    backend["LogConfiguration"]["Options"]["awslogs-stream-prefix"] = "backend"
    task["ContainerDefinitions"] = [frontend, backend]
    service = resources["ServiceD69D759B"]
    service["Properties"]["HealthCheckGracePeriodSeconds"] = 120
    service["DependsOn"] = list(dict.fromkeys([
        *service.get("DependsOn", []), "WritingPersistencePolicy", "WritingLogoutRule",
    ]))
    if reference_secret:
        secret_arn = reference_secret["arn"]
        if not re.fullmatch(r"arn:aws:secretsmanager:ap-northeast-2:\d{12}:secret:canvas-writing/[^:\s]+", secret_arn):
            raise ValueError("The reference credential must be an application-scoped Secrets Manager ARN.")
        resources["WritingReferenceSecretPolicy"] = {
            "Type": "AWS::IAM::Policy",
            "Properties": {
                "PolicyName": "WritingReferenceCredential",
                "Roles": [{"Ref": "TaskDefExecutionRoleB4775C97"}],
                "PolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Action": "secretsmanager:GetSecretValue",
                        "Resource": secret_arn,
                    }],
                },
            },
        }
        backend["Secrets"] = [{"Name": "FIRECRAWL_API_KEY", "ValueFrom": secret_arn}]
        service["DependsOn"].append("WritingReferenceSecretPolicy")
    return result


def write_private(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--images", type=Path)
    parser.add_argument("--reference-secret", type=Path)
    args = parser.parse_args()
    original = json.loads(args.baseline.read_text())
    support = support_template(original)
    args.output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_private(args.output_directory / "support-template.json", support)
    print("Support template: seven additions; existing HTTPS listener updated; existing data and task definition preserved.")
    if args.images:
        images = json.loads(args.images.read_text())
        reference_secret = json.loads(args.reference_secret.read_text()) if args.reference_secret else None
        application = application_template(support, images, reference_secret)
        write_private(args.output_directory / "application-template.json", application)
        print("Application template: immutable frontend/backend images; existing Fargate size; no public backend ingress.")


if __name__ == "__main__":
    main()
