"""Apply the workspace palette and logo to the existing Cognito app client.

The user-pool tier, users, OAuth grants, and authentication policies are unchanged.
The domain branding version/language are managed through the stack separately.
"""
import argparse
import copy
import json
from pathlib import Path

import boto3

PALETTE = {
    "0972d3ff": "345c44ff",
    "033160ff": "254a34ff",
    "f2f8fdff": "eaf1e8ff",
    "d3e7f9ff": "dce8d6ff",
    "000716ff": "29372eff",
    "414d5cff": "495b42ff",
    "5f6b7aff": "697367ff",
    "7d8998ff": "97a28eff",
    "c6c6cdff": "e4e7dfff",
    "ebebf0ff": "e4e7dfff",
    "d5dbdbff": "e4e7dfff",
    "fafafaff": "fafbf7ff",
    "fff7f7ff": "fff5eeff",
    "d91515ff": "935c43ff",
    "037f0cff": "598461ff",
    "f2fcf3ff": "eaf1e8ff",
}


def themed(value):
    if isinstance(value, dict):
        return {key: themed(item) for key, item in value.items()}
    if isinstance(value, list):
        return [themed(item) for item in value]
    return PALETTE.get(value.lower(), value) if isinstance(value, str) else value


def workspace_settings(defaults):
    settings = themed(copy.deepcopy(defaults))
    categories = settings["categories"]
    categories["global"]["colorSchemeMode"] = "LIGHT"
    categories["global"]["pageHeader"]["enabled"] = False
    categories["global"]["pageFooter"]["enabled"] = False
    categories["global"]["spacingDensity"] = "REGULAR"
    categories["form"]["displayGraphics"] = False
    categories["form"]["instructions"]["enabled"] = True
    categories["form"]["languageSelector"]["enabled"] = False
    categories["form"]["location"] = {"horizontal": "CENTER", "vertical": "CENTER"}

    components = settings["components"]
    components["pageBackground"]["image"]["enabled"] = False
    components["pageBackground"]["lightMode"]["color"] = "f4f5f0ff"
    components["favicon"]["enabledTypes"] = ["SVG"]
    components["form"]["backgroundImage"]["enabled"] = False
    components["form"]["borderRadius"] = 8.0
    components["form"]["lightMode"] = {
        "backgroundColor": "ffffffff",
        "borderColor": "e4e7dfff",
    }
    components["form"]["logo"] = {
        "enabled": True, "location": "CENTER", "position": "TOP", "formInclusion": "IN",
    }
    components["pageText"]["lightMode"] = {
        "bodyColor": "29372eff", "headingColor": "29372eff", "descriptionColor": "697367ff",
    }
    classes = settings["componentClasses"]
    classes["buttons"]["borderRadius"] = 6.0
    classes["input"]["borderRadius"] = 6.0
    classes["input"]["lightMode"] = {
        "defaults": {"backgroundColor": "ffffffff", "borderColor": "7f8d75ff"},
        "placeholderColor": "697367ff",
    }
    classes["focusState"]["lightMode"]["borderColor"] = "4e805cff"
    classes["inputLabel"]["lightMode"]["textColor"] = "29372eff"
    components["alert"]["borderRadius"] = 6.0
    return settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-pool-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--region", default="ap-northeast-2")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    client = boto3.client("cognito-idp", region_name=args.region)
    try:
        current = client.describe_managed_login_branding_by_client(
            UserPoolId=args.user_pool_id, ClientId=args.client_id, ReturnMergedResources=True,
        )["ManagedLoginBranding"]
    except client.exceptions.ResourceNotFoundException:
        client.create_managed_login_branding(
            UserPoolId=args.user_pool_id, ClientId=args.client_id, UseCognitoProvidedValues=True,
        )
        current = client.describe_managed_login_branding_by_client(
            UserPoolId=args.user_pool_id, ClientId=args.client_id, ReturnMergedResources=True,
        )["ManagedLoginBranding"]
    settings = workspace_settings(current["Settings"])
    (directory / "settings.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2))
    assets = [
        {"Category": "FORM_LOGO", "ColorMode": mode, "Extension": "PNG",
         "Bytes": (directory / "wordmark.png").read_bytes()}
        for mode in ["LIGHT", "DARK"]
    ] + [
        {"Category": "FAVICON_SVG", "ColorMode": mode, "Extension": "SVG",
         "Bytes": (directory / "favicon.svg").read_bytes()}
        for mode in ["LIGHT", "DARK"]
    ]
    result = client.update_managed_login_branding(
        UserPoolId=args.user_pool_id,
        ManagedLoginBrandingId=current["ManagedLoginBrandingId"],
        UseCognitoProvidedValues=False,
        Settings=settings,
        Assets=assets,
    )
    print(json.dumps({
        "brandingId": result["ManagedLoginBranding"]["ManagedLoginBrandingId"],
        "palette": "Open Canvas workspace",
        "logo": "FORM_LOGO",
        "colorScheme": "LIGHT",
    }))


if __name__ == "__main__":
    main()
