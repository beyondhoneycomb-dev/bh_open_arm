"""MJCF v2 asset invariants for the OpenArm bimanual model (WP-0C-03).

This module is the file-internal contradiction detector the plan calls the "MJCF
invariant checker". It parses the XML directly (never through the MuJoCo
compiler) so that it judges what the asset *declares*, joint class against
actuator class, rather than what the compiler resolves them to. A resolved model
hides the contradiction the check exists to find: MuJoCo happily compiles a joint
whose ``class`` names one motor while its actuator names another.

The invariants:

- Every actuated joint's motor family, read from its joint ``class``, equals the
  motor family read from its actuator ``class``. The lone sanctioned divergence
  is the gripper, whose ``motor_finger`` joint dynamics are driven by a
  ``position_DM4310`` actuator upstream by design; it is reported as a named
  divergence, never folded into the pass set silently, so a real typo of the same
  shape (J7's ``motor_DM3507`` against a ``position_DM4310`` actuator) still lands
  in the violation bucket.
- Wrist joint 7 references ``motor_DM4310`` on both arms, and nothing references
  the ``motor_DM3507`` typo class (the ``<default>`` definition may remain; the
  criterion is zero references).
- Joint 7's resolved dynamics are the DM4310 centre values, never the typo triple
  ``0.0049 / 0.01 / 0.01`` — the source of any J7 domain-randomization centre is
  the fixed asset, not the bug.
- Joint 2 carries the v2 limit magnitudes and no joint retains the v1 ``±1.745329``
  shoulder range.
- In a cell scene the stereo head cameras hang under ``openarm_lifter_link``; a
  scene that leaves them parented to the world is reported as a warning, not a
  hard failure, because both the upstream cell and the re-parented variant are
  legitimate assets that a caller may load for different reasons.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

MOTOR_CLASS_PREFIX = "motor_"
POSITION_CLASS_PREFIX = "position_"

TYPO_MOTOR_CLASS = "motor_DM3507"
J7_MOTOR_CLASS = "motor_DM4310"

# The typo class's dynamics triple; a J7 resolving to these is running the bug.
TYPO_FRICTIONLOSS = 0.01
TYPO_DAMPING = 0.01
TYPO_ARMATURE = 0.0049

# DM4310 centre values J7 must resolve to after the fix (== J5/J6).
DM4310_FRICTIONLOSS = 0.04
DM4310_DAMPING = 0.9
DM4310_ARMATURE = 0.0100
DM4310_FORCERANGE = 7.0

J7_JOINTS = ("openarm_left_joint7", "openarm_right_joint7")
J2_JOINTS = ("openarm_left_joint2", "openarm_right_joint2")

# v2 shoulder limits are the +pi/2-shifted range; the right arm reads
# (-0.17453, 3.3161) and the left arm mirrors it.
V2_J2_RIGHT_LIMITS = (-0.17453, 3.3161)
V2_J2_LEFT_LIMITS = (-3.3161, 0.17453)
# The v1 shoulder range this asset must not retain anywhere.
V1_SHOULDER_LIMIT = 1.745329

LIFTER_BODY = "openarm_lifter_link"
HEAD_CAMERA_PREFIX = "camera_head"
WORLD_PARENT = "world"

# The only joint/actuator motor-family pair that may differ without being a fault:
# the gripper's motor_finger joint is actuated through DM4310 position gains.
SANCTIONED_CROSS_FAMILY = frozenset({("finger", "DM4310")})

STATUS_CONSISTENT = "CONSISTENT"
STATUS_KNOWN_DIVERGENCE = "KNOWN_DIVERGENCE"
STATUS_VIOLATION = "VIOLATION"

# Float comparison tolerance for limit and dynamics literals in the asset.
_LIMIT_TOLERANCE = 1e-6


def motor_family(class_name: str) -> str:
    """Return the motor family a class name denotes.

    ``motor_DM4310`` and ``position_DM4310`` both denote ``DM4310``; ``lifter`` and
    ``position_lifter`` both denote ``lifter``; ``motor_finger`` denotes ``finger``.

    Args:
        class_name: A MuJoCo ``<default>`` class name.

    Returns:
        (str) The family token with any ``motor_``/``position_`` prefix stripped.
    """
    for prefix in (MOTOR_CLASS_PREFIX, POSITION_CLASS_PREFIX):
        if class_name.startswith(prefix):
            return class_name[len(prefix) :]
    return class_name


@dataclass(frozen=True)
class ClassDynamics:
    """Dynamics a ``<default>`` class assigns to the joints that inherit it."""

    frictionloss: float | None
    damping: float | None
    armature: float | None
    forcerange: tuple[float, float] | None

    def is_typo_triple(self) -> bool:
        """Whether these dynamics are the ``motor_DM3507`` typo values."""
        return (
            self.armature is not None
            and abs(self.armature - TYPO_ARMATURE) < _LIMIT_TOLERANCE
            and self.damping is not None
            and abs(self.damping - TYPO_DAMPING) < _LIMIT_TOLERANCE
        )

    def is_dm4310_centre(self) -> bool:
        """Whether these dynamics are the DM4310 centre values J7 must resolve to."""
        return (
            self.frictionloss is not None
            and abs(self.frictionloss - DM4310_FRICTIONLOSS) < _LIMIT_TOLERANCE
            and self.damping is not None
            and abs(self.damping - DM4310_DAMPING) < _LIMIT_TOLERANCE
            and self.armature is not None
            and abs(self.armature - DM4310_ARMATURE) < _LIMIT_TOLERANCE
        )


@dataclass(frozen=True)
class ConsistencyFinding:
    """One actuated joint's motor-family comparison of joint class vs actuator class."""

    joint: str
    joint_class: str
    actuator_class: str
    joint_family: str
    actuator_family: str
    status: str


