from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import struct
from typing import Any, Mapping

from ygo_effect_dsl.engine.action import (
    action_aggregation_compatibility_report,
    derive_ocgcore_action_aggregation,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.route_dsl import load_route_document


ACTION_AGGREGATION_EDGE_EVIDENCE_SCHEMA_VERSION = (
    "ocgcore-action-aggregation-edge-evidence-v1"
)
_REAL_ROUTE_FILENAMES = (
    "real_core_action_aggregation.route.yaml",
    "real_core_effect_veiler.route.yaml",
    "real_core_effect_veiler_interrupted.route.yaml",
    "real_core_temporary_atk.route.yaml",
)


def _trace(*frames: tuple[int, bytes]) -> dict[str, Any]:
    return {
        "frames": [
            {
                "frame_index": index,
                "message_type": message_type,
                "payload_hex": payload.hex(),
            }
            for index, (message_type, payload) in enumerate(frames)
        ]
    }


def _event(
    step: int,
    *,
    action_kind: str,
    request_type: str,
    candidate_id: str,
    core_output: Mapping[str, Any],
    cancelable: bool = False,
    card_ref: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    semantic = {
        "action_kind": action_kind,
        "candidate_id": candidate_id,
        "request_type": request_type,
        "step": step,
    }
    action_id = stable_digest(semantic, prefix="act_edge_")
    occurrence_id = stable_digest(
        {"action_id": action_id, "state_hash_before": f"state_edge_{step}", "step": step},
        prefix="aocc_edge_",
    )
    selected = action_kind != "DECLINE"
    return {
        "action": {
            "action_id": action_id,
            "kind": action_kind,
            "player": 0,
            "selections": (
                [{"candidate_id": candidate_id}] if selected else []
            ),
        },
        "action_occurrence_id": occurrence_id,
        "chain_index": 1,
        "core_output": to_canonical_data(core_output),
        "request": {
            "candidates": [
                {
                    "candidate_id": candidate_id,
                    "card_ref": card_ref,
                    "kind": "card",
                    "label": candidate_id,
                }
            ],
            "context": {"extra": {"cancelable": cancelable}},
            "player": 0,
            "request_type": request_type,
        },
        "state_hash_after": f"state_edge_{step + 1}",
        "state_hash_before": f"state_edge_{step}",
        "step": step,
        "turn": 1,
        "turn_action_index": step,
    }


def _replay(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "events": events,
        "initial_core_output": _trace((16, b"")),
        "version_metadata": {"ocgcore_api": "11.0"},
    }


def _move(card_ref: Mapping[str, int]) -> bytes:
    return struct.pack(
        "<IBBIIBBIII",
        card_ref["public_card_id"],
        card_ref["controller"],
        card_ref["location"],
        card_ref["sequence"],
        card_ref["position"],
        card_ref["controller"],
        16,
        0,
        1,
        0x80 | 0x4000,
    )


def _edge_replays() -> dict[str, dict[str, Any]]:
    cancel = _replay(
        [
            _event(
                0,
                action_kind="ACTIVATE_EFFECT",
                request_type="select_chain",
                candidate_id="effect:cancel",
                core_output=_trace((15, b"")),
            ),
            _event(
                1,
                action_kind="DECLINE",
                request_type="select_card",
                candidate_id="control:cancel",
                cancelable=True,
                core_output=_trace((16, b"")),
            ),
        ]
    )
    fizzle = _replay(
        [
            _event(
                0,
                action_kind="ACTIVATE_EFFECT",
                request_type="select_chain",
                candidate_id="effect:fizzle",
                core_output=_trace((71, b"\x01"), (16, b"")),
            ),
            _event(
                1,
                action_kind="PASS",
                request_type="select_chain",
                candidate_id="control:pass:1",
                core_output=_trace(
                    (72, b"\x01"),
                    (76, b"\x01"),
                    (73, b"\x01"),
                    (74, b""),
                    (16, b""),
                ),
            ),
            _event(
                2,
                action_kind="PASS",
                request_type="select_chain",
                candidate_id="control:pass:2",
                core_output=_trace((16, b"")),
            ),
        ]
    )
    multi_chain_negation = _replay(
        [
            _event(
                0,
                action_kind="ACTIVATE_EFFECT",
                request_type="select_chain",
                candidate_id="effect:chain:1",
                core_output=_trace((71, b"\x01"), (16, b"")),
            ),
            _event(
                1,
                action_kind="ACTIVATE_EFFECT",
                request_type="select_chain",
                candidate_id="effect:chain:2",
                core_output=_trace((71, b"\x02"), (16, b"")),
            ),
            _event(
                2,
                action_kind="PASS",
                request_type="select_chain",
                candidate_id="control:pass:chain",
                core_output=_trace(
                    (72, b"\x02"),
                    (75, b"\x02"),
                    (73, b"\x02"),
                    (72, b"\x01"),
                    (73, b"\x01"),
                    (74, b""),
                    (16, b""),
                ),
            ),
            _event(
                3,
                action_kind="PASS",
                request_type="select_chain",
                candidate_id="control:pass:after-chain",
                core_output=_trace((16, b"")),
            ),
        ]
    )
    first_cost = {
        "controller": 0,
        "location": 2,
        "position": 10,
        "public_card_id": 1001,
        "sequence": 1,
    }
    second_cost = {**first_cost, "public_card_id": 1002, "sequence": 2}
    discard_hint = struct.pack("<BBQ", 3, 0, 501)
    target_hint = struct.pack("<BBQ", 3, 0, 551)
    multi_select = _replay(
        [
            _event(
                0,
                action_kind="ACTIVATE_EFFECT",
                request_type="select_chain",
                candidate_id="effect:multi",
                core_output=_trace((2, discard_hint), (15, b"")),
            ),
            _event(
                1,
                action_kind="SELECT_CARD",
                request_type="select_card",
                candidate_id="cost:first",
                card_ref=first_cost,
                core_output=_trace(
                    (50, _move(first_cost)), (2, discard_hint), (15, b"")
                ),
            ),
            _event(
                2,
                action_kind="SELECT_CARD",
                request_type="select_card",
                candidate_id="cost:second",
                card_ref=second_cost,
                core_output=_trace(
                    (50, _move(second_cost)), (2, target_hint), (15, b"")
                ),
            ),
            _event(
                3,
                action_kind="SELECT_CARD",
                request_type="select_card",
                candidate_id="target:field",
                card_ref={
                    "controller": 0,
                    "location": 4,
                    "position": 1,
                    "public_card_id": 2001,
                    "sequence": 0,
                },
                core_output=_trace((71, b"\x01"), (16, b"")),
            ),
        ]
    )
    resolution = _replay(
        [
            _event(
                0,
                action_kind="ACTIVATE_EFFECT",
                request_type="select_chain",
                candidate_id="effect:resolution",
                core_output=_trace((71, b"\x01"), (16, b"")),
            ),
            _event(
                1,
                action_kind="PASS",
                request_type="select_chain",
                candidate_id="control:pass",
                core_output=_trace(
                    (72, b"\x01"), (2, target_hint), (15, b"")
                ),
            ),
            _event(
                2,
                action_kind="SELECT_CARD",
                request_type="select_card",
                candidate_id="resolution:card",
                core_output=_trace((14, b"")),
            ),
            _event(
                3,
                action_kind="SELECT_OPTION",
                request_type="select_option",
                candidate_id="resolution:option",
                core_output=_trace(
                    (73, b"\x01"), (74, b""), (16, b"")
                ),
            ),
        ]
    )
    return {
        "cancel": cancel,
        "fizzle_or_disable": fizzle,
        "multi_chain_negation": multi_chain_negation,
        "multi_selection": multi_select,
        "resolution_selection": resolution,
    }


def _edge_summary(replay: Mapping[str, Any]) -> dict[str, Any]:
    before = stable_digest(replay, prefix="edgereplay_")
    aggregation, evidence = derive_ocgcore_action_aggregation(replay)
    after = stable_digest(replay, prefix="edgereplay_")
    if before != after:
        raise ValueError("action aggregation mutated its atomic Replay input")
    return to_canonical_data(
        {
            "atomic_replay_digest_after": after,
            "atomic_replay_digest_before": before,
            "evidence_id": evidence["evidence_id"],
            "fallback_steps": evidence["fallback_steps"],
            "group_boundaries": evidence["group_boundaries"],
            "groups": [
                {
                    "atomic_steps": [part.step for part in group.parts],
                    "roles": [part.role.value for part in group.parts],
                }
                for group in aggregation.groups
            ],
            "lifecycle": [
                item["message_name"] for item in evidence["chain_lifecycle"]
            ],
        }
    )


def build_action_aggregation_edge_evidence(
    *, repo_root: str | Path | None = None
) -> dict[str, Any]:
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    prototype_dir = root / "examples" / "prototype"
    real_routes = []
    for filename in _REAL_ROUTE_FILENAMES:
        route = load_route_document(prototype_dir / filename)
        route_before = deepcopy(route)
        aggregation, evidence = derive_ocgcore_action_aggregation(route["replay"])
        if aggregation.to_dict() != route["presentation"]["action_aggregation"]:
            raise ValueError(f"{filename} stored aggregation is not reproducible")
        if evidence != route["presentation"]["action_aggregation_evidence"]:
            raise ValueError(f"{filename} stored evidence is not reproducible")
        if route != route_before:
            raise ValueError(f"{filename} was mutated during aggregation")
        real_routes.append(
            {
                "action_coordinate_digest": stable_digest(
                    [
                        {
                            "action_id": event["action"]["action_id"],
                            "action_occurrence_id": event.get("action_occurrence_id"),
                            "chain_index": event.get("chain_index"),
                            "step": event["step"],
                            "turn": event.get("turn"),
                            "turn_action_index": event.get("turn_action_index"),
                        }
                        for event in route["replay"]["events"]
                    ],
                    prefix="actioncoords_",
                ),
                "evidence_id": evidence["evidence_id"],
                "filename": filename,
                "interruption_digest": stable_digest(
                    route.get("interruptions", []), prefix="interruptions_"
                ),
                "replay_digest": stable_digest(
                    route["replay"], prefix="atomicreplay_"
                ),
                "route_id": route["route_id"],
            }
        )
    edge_fixtures = {
        name: _edge_summary(replay)
        for name, replay in sorted(_edge_replays().items())
    }
    identity = to_canonical_data(
        {
            "compatibility": action_aggregation_compatibility_report(),
            "edge_fixtures": edge_fixtures,
            "invariants": {
                "atomic_actions_mutated": False,
                "interruption_coordinates_mutated": False,
                "route_identity_input": False,
            },
            "real_core_routes": real_routes,
            "schema_version": ACTION_AGGREGATION_EDGE_EVIDENCE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="actaggedgeev_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="build action aggregation lifecycle edge evidence"
    )
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    evidence = build_action_aggregation_edge_evidence(repo_root=args.repo_root)
    serialized = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(serialized, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(
            f"action-aggregation-edge-evidence: wrote {args.out} "
            f"evidence_id={evidence['evidence_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
