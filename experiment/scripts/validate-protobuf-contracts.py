#!/usr/bin/env python3

"""Validate the canonical protobuf contract, its mirrors and generated stubs."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable

from google.protobuf import descriptor_pb2


SCHEMA_VERSION = "1.0.0"
CANONICAL_PATH = pathlib.PurePosixPath("protos/demo.proto")
MIRROR_PATHS = (
    pathlib.PurePosixPath("src/adservice/src/main/proto/demo.proto"),
    pathlib.PurePosixPath("src/currencyservice/proto/demo.proto"),
    pathlib.PurePosixPath("src/paymentservice/proto/demo.proto"),
)
GO_DESCRIPTOR_PATHS = (
    pathlib.PurePosixPath("src/checkoutservice/genproto/demo.pb.go"),
    pathlib.PurePosixPath("src/frontend/genproto/demo.pb.go"),
    pathlib.PurePosixPath("src/productcatalogservice/genproto/demo.pb.go"),
    pathlib.PurePosixPath("src/shippingservice/genproto/demo.pb.go"),
)
GO_GRPC_PATHS = tuple(
    pathlib.PurePosixPath(str(path).replace("demo.pb.go", "demo_grpc.pb.go"))
    for path in GO_DESCRIPTOR_PATHS
)
PYTHON_DESCRIPTOR_PATHS = (
    pathlib.PurePosixPath("src/emailservice/demo_pb2.py"),
    pathlib.PurePosixPath("src/recommendationservice/demo_pb2.py"),
)
PYTHON_GRPC_PATHS = tuple(
    pathlib.PurePosixPath(str(path).replace("demo_pb2.py", "demo_pb2_grpc.py"))
    for path in PYTHON_DESCRIPTOR_PATHS
)
CART_SUBSET_PATH = pathlib.PurePosixPath("src/cartservice/src/protos/Cart.proto")


class ValidationError(RuntimeError):
    """A deterministic protobuf validation error."""


def default_json_name(field_name: str) -> str:
    """Return protoc's default lowerCamelCase JSON name for a snake_case field."""

    result: list[str] = []
    capitalize_next = False
    for character in field_name:
        if character == "_":
            capitalize_next = True
        elif capitalize_next:
            result.append(character.upper())
            capitalize_next = False
        else:
            result.append(character)
    return "".join(result)


def normalize_descriptor(
    descriptor: descriptor_pb2.FileDescriptorProto,
) -> descriptor_pb2.FileDescriptorProto:
    """Normalize non-contractual compiler/version differences."""

    normalized = descriptor_pb2.FileDescriptorProto()
    normalized.CopyFrom(descriptor)
    normalized.ClearField("source_code_info")
    normalized.options.ClearField("go_package")

    def normalize_message(message: descriptor_pb2.DescriptorProto) -> None:
        for field in message.field:
            if not field.json_name or field.json_name == default_json_name(field.name):
                field.ClearField("json_name")
        for nested in message.nested_type:
            normalize_message(nested)

    for message in normalized.message_type:
        normalize_message(message)
    return normalized


def descriptor_sha256(descriptor: descriptor_pb2.FileDescriptorProto) -> str:
    normalized = normalize_descriptor(descriptor)
    return hashlib.sha256(normalized.SerializeToString(deterministic=True)).hexdigest()


