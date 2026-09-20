import importlib.util
import pathlib
import unittest

from google.protobuf import descriptor_pb2


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "validate-protobuf-contracts.py"

SPEC = importlib.util.spec_from_file_location("validate_protobuf_contracts", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def contract() -> descriptor_pb2.FileDescriptorProto:
    descriptor = descriptor_pb2.FileDescriptorProto(
        name="demo.proto",
        package="example",
        syntax="proto3",
    )
    request = descriptor.message_type.add(name="Request")
    request.field.add(
        name="user_id",
        json_name="userId",
        number=1,
        label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    response = descriptor.message_type.add(name="Response")
    response.field.add(
        name="accepted",
        json_name="accepted",
        number=1,
        label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_BOOL,
    )
    service = descriptor.service.add(name="Checkout")
    service.method.add(
        name="PlaceOrder",
        input_type=".example.Request",
        output_type=".example.Response",
    )
    return descriptor


class ProtobufContractTests(unittest.TestCase):
    def test_default_json_names_do_not_create_false_drift(self):
        current = contract()
        older_generator = descriptor_pb2.FileDescriptorProto()
        older_generator.CopyFrom(current)
        for message in older_generator.message_type:
            for field in message.field:
                field.ClearField("json_name")

        self.assertEqual(
            MODULE.descriptor_sha256(current),
            MODULE.descriptor_sha256(older_generator),
        )

    def test_additive_message_field_is_compatible(self):
        baseline = contract()
        candidate = contract()
        candidate.message_type[0].field.add(
            name="region",
            number=2,
            label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
            type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
        )

        self.assertEqual(MODULE.compatibility_errors(baseline, candidate), [])

    def test_removed_field_is_blocked(self):
        baseline = contract()
        candidate = contract()
        candidate.message_type[0].ClearField("field")

        errors = MODULE.compatibility_errors(baseline, candidate)

        self.assertTrue(any("field removed" in error for error in errors))

    def test_field_type_change_is_blocked(self):
        baseline = contract()
        candidate = contract()
        candidate.message_type[0].field[0].type = (
            descriptor_pb2.FieldDescriptorProto.TYPE_INT64
        )

        errors = MODULE.compatibility_errors(baseline, candidate)

        self.assertTrue(any("field changed incompatibly" in error for error in errors))

    def test_additive_rpc_is_compatible(self):
        baseline = contract()
        candidate = contract()
        candidate.service[0].method.add(
            name="PreviewOrder",
            input_type=".example.Request",
            output_type=".example.Response",
        )

        self.assertEqual(MODULE.compatibility_errors(baseline, candidate), [])

    def test_removed_rpc_is_blocked(self):
        baseline = contract()
        candidate = contract()
        candidate.service[0].ClearField("method")

        errors = MODULE.compatibility_errors(baseline, candidate)

        self.assertTrue(any("RPC removed" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