@dataclass
class AuditReport:
    """The full result of auditing one MJCF file.

    ``ok`` is the hard verdict over the checks that apply to this file; warnings do
    not clear it but are surfaced (a non-re-parented cell scene is the canonical
    warning).
    """

    path: str
    ok: bool = True
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    consistency: list[ConsistencyFinding] = field(default_factory=list)

    def _fail(self, message: str) -> None:
        self.ok = False
        self.failures.append(message)

    def _warn(self, message: str) -> None:
        self.warnings.append(message)


def _load_root(source: str | Path | ET.Element) -> ET.Element:
    """Return the XML root for a path, a string of XML, or an element.

    A string is XML content when it starts with ``<`` (after leading whitespace);
    otherwise it is a filesystem path. A path never begins with ``<``, so the two
    cases never collide.
    """
    if isinstance(source, ET.Element):
        return source
    if isinstance(source, str) and source.lstrip().startswith("<"):
        return ET.fromstring(source)
    return ET.fromstring(Path(source).read_text(encoding="utf-8"))


def _describe_source(source: str | Path | ET.Element) -> str:
    """Return a short label for a source, never the full XML body."""
    if isinstance(source, ET.Element):
        return "<element>"
    if isinstance(source, str) and source.lstrip().startswith("<"):
        return "<xml>"
    return str(source)


def parse_default_dynamics(root: ET.Element) -> dict[str, ClassDynamics]:
    """Map each ``<default class=...>`` to the dynamics it declares.

    Args:
        root: The MJCF document root.

    Returns:
        (dict[str, ClassDynamics]) Class name to its joint/actuator dynamics.
    """
    dynamics: dict[str, ClassDynamics] = {}
    for default_el in root.iter("default"):
        class_name = default_el.get("class")
        if class_name is None:
            continue
        joint_el = default_el.find("joint")
        force_source = default_el.find("motor")
        if force_source is None:
            force_source = default_el.find("position")
        forcerange = None
        if force_source is not None:
            forcerange = _parse_pair(force_source.get("forcerange"))
        dynamics[class_name] = ClassDynamics(
            frictionloss=_maybe_float(joint_el, "frictionloss") if joint_el is not None else None,
            damping=_maybe_float(joint_el, "damping") if joint_el is not None else None,
            armature=_maybe_float(joint_el, "armature") if joint_el is not None else None,
            forcerange=forcerange,
        )
    return dynamics


def joint_classes(root: ET.Element) -> dict[str, str]:
    """Map each named body joint to its ``class``.

    Template joints inside ``<default>`` (no name) and equality mimic joints (no
    ``class``) are excluded, so only real articulated joints remain.

    Args:
        root: The MJCF document root.

    Returns:
        (dict[str, str]) Joint name to its class name.
    """
    return {
        joint.get("name", ""): joint.get("class", "")
        for joint in root.iter("joint")
        if joint.get("name") and joint.get("class")
    }