def compile_proto(
    proto_file: pathlib.Path,
    include_dir: pathlib.Path,
    protoc: str,
) -> descriptor_pb2.FileDescriptorProto:
    with tempfile.TemporaryDirectory(prefix="pdt-proto-descriptor-") as temp_dir:
        output = pathlib.Path(temp_dir) / "descriptor.pb"
        subprocess.run(
            [
                protoc,
                f"--proto_path={include_dir}",
                f"--descriptor_set_out={output}",
                str(proto_file),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        descriptor_set = descriptor_pb2.FileDescriptorSet.FromString(output.read_bytes())
    if len(descriptor_set.file) != 1:
        raise ValidationError(f"expected one descriptor for {proto_file}")
    return descriptor_set.file[0]


def compile_proto_bytes(contents: bytes, protoc: str) -> descriptor_pb2.FileDescriptorProto:
    with tempfile.TemporaryDirectory(prefix="pdt-proto-baseline-") as temp_dir:
        proto_file = pathlib.Path(temp_dir) / "demo.proto"
        proto_file.write_bytes(contents)
        return compile_proto(proto_file, proto_file.parent, protoc)


def extract_go_descriptor(path: pathlib.Path) -> descriptor_pb2.FileDescriptorProto:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        r"var file_demo_proto_rawDesc = \[\]byte\{(.*?)\n\}",
        source,
        flags=re.DOTALL,
    )
    if not match:
        raise ValidationError(f"cannot find embedded descriptor in {path}")
    values = [
        int(value, 0)
        for value in re.findall(r"0x[0-9a-fA-F]+|\b\d+\b", match.group(1))
    ]
    try:
        return descriptor_pb2.FileDescriptorProto.FromString(bytes(values))
    except (ValueError, TypeError) as error:
        raise ValidationError(f"invalid embedded descriptor in {path}: {error}") from error


def extract_python_descriptor(path: pathlib.Path) -> descriptor_pb2.FileDescriptorProto:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "AddSerializedFile"
            and node.args
        ):
            try:
                raw_descriptor = ast.literal_eval(node.args[0])
            except (ValueError, TypeError, SyntaxError):
                continue
            if isinstance(raw_descriptor, bytes):
                return descriptor_pb2.FileDescriptorProto.FromString(raw_descriptor)
    raise ValidationError(f"cannot find embedded descriptor in {path}")


def expected_rpc_paths(descriptor: descriptor_pb2.FileDescriptorProto) -> set[str]:
    package_prefix = f"{descriptor.package}." if descriptor.package else ""
    return {
        f"/{package_prefix}{service.name}/{method.name}"
        for service in descriptor.service
        for method in service.method
    }


