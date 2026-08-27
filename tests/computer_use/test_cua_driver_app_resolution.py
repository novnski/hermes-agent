"""Local macOS CuaDriver bundle resolution guards."""

from tools.computer_use import cua_backend


def _bundle(tmp_path):
    app = tmp_path / "CuaDriver.app"
    binary = app / "Contents" / "MacOS" / "cua-driver"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    return app, binary


def test_resolves_bundle_through_path_symlink(tmp_path):
    app, binary = _bundle(tmp_path)
    link = tmp_path / "bin" / "cua-driver"
    link.parent.mkdir()
    link.symlink_to(binary)
    assert cua_backend._resolve_cua_driver_app_path(str(link)) == str(app)


def test_resolves_bundle_through_symlink_chain(tmp_path):
    app, binary = _bundle(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.symlink_to(binary)
    second.symlink_to(first)
    assert cua_backend._resolve_cua_driver_app_path(str(second)) == str(app)


def test_loose_binary_and_broken_link_fail_closed(tmp_path):
    loose = tmp_path / "loose-driver"
    loose.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    loose.chmod(0o755)
    broken = tmp_path / "broken"
    broken.symlink_to(tmp_path / "missing")
    assert cua_backend._resolve_cua_driver_app_path(str(loose)) is None
    assert cua_backend._resolve_cua_driver_app_path(str(broken)) is None
