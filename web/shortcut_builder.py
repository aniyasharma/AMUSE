"""Build an installable AMUSE Watch Shortcuts file (signed when possible)."""

from __future__ import annotations

import plistlib
import subprocess
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNSIGNED = ROOT / "web" / "static" / "AMUSE-Watch.unsigned.shortcut"
SIGNED = ROOT / "web" / "static" / "AMUSE-Watch.shortcut"


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def _type_filter(sample_type: str, days: str = "7") -> dict:
    return {
        "Value": {
            "WFActionParameterFilterPrefix": 1,
            "WFContentPredicateBoundedDate": False,
            "WFActionParameterFilterTemplates": [
                {
                    "Bounded": True,
                    "Operator": 4,
                    "Property": "Type",
                    "Removable": False,
                    "Values": {
                        "Enumeration": {
                            "Value": sample_type,
                            "WFSerializationType": "WFStringSubstitutableState",
                        }
                    },
                },
                {
                    "Bounded": True,
                    "Operator": 1002,
                    "Property": "Start Date",
                    "Removable": False,
                    "Values": {
                        "Number": days,
                        "Unit": 16,
                    },
                },
            ],
        },
        "WFSerializationType": "WFContentPredicateTableTemplate",
    }


def _output_ref(name: str, output_uuid: str) -> dict:
    return {
        "Value": {
            "OutputName": name,
            "OutputUUID": output_uuid,
            "Type": "ActionOutput",
        },
        "WFSerializationType": "WFTextTokenAttachment",
    }


def _find_health(sample_type: str, action_uuid: str, limit: int = 1) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.filter.health.quantity",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
            "WFContentItemFilter": _type_filter(sample_type),
            "WFContentItemLimitEnabled": True,
            "WFContentItemLimitNumber": limit,
        },
    }


def _get_detail(property_name: str, action_uuid: str, source_uuid: str) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.properties.health.quantity",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
            "WFContentItemPropertyName": property_name,
            "WFInput": _output_ref("Health Samples", source_uuid),
        },
    }


def _set_variable(name: str, action_uuid: str, source_uuid: str, source_name: str) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.setvariable",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
            "WFVariableName": name,
            "WFInput": _output_ref(source_name, source_uuid),
        },
    }


def _ask_number(prompt: str, action_uuid: str) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.ask",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
            "WFAskActionPrompt": prompt,
            "WFInputType": "Number",
        },
    }


def _variable_token(name: str) -> dict:
    return {
        "VariableName": name,
        "Type": "Variable",
    }


def build_workflow(base_url: str) -> dict:
    """base_url like http://192.168.1.20:8501 (no trailing query)."""

    base = base_url.rstrip("/")
    prefix = f"{base}/?hk_hrv="
    mid = "&hk_sleep="
    end = "&hk_hr="

    hrv_find = _uid()
    hrv_val = _uid()
    hrv_var = _uid()
    hr_find = _uid()
    hr_val = _uid()
    hr_var = _uid()
    sleep_ask = _uid()
    sleep_var = _uid()
    text_uuid = _uid()
    open_uuid = _uid()

    # Text: PREFIX + HRV + MID + SLEEP + END + HR
    marker = "￼"
    text_string = f"{prefix}{marker}{mid}{marker}{end}{marker}"
    p1 = len(prefix)
    p2 = len(prefix) + 1 + len(mid)
    p3 = len(prefix) + 1 + len(mid) + 1 + len(end)

    actions = [
        # Watch / HealthKit — HRV + resting HR automatic
        _find_health("Heart Rate Variability", hrv_find, 1),
        _get_detail("Value", hrv_val, hrv_find),
        _set_variable("AMUSE_HRV", hrv_var, hrv_val, "Details of Health Sample"),
        _find_health("Resting Heart Rate", hr_find, 1),
        _get_detail("Value", hr_val, hr_find),
        _set_variable("AMUSE_HR", hr_var, hr_val, "Details of Health Sample"),
        # Sleep duration math is brittle across iOS versions — ask once, Watch HRV still auto
        _ask_number("Hours slept last night (from your Apple Watch sleep ring)", sleep_ask),
        _set_variable("AMUSE_SLEEP", sleep_var, sleep_ask, "Provided Input"),
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "UUID": text_uuid,
                "WFTextActionText": {
                    "Value": {
                        "string": text_string,
                        "attachmentsByRange": {
                            f"{{{p1}, 1}}": _variable_token("AMUSE_HRV"),
                            f"{{{p2}, 1}}": _variable_token("AMUSE_SLEEP"),
                            f"{{{p3}, 1}}": _variable_token("AMUSE_HR"),
                        },
                    },
                    "WFSerializationType": "WFTextTokenString",
                },
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.openurl",
            "WFWorkflowActionParameters": {
                "UUID": open_uuid,
                "WFInput": _output_ref("Text", text_uuid),
            },
        },
    ]

    return {
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "1300.1",
        "WFWorkflowClientRelease": "3.0",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {
            "WFWorkflowIconStartColor": 4282601983,
            "WFWorkflowIconGlyphNumber": 59750,
        },
        "WFWorkflowImportQuestions": [],
        "WFWorkflowTypes": [],
        "WFWorkflowInputContentItemClasses": [],
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowName": "AMUSE Watch",
    }


def write_unsigned(base_url: str, path: Path | None = None) -> Path:
    path = path or UNSIGNED
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(build_workflow(base_url), handle, fmt=plistlib.FMT_XML)
    return path


def try_sign(unsigned: Path | None = None, signed: Path | None = None) -> Path | None:
    unsigned = unsigned or UNSIGNED
    signed = signed or SIGNED
    if not unsigned.exists():
        return None
    if signed.exists():
        signed.unlink()
    try:
        result = subprocess.run(
            [
                "shortcuts",
                "sign",
                "--mode",
                "anyone",
                "--input",
                str(unsigned),
                "--output",
                str(signed),
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("shortcuts sign failed:", exc)
        return None
    if result.returncode != 0:
        print("shortcuts sign error:", result.stderr or result.stdout)
        return None
    if not signed.exists() or signed.stat().st_size < 100:
        print("shortcuts sign produced no file")
        return None
    # Signed packages start with AEA1
    magic = signed.read_bytes()[:4]
    if magic != b"AEA1":
        print("shortcuts sign output not AEA1:", magic)
        return None
    return signed


def build_for_base_url(base_url: str) -> tuple[Path, bool]:
    """Return (path_to_serve, signed?)."""

    write_unsigned(base_url)
    signed = try_sign()
    if signed:
        return signed, True
    # Fall back to unsigned XML plist; Share → Shortcuts → Add Shortcut on iPhone.
    dest = SIGNED
    dest.write_bytes(UNSIGNED.read_bytes())
    return dest, False