def extract_rpc_paths(path: pathlib.Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    return set(re.findall(r"['\"](/[^/'\"]+\.[^/'\"]+/[^/'\"]+)['\"]", source))


def flatten_messages(
    messages: Iterable[descriptor_pb2.DescriptorProto],
    prefix: str,
) -> dict[str, descriptor_pb2.DescriptorProto]:
    flattened: dict[str, descriptor_pb2.DescriptorProto] = {}
    for message in messages:
        full_name = f"{prefix}.{message.name}" if prefix else message.name
        flattened[full_name] = message
        flattened.update(flatten_messages(message.nested_type, full_name))
    return flattened


def flatten_enums(
    descriptor: descriptor_pb2.FileDescriptorProto,
) -> dict[str, descriptor_pb2.EnumDescriptorProto]:
    enums: dict[str, descriptor_pb2.EnumDescriptorProto] = {
        enum.name: enum for enum in descriptor.enum_type
    }

    def add_nested(message: descriptor_pb2.DescriptorProto, prefix: str) -> None:
        message_name = f"{prefix}.{message.name}" if prefix else message.name
        for enum in message.enum_type:
            enums[f"{message_name}.{enum.name}"] = enum
        for nested in message.nested_type:
            add_nested(nested, message_name)

    for message in descriptor.message_type:
        add_nested(message, "")
    return enums


def scalar_field_signature(field: descriptor_pb2.FieldDescriptorProto) -> tuple[object, ...]:
    return (
        field.name,
        field.number,
        field.label,
        field.type,
        field.type_name,
        field.oneof_index if field.HasField("oneof_index") else None,
        field.proto3_optional,
    )


def compatibility_errors(
    baseline: descriptor_pb2.FileDescriptorProto,
    candidate: descriptor_pb2.FileDescriptorProto,
) -> list[str]:
    """Apply a strict backward source-and-wire compatibility policy."""

    old = normalize_descriptor(baseline)
    new = normalize_descriptor(candidate)
    errors: list[str] = []
    if old.package != new.package:
        errors.append(f"package changed from {old.package!r} to {new.package!r}")
    if old.syntax != new.syntax:
        errors.append(f"syntax changed from {old.syntax!r} to {new.syntax!r}")

    old_messages = flatten_messages(old.message_type, "")
    new_messages = flatten_messages(new.message_type, "")
    for name, old_message in old_messages.items():
        new_message = new_messages.get(name)
        if new_message is None:
            errors.append(f"message removed: {name}")
            continue
        old_by_number = {field.number: field for field in old_message.field}
        new_by_number = {field.number: field for field in new_message.field}
        for number, old_field in old_by_number.items():
            new_field = new_by_number.get(number)
            if new_field is None:
                errors.append(f"field removed: {name}.{old_field.name} ({number})")
            elif scalar_field_signature(old_field) != scalar_field_signature(new_field):
                errors.append(
                    f"field changed incompatibly: {name}.{old_field.name} ({number})"
                )
        old_oneofs = [oneof.name for oneof in old_message.oneof_decl]
        new_oneofs = [oneof.name for oneof in new_message.oneof_decl]
        if old_oneofs != new_oneofs[: len(old_oneofs)]:
            errors.append(f"oneof declarations changed incompatibly: {name}")

    old_enums = flatten_enums(old)
    new_enums = flatten_enums(new)
    for name, old_enum in old_enums.items():
        new_enum = new_enums.get(name)
        if new_enum is None:
            errors.append(f"enum removed: {name}")
            continue
        new_values = {(value.name, value.number) for value in new_enum.value}
        for value in old_enum.value:
            if (value.name, value.number) not in new_values:
                errors.append(f"enum value changed or removed: {name}.{value.name}")

    new_services = {service.name: service for service in new.service}
    for old_service in old.service:
        new_service = new_services.get(old_service.name)
        if new_service is None:
            errors.append(f"service removed: {old_service.name}")
            continue
        new_methods = {method.name: method for method in new_service.method}
        for old_method in old_service.method:
            new_method = new_methods.get(old_method.name)
            if new_method is None:
                errors.append(f"RPC removed: {old_service.name}.{old_method.name}")
                continue
            old_signature = (
                old_method.input_type,
                old_method.output_type,
                old_method.client_streaming,
                old_method.server_streaming,
            )
            new_signature = (
                new_method.input_type,
                new_method.output_type,
                new_method.client_streaming,
                new_method.server_streaming,
            )
            if old_signature != new_signature:
                errors.append(f"RPC signature changed: {old_service.name}.{old_method.name}")
    return errors


def cart_subset_errors(
    canonical: descriptor_pb2.FileDescriptorProto,
    subset: descriptor_pb2.FileDescriptorProto,
) -> list[str]:
    """Validate the intentionally reduced C# Cart contract against the canonical file."""

    canonical = normalize_descriptor(canonical)
    subset = normalize_descriptor(subset)
    errors: list[str] = []
    canonical_services = {service.name: service for service in canonical.service}
    subset_services = {service.name: service for service in subset.service}
    cart_service = canonical_services.get("CartService")
    if cart_service is None or subset_services.get("CartService") != cart_service:
        errors.append("CartService declaration differs from the canonical contract")
        return errors
    if set(subset_services) != {"CartService"}:
        errors.append("Cart.proto must contain only CartService")

    canonical_messages = flatten_messages(canonical.message_type, "")
    subset_messages = flatten_messages(subset.message_type, "")
    pending = {
        type_name.removeprefix(f".{canonical.package}.")
        for method in cart_service.method
        for type_name in (method.input_type, method.output_type)
    }
    required: set[str] = set()
    while pending:
        message_name = pending.pop()
        if message_name in required:
            continue
        required.add(message_name)
        message = canonical_messages.get(message_name)
        if message is None:
            errors.append(f"canonical CartService references unknown message: {message_name}")
            continue
        for field in message.field:
            if field.type == descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE:
                pending.add(field.type_name.removeprefix(f".{canonical.package}."))

    if set(subset_messages) != required:
        errors.append(
            "Cart.proto message set differs: "
            f"expected={sorted(required)} actual={sorted(subset_messages)}"
        )
    for name in sorted(required & set(subset_messages)):
        if canonical_messages[name] != subset_messages[name]:
            errors.append(f"Cart.proto message differs from canonical contract: {name}")
    return errors


def git_file(repo_root: pathlib.Path, ref: str, path: pathlib.PurePosixPath) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{ref}:{path}"],
        check=True,
        capture_output=True,
    )
    return result.stdout


def git_file_differs(repo_root: pathlib.Path, ref: str, path: pathlib.PurePosixPath) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--quiet", ref, "--", str(path)],
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise subprocess.CalledProcessError(result.returncode, result.args)
    return result.returncode == 1