def actuator_joint_classes(root: ET.Element) -> dict[str, str]:
    """Map each actuated joint to the class of the actuator that drives it.

    Args:
        root: The MJCF document root.

    Returns:
        (dict[str, str]) Joint name to actuator class name.
    """
    actuator = root.find("actuator")
    if actuator is None:
        return {}
    mapping: dict[str, str] = {}
    for element in actuator:
        joint_name = element.get("joint")
        actuator_class = element.get("class")
        if joint_name and actuator_class:
            mapping[joint_name] = actuator_class
    return mapping


def check_motor_class_consistency(root: ET.Element) -> list[ConsistencyFinding]:
    """Compare every actuated joint's motor family against its actuator's.

    Args:
        root: The MJCF document root.

    Returns:
        (list[ConsistencyFinding]) One finding per actuated joint, ordered by joint.
    """
    declared = joint_classes(root)
    driven = actuator_joint_classes(root)
    findings: list[ConsistencyFinding] = []
    for joint_name in sorted(driven):
        actuator_class = driven[joint_name]
        joint_class = declared.get(joint_name)
        if joint_class is None:
            continue
        joint_fam = motor_family(joint_class)
        actuator_fam = motor_family(actuator_class)
        if joint_fam == actuator_fam:
            status = STATUS_CONSISTENT
        elif (joint_fam, actuator_fam) in SANCTIONED_CROSS_FAMILY:
            status = STATUS_KNOWN_DIVERGENCE
        else:
            status = STATUS_VIOLATION
        findings.append(
            ConsistencyFinding(
                joint=joint_name,
                joint_class=joint_class,
                actuator_class=actuator_class,
                joint_family=joint_fam,
                actuator_family=actuator_fam,
                status=status,
            )
        )
    return findings


def head_camera_parents(source: str | Path | ET.Element) -> dict[str, str]:
    """Map each stereo head camera to the name of its enclosing body.

    Args:
        source: Path to an MJCF file, a string of MJCF, or a parsed root element.

    Returns:
        (dict[str, str]) Head camera name to its parent body name, ``"world"`` when
        the camera is a direct child of the worldbody.
    """
    root = _load_root(source)
    parents = {child: parent for parent in root.iter() for child in parent}
    result: dict[str, str] = {}
    for camera in root.iter("camera"):
        name = camera.get("name", "")
        if not name.startswith(HEAD_CAMERA_PREFIX):
            continue
        node = parents.get(camera)
        body_name = WORLD_PARENT
        while node is not None:
            if node.tag == "body":
                body_name = node.get("name", WORLD_PARENT)
                break
            node = parents.get(node)
        result[name] = body_name
    return result


def _maybe_float(element: ET.Element, attribute: str) -> float | None:
    """Return a float attribute, or None when absent."""
    value = element.get(attribute)
    return float(value) if value is not None else None


def _parse_pair(value: str | None) -> tuple[float, float] | None:
    """Parse a two-number MuJoCo range/forcerange attribute."""
    if value is None:
        return None
    parts = value.split()
    if len(parts) != 2:
        return None
    return float(parts[0]), float(parts[1])


def _close(pair: tuple[float, float] | None, expected: tuple[float, float]) -> bool:
    """Whether a parsed pair matches an expected pair within tolerance."""
    if pair is None:
        return False
    return abs(pair[0] - expected[0]) < _LIMIT_TOLERANCE and (
        abs(pair[1] - expected[1]) < _LIMIT_TOLERANCE
    )


