"""Synthetic SAST canary. This file must be detected, never executed."""


def dynamic_execution_canary(untrusted_input):
    return eval(untrusted_input)
