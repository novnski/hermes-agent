"""Regression guard for the macOS post-update TCC notice."""

import ast
import inspect

from hermes_cli import update_cmd


def test_tcc_notice_gate_uses_a_local_name():
    source = inspect.getsource(update_cmd._cmd_update_impl)
    tree = ast.parse(source)
    function = tree.body[0]
    assigned_names = {
        node.id
        for node in ast.walk(function)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    assigned_args = {node.arg for node in ast.walk(function) if isinstance(node, ast.arg)}
    tcc_gate_names = {
        node.id
        for node in ast.walk(function)
        if isinstance(node, ast.If)
        and "tccutil reset ScreenCapture" in ast.unparse(node)
        for node in ast.walk(node.test)
        if isinstance(node, ast.Name) and node.id != "sys"
    }

    assert tcc_gate_names <= assigned_names | assigned_args
