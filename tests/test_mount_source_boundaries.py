"""Boundary tests for mount source category matching.

The categorizer should match exact path segments, not arbitrary string
prefixes.  For example, /etc and /etc/ssl are system paths, but /etcetera is
just another absolute path.
"""
from __future__ import annotations

import os
import sys
import unittest

_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from docker_topology_live.scanner import _categorize_mount_source


class TestMountSourceCategoryBoundaries(unittest.TestCase):
    """Sensitive categories must use path-segment boundaries."""

    def test_etc_exact_and_children_are_system(self):
        self.assertEqual(_categorize_mount_source("/etc"), "system")
        self.assertEqual(_categorize_mount_source("/etc/ssl"), "system")
        self.assertEqual(_categorize_mount_source("/etc/ssl/certs"), "system")

    def test_etcetera_is_absolute_path(self):
        self.assertEqual(_categorize_mount_source("/etcetera"), "absolute-path")
        self.assertEqual(_categorize_mount_source("/etcetera/config"), "absolute-path")

    def test_home_exact_and_children_are_home(self):
        self.assertEqual(_categorize_mount_source("/home"), "home")
        self.assertEqual(_categorize_mount_source("/home/alice"), "home")
        self.assertEqual(_categorize_mount_source("/home/alice/project"), "home")

    def test_homebrew_is_absolute_path(self):
        self.assertEqual(_categorize_mount_source("/homebrew"), "absolute-path")
        self.assertEqual(_categorize_mount_source("/homebrew/bin"), "absolute-path")

    def test_users_exact_and_children_are_home(self):
        self.assertEqual(_categorize_mount_source("/Users"), "home")
        self.assertEqual(_categorize_mount_source("/Users/bob"), "home")
        self.assertEqual(_categorize_mount_source("/Users/bob/project"), "home")

    def test_usershare_is_absolute_path(self):
        self.assertEqual(_categorize_mount_source("/Usershare"), "absolute-path")
        self.assertEqual(_categorize_mount_source("/Usershare/data"), "absolute-path")

    def test_proc_sys_root_boundaries(self):
        self.assertEqual(_categorize_mount_source("/proc"), "system")
        self.assertEqual(_categorize_mount_source("/proc/net"), "system")
        self.assertEqual(_categorize_mount_source("/procfs"), "absolute-path")
        self.assertEqual(_categorize_mount_source("/sys"), "system")
        self.assertEqual(_categorize_mount_source("/sys/kernel"), "system")
        self.assertEqual(_categorize_mount_source("/sysadmin"), "absolute-path")
        self.assertEqual(_categorize_mount_source("/root"), "system")
        self.assertEqual(_categorize_mount_source("/root/.ssh"), "system")
        self.assertEqual(_categorize_mount_source("/rootless"), "absolute-path")

    def test_var_run_boundaries(self):
        self.assertEqual(_categorize_mount_source("/var/run"), "system")
        self.assertEqual(_categorize_mount_source("/var/run/containerd"), "system")
        self.assertEqual(_categorize_mount_source("/var/runtime"), "absolute-path")

    def test_docker_socket_special_case_remains(self):
        self.assertEqual(_categorize_mount_source("/var/run/docker.sock"), "docker-socket")


if __name__ == "__main__":
    unittest.main()
