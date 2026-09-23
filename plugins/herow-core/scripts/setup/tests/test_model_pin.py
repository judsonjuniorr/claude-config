"""Tests for model-pin.py's version gate and its model tables."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import unittest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "model-pin.py"
_spec = importlib.util.spec_from_file_location("model_pin", _PATH)
mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mp)


class VersionGateTest(unittest.TestCase):
    def _gate(
        self, installed: tuple[int, int, int] | None, model_id: str
    ) -> str | None:
        original = mp._installed_cc_version
        mp._installed_cc_version = lambda: installed
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                return mp._version_gate(model_id)
        finally:
            mp._installed_cc_version = original

    def test_pins_model_at_its_minimum_version(self) -> None:
        self.assertEqual(self._gate((2, 1, 280), "claude-opus-5-5"), "claude-opus-5-5")

    def test_steps_down_one_generation_below_minimum(self) -> None:
        self.assertEqual(self._gate((2, 1, 279), "claude-opus-5-5"), "claude-opus-5")

    def test_chain_skips_every_model_the_install_cannot_select(self) -> None:
        self.assertEqual(self._gate((2, 1, 200), "claude-opus-5-5"), "claude-opus-4-8")
        self.assertEqual(self._gate((2, 1, 100), "claude-opus-5-5"), "claude-opus-4-7")

    def test_unknown_version_fails_open(self) -> None:
        self.assertEqual(self._gate(None, "claude-opus-5-5"), "claude-opus-5-5")

    def test_ungated_model_passes_through(self) -> None:
        self.assertEqual(self._gate((2, 1, 1), "claude-opus-4-7"), "claude-opus-4-7")

    def test_variant_and_dated_ids_are_gated(self) -> None:
        self.assertEqual(
            self._gate((2, 1, 250), "claude-opus-5-5[1m]"), "claude-opus-5"
        )
        self.assertEqual(
            self._gate((2, 1, 250), "claude-opus-5-5-20260901"), "claude-opus-5"
        )

    def test_sonnet_falls_back_to_previous_generation(self) -> None:
        self.assertEqual(
            self._gate((2, 1, 150), "claude-sonnet-5"), "claude-sonnet-4-6"
        )


class TableInvariantTest(unittest.TestCase):
    def test_every_chain_ends_on_an_ungated_model_without_looping(self) -> None:
        for start in mp.MODEL_VERSION_FALLBACK:
            seen: set[str] = set()
            current = start
            while current in mp.MODEL_VERSION_FALLBACK:
                self.assertNotIn(current, seen, f"fallback loop through {current}")
                seen.add(current)
                current = mp.MODEL_VERSION_FALLBACK[current]
            self.assertNotIn(
                current, mp.MODEL_MIN_VERSION, f"{start} chain ends on gated {current}"
            )

    def test_every_gated_model_has_a_fallback(self) -> None:
        for model_id in mp.MODEL_MIN_VERSION:
            self.assertIn(model_id, mp.MODEL_VERSION_FALLBACK)

    def test_fallback_stays_in_family(self) -> None:
        for src, dst in mp.MODEL_VERSION_FALLBACK.items():
            self.assertEqual(src.split("-")[1], dst.split("-")[1])

    def test_static_fallback_lists_three_per_family_with_matching_labels(self) -> None:
        for family in ("opus", "sonnet"):
            self.assertEqual(
                sum(1 for fam, _, _ in mp.STATIC_FALLBACK if fam == family), 3
            )
        for _, model_id, label in mp.STATIC_FALLBACK:
            self.assertEqual(mp._label(model_id), label)


if __name__ == "__main__":
    unittest.main()
