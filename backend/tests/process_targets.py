"""Spawn targets keep test-module collection outside the child startup budget."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from json import JSONDecodeError
from pathlib import Path


def _return_value(value: str) -> str:
    return value


def _wait_and_mark(started_path: str, finished_path: str, seconds: float) -> str:
    Path(started_path).touch()
    time.sleep(seconds)
    Path(finished_path).touch()
    return "finished"


def _ignore_terminate_and_wait(started_path: str) -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path(started_path).touch()
    while True:
        time.sleep(0.02)


def _spawn_grandchild_and_wait(started_path: str, finished_path: str) -> None:
    subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import pathlib,sys,time;time.sleep(.5);pathlib.Path(sys.argv[1]).touch()",
            finished_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    Path(started_path).touch()
    while True:
        time.sleep(0.02)


def _spawn_grandchild_and_return(finished_path: str) -> str:
    subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import pathlib, sys, time; time.sleep(0.5); pathlib.Path(sys.argv[1]).touch()",
            finished_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return "finished"


def _raise_with_private_message() -> None:
    raise RuntimeError("https://example.invalid/?token=private")


def _raise_validation_error() -> None:
    from pydantic import BaseModel, Field

    class _VersionInput(BaseModel):
        component_version: str = Field(pattern=r"^[a-z]+$")

    _VersionInput(component_version="secret/invalid")


def _raise_parse_error() -> None:
    raise JSONDecodeError("secret-token", "private payload", 0)


def _raise_value_error() -> None:
    raise ValueError("secret invalid value")


def _raise_owned_value_error() -> None:
    from content.discovery import _topic_id_from_configuration_ref

    _topic_id_from_configuration_ref("invalid")


def _raise_network_error() -> None:
    raise ConnectionError("https://example.invalid/?token=private")


def _exit_without_result() -> None:
    os._exit(19)


def _controlled_long_child(message: object, lease: object, lease_seconds: int) -> object:
    from worker.app import ChildJobCompletion, ChildJobResult

    time.sleep(6)
    return ChildJobResult(lease=lease, completion=ChildJobCompletion(status="succeeded"))
