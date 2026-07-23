from woodpecker_mcp.spec import TOOLS, prepare_spec


def operations(spec: dict) -> dict[tuple[str, str], dict]:
    return {
        (method.upper(), path): op
        for path, item in spec["paths"].items()
        for method, op in item.items()
    }


def test_prepared_spec_exposes_exactly_the_allowlisted_operations(raw_spec):
    prepared = prepare_spec(raw_spec)

    ops = operations(prepared)

    assert set(ops) == set(TOOLS)
    for key, tool in TOOLS.items():
        assert ops[key]["operationId"] == tool.name


def test_read_only_spec_drops_exactly_the_write_operations(raw_spec):
    prepared = prepare_spec(raw_spec, read_only=True)

    ops = operations(prepared)

    expected = {key for key, tool in TOOLS.items() if not tool.write}
    assert set(ops) == expected


def test_prepared_spec_has_no_response_schemas(raw_spec):
    prepared = prepare_spec(raw_spec)

    for op in operations(prepared).values():
        for response in op.get("responses", {}).values():
            assert "content" not in response


def test_prepared_spec_has_no_authorization_parameters(raw_spec):
    prepared = prepare_spec(raw_spec)

    for op in operations(prepared).values():
        for param in op.get("parameters", []):
            assert param["name"].lower() != "authorization"