def relative(path: pathlib.Path, root: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def validate(args: argparse.Namespace) -> dict[str, object]:
    repo_root = args.repo_root.resolve()
    errors: list[str] = []
    checks: dict[str, object] = {}

    protoc_version = subprocess.run(
        [args.protoc, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    checks["protoc"] = {
        "actual_version": protoc_version,
        "expected_version": args.expected_protoc_version,
        "status": "pass" if protoc_version == args.expected_protoc_version else "fail",
    }
    if protoc_version != args.expected_protoc_version:
        errors.append(
            f"protoc version mismatch: expected {args.expected_protoc_version}, got {protoc_version}"
        )

    canonical_path = repo_root / CANONICAL_PATH
    canonical = compile_proto(canonical_path, canonical_path.parent, args.protoc)
    canonical_hash = descriptor_sha256(canonical)
    checks["canonical"] = {
        "path": str(CANONICAL_PATH),
        "normalized_descriptor_sha256": canonical_hash,
        "status": "pass",
    }

    mirror_results = []
    for mirror_relative in MIRROR_PATHS:
        mirror_path = repo_root / mirror_relative
        mirror = compile_proto(mirror_path, mirror_path.parent, args.protoc)
        status = "pass" if descriptor_sha256(mirror) == canonical_hash else "fail"
        mirror_results.append({"path": str(mirror_relative), "status": status})
        if status == "fail":
            errors.append(f"semantic protobuf mirror drift: {mirror_relative}")
    checks["semantic_mirrors"] = mirror_results

    cart_path = repo_root / CART_SUBSET_PATH
    cart_descriptor = compile_proto(cart_path, cart_path.parent, args.protoc)
    cart_errors = cart_subset_errors(canonical, cart_descriptor)
    checks["cart_subset"] = {
        "path": str(CART_SUBSET_PATH),
        "status": "fail" if cart_errors else "pass",
        "errors": cart_errors,
    }
    errors.extend(cart_errors)

    generated_results = []
    for generated_relative in GO_DESCRIPTOR_PATHS:
        generated = extract_go_descriptor(repo_root / generated_relative)
        status = "pass" if descriptor_sha256(generated) == canonical_hash else "fail"
        generated_results.append(
            {"path": str(generated_relative), "language": "go", "status": status}
        )
        if status == "fail":
            errors.append(f"generated protobuf descriptor drift: {generated_relative}")
    for generated_relative in PYTHON_DESCRIPTOR_PATHS:
        generated = extract_python_descriptor(repo_root / generated_relative)
        status = "pass" if descriptor_sha256(generated) == canonical_hash else "fail"
        generated_results.append(
            {"path": str(generated_relative), "language": "python", "status": status}
        )
        if status == "fail":
            errors.append(f"generated protobuf descriptor drift: {generated_relative}")
    checks["generated_descriptors"] = generated_results

    expected_paths = expected_rpc_paths(canonical)
    grpc_results = []
    for grpc_relative in (*GO_GRPC_PATHS, *PYTHON_GRPC_PATHS):
        actual_paths = extract_rpc_paths(repo_root / grpc_relative)
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        grpc_results.append(
            {
                "path": str(grpc_relative),
                "status": "fail" if missing or extra else "pass",
                "missing_rpc_paths": missing,
                "extra_rpc_paths": extra,
            }
        )
        if missing or extra:
            errors.append(f"generated gRPC method drift: {grpc_relative}")
    checks["generated_grpc_methods"] = grpc_results

    baseline_ref = args.base_ref
    if baseline_ref is None and git_file_differs(repo_root, "HEAD", CANONICAL_PATH):
        baseline_ref = "HEAD"
    compatibility: dict[str, object] = {
        "policy": "strict-backward-source-and-wire",
        "baseline_ref": baseline_ref,
        "status": "not-applicable",
        "errors": [],
    }
    if baseline_ref is not None:
        baseline = compile_proto_bytes(
            git_file(repo_root, baseline_ref, CANONICAL_PATH), args.protoc
        )
        breaking = compatibility_errors(baseline, canonical)
        compatibility.update(
            {
                "baseline_descriptor_sha256": descriptor_sha256(baseline),
                "status": "fail" if breaking else "pass",
                "errors": breaking,
            }
        )
        errors.extend(breaking)
    checks["backward_compatibility"] = compatibility

    return {
        "schema_version": SCHEMA_VERSION,
        "scope": "canonical-protobuf-contract",
        "decision": "block" if errors else "pass",
        "checks": checks,
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--base-ref")
    parser.add_argument("--protoc", default="protoc")
    parser.add_argument("--expected-protoc-version", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = validate(args)
    except (
        ValidationError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
    ) as error:
        result = {
            "schema_version": SCHEMA_VERSION,
            "scope": "canonical-protobuf-contract",
            "decision": "block",
            "checks": {},
            "errors": [str(error)],
        }

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