def audit(source: str | Path | ET.Element) -> AuditReport:
    """Audit an MJCF file for the WP-0C-03 invariants.

    Only invariants whose subject exists in the file are enforced: the J7/J2/motor
    checks apply to the bimanual asset, the head-camera check to a cell scene. A
    cell scene attaches the bimanual as a submodel, so its arm joints are absent
    from this XML and are not judged here.

    Args:
        source: Path to an MJCF file, a string of MJCF, or a parsed root element.

    Returns:
        (AuditReport) The verdict, with per-check failures and warnings.
    """
    root = _load_root(source)
    report = AuditReport(path=_describe_source(source))

    report.consistency = check_motor_class_consistency(root)
    violations = [finding for finding in report.consistency if finding.status == STATUS_VIOLATION]
    for finding in violations:
        report._fail(
            f"motor-class contradiction on {finding.joint}: joint class {finding.joint_class} "
            f"({finding.joint_family}) vs actuator class {finding.actuator_class} "
            f"({finding.actuator_family})"
        )

    declared = joint_classes(root)
    has_j7 = any(joint in declared for joint in J7_JOINTS)
    if has_j7:
        _audit_joint7(root, declared, report)

    has_j2 = any(joint in declared for joint in J2_JOINTS)
    if has_j2:
        _audit_joint2(root, report)

    head_parents = head_camera_parents(root)
    if head_parents:
        if all(parent == LIFTER_BODY for parent in head_parents.values()):
            pass
        else:
            stray = sorted(name for name, parent in head_parents.items() if parent != LIFTER_BODY)
            report._warn(
                "head cameras not re-parented under "
                f"{LIFTER_BODY}: {', '.join(stray)} — sim/real head viewpoint diverges "
                "at lifter stroke != 0 (09 FR-SIM-006)"
            )

    return report


def _audit_joint7(root: ET.Element, declared: dict[str, str], report: AuditReport) -> None:
    """Enforce the J7 class, reference-count, and resolved-dynamics invariants."""
    for joint in J7_JOINTS:
        joint_class = declared.get(joint)
        if joint_class != J7_MOTOR_CLASS:
            report._fail(f"{joint} class is {joint_class!r}, expected {J7_MOTOR_CLASS!r}")

    typo_refs = sorted(name for name, cls in declared.items() if cls == TYPO_MOTOR_CLASS)
    if typo_refs:
        report._fail(
            f"{TYPO_MOTOR_CLASS} still referenced by {', '.join(typo_refs)} "
            f"({len(typo_refs)} reference(s), expected 0)"
        )

    dynamics = parse_default_dynamics(root)
    for joint in J7_JOINTS:
        joint_class = declared.get(joint)
        resolved = dynamics.get(joint_class) if joint_class else None
        if resolved is None:
            continue
        if resolved.is_typo_triple():
            report._fail(
                f"{joint} resolves to the typo dynamics (armature {TYPO_ARMATURE}); "
                "a J7 DR centre taken from this asset would be the bug"
            )
        elif not resolved.is_dm4310_centre():
            report._fail(
                f"{joint} does not resolve to the DM4310 centre values "
                f"(frictionloss {DM4310_FRICTIONLOSS} / damping {DM4310_DAMPING} / "
                f"armature {DM4310_ARMATURE})"
            )


def _audit_joint2(root: ET.Element, report: AuditReport) -> None:
    """Enforce the v2 shoulder limits and the absence of any v1 remnant."""
    ranges: dict[str, tuple[float, float] | None] = {}
    for joint in root.iter("joint"):
        name = joint.get("name")
        if name in J2_JOINTS:
            ranges[name] = _parse_pair(joint.get("range"))

    right = ranges.get("openarm_right_joint2")
    if not _close(right, V2_J2_RIGHT_LIMITS):
        report._fail(f"openarm_right_joint2 range {right}, expected {V2_J2_RIGHT_LIMITS}")
    left = ranges.get("openarm_left_joint2")
    if not _close(left, V2_J2_LEFT_LIMITS):
        report._fail(f"openarm_left_joint2 range {left}, expected {V2_J2_LEFT_LIMITS}")

    for joint in root.iter("joint"):
        pair = _parse_pair(joint.get("range"))
        if pair is None:
            continue
        if all(abs(abs(bound) - V1_SHOULDER_LIMIT) < _LIMIT_TOLERANCE for bound in pair):
            report._fail(
                f"{joint.get('name')} retains the v1 shoulder range "
                f"(+/-{V1_SHOULDER_LIMIT}); v2 shifted joint2 by +pi/2"
            )


def main(argv: list[str] | None = None) -> int:
    """Run the audit on one or more MJCF paths and print the verdict.

    Returns:
        (int) 0 when every audited file passes, 1 otherwise.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Audit MJCF v2 assets for WP-0C-03 invariants.")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)

    exit_code = 0
    for path in args.paths:
        report = audit(path)
        status = "PASS" if report.ok else "FAIL"
        print(f"{status}  {path}")
        for failure in report.failures:
            print(f"  FAIL  {failure}")
        for warning in report.warnings:
            print(f"  WARN  {warning}")
        if not report.ok:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
