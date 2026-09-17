"""Synthetic pure mixing checks; no Home Assistant, sockets or lamp evidence."""

import importlib.util
import itertools
import unittest
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "modules/aquarius_plant_led/custom_components/aquarius_plant_led/compact.py"
)
SPEC = importlib.util.spec_from_file_location("_hahapent_pure_compact_tests", SOURCE)
compact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compact)

KEYS = tuple("channel_" + letter for letter in "abcdef")
RGB_ONLY = ("red", "green", "blue", "unused", "unused", "unused")
RGB_WHITE = ("red", "green", "blue", "white", "unused", "unused")
DUPLICATES = ("red", "green", "blue", "white", "red", "white")


def options(roles=DUPLICATES):
    return {
        compact.CONF_CHANNEL_ROLES_VERSION: compact.COMPACT_ROLES_VERSION,
        compact.CONF_CHANNEL_ROLES: dict(zip(KEYS, roles)),
    }


class RoleConfigurationTests(unittest.TestCase):
    def test_runtime_role_sequence_validation_is_public_and_immutable(self):
        roles = list(RGB_ONLY)
        self.assertEqual(compact.validate_roles(roles), RGB_ONLY)
        self.assertIsInstance(compact.validate_roles(roles), tuple)
        with self.assertRaises(ValueError):
            compact.validate_roles(dict(zip(KEYS, roles)))

    def test_normalization_orders_exact_channels_and_is_immutable(self):
        mapping = dict(reversed(list(zip(KEYS, DUPLICATES))))
        self.assertEqual(compact.normalize_channel_roles(mapping), DUPLICATES)
        self.assertEqual(compact.normalize_channel_roles(MappingProxyType(mapping)), DUPLICATES)
        roles = compact.normalize_channel_roles(mapping)
        mapping["channel_a"] = "white"
        self.assertIsInstance(roles, tuple)
        self.assertEqual(roles, DUPLICATES)

    def test_all_primaries_required_but_duplicate_and_white_roles_optional(self):
        for roles in (
            RGB_ONLY,
            RGB_WHITE,
            DUPLICATES,
            ("red", "red", "green", "blue", "blue", "red"),
        ):
            with self.subTest(roles=roles):
                self.assertEqual(compact.normalize_channel_roles(dict(zip(KEYS, roles))), roles)
        for missing in ("red", "green", "blue"):
            roles = tuple("white" if role == missing else role for role in DUPLICATES)
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                compact.normalize_channel_roles(dict(zip(KEYS, roles)))

    def test_role_mapping_rejects_missing_extra_and_non_mapping_inputs(self):
        mapping = dict(zip(KEYS, RGB_ONLY))
        invalid = [None, [], RGB_ONLY, "red", {}, {**mapping, "channel_g": "unused"}]
        invalid.append({key: role for key, role in mapping.items() if key != "channel_f"})
        invalid.append({**mapping, "channel_A": mapping["channel_a"]})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                compact.normalize_channel_roles(value)

    def test_role_tokens_are_not_labels_or_coerced_values(self):
        for value in (None, False, 0, "Red", " red", "red ", "ruby red", "daylight white", [], {}):
            roles = dict(zip(KEYS, DUPLICATES))
            roles["channel_f"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                compact.normalize_channel_roles(roles)

    def test_options_require_explicit_supported_integer_version(self):
        configured = options()
        self.assertEqual(compact.compact_roles_from_options(configured), DUPLICATES)
        for version in (None, True, False, 0, 2, 1.0, "1", []):
            with self.subTest(version=version):
                self.assertIsNone(
                    compact.compact_roles_from_options(
                        {**configured, compact.CONF_CHANNEL_ROLES_VERSION: version}
                    )
                )
        configured.pop(compact.CONF_CHANNEL_ROLES_VERSION)
        self.assertIsNone(compact.compact_roles_from_options(configured))

    def test_absent_malformed_and_future_options_have_no_mapping(self):
        for value in (None, True, "options", [], {}, {compact.CONF_CHANNEL_ROLES_VERSION: 1}):
            with self.subTest(value=value):
                self.assertIsNone(compact.compact_roles_from_options(value))
        for mapping in (None, [], RGB_ONLY, {}, dict(zip(KEYS, ("unused",) * 6))):
            self.assertIsNone(
                compact.compact_roles_from_options(
                    {compact.CONF_CHANNEL_ROLES_VERSION: 1, compact.CONF_CHANNEL_ROLES: mapping}
                )
            )

    def test_display_labels_never_supply_or_override_semantic_roles(self):
        labels = dict(zip(KEYS, ("Red", "Green", "Blue", "White", "Red", "White")))
        display = {"channel_labels_version": 1, "channel_labels": labels}
        self.assertIsNone(compact.compact_roles_from_options(display))
        self.assertEqual(compact.compact_roles_from_options({**display, **options()}), DUPLICATES)
        display["channel_labels"] = {key: "Unrelated owner name" for key in KEYS}
        self.assertEqual(compact.compact_roles_from_options({**display, **options()}), DUPLICATES)

    def test_explicit_role_change_reorders_output_without_guessing(self):
        configured = options(RGB_ONLY)
        before = compact.compact_roles_from_options(configured)
        configured[compact.CONF_CHANNEL_ROLES]["channel_a"] = "blue"
        configured[compact.CONF_CHANNEL_ROLES]["channel_c"] = "red"
        after = compact.compact_roles_from_options(configured)
        self.assertEqual(compact.mix_rgb((255, 0, 0), 20, before), (20, 0, 0, 0, 0, 0))
        self.assertEqual(compact.mix_rgb((255, 0, 0), 20, after), (0, 0, 20, 0, 0, 0))


class StrictValueTests(unittest.TestCase):
    def test_rgb_is_three_strict_integers_and_returned_as_a_copy(self):
        rgb = [0, 127, 255]
        checked = compact.validate_rgb(rgb)
        rgb[0] = 200
        self.assertEqual(checked, (0, 127, 255))
        invalid = [None, "000", b"abc", {}, (), (0,) * 2, (0,) * 4]
        invalid.extend((value, 0, 0) for value in (-1, 256, True, False, 1.0, "1", None))
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                compact.validate_rgb(value)

    def test_intensity_accepts_every_integer_percentage_without_coercion(self):
        for value in range(101):
            self.assertEqual(compact.validate_intensity(value), value)
        for value in (-1, 101, True, False, 1.0, float("nan"), float("inf"), "1", None, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compact.validate_intensity(value)

    def test_every_channel_helper_rejects_invalid_shape_and_values(self):
        invalid = [None, "000000", bytes(6), {}, (), (0,) * 5, (0,) * 7]
        invalid.extend((value, 0, 0, 0, 0, 0) for value in (-1, 101, True, 1.0, "2", None))
        for value in invalid:
            for operation in (
                lambda: compact.peak_intensity(value),
                lambda: compact.scale_channels(value, 0),
                lambda: compact.rgb_from_channels(value, RGB_ONLY),
            ):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    operation()

    def test_mixing_validates_even_zero_output_and_invalid_role_sequences(self):
        for roles in (None, {}, ("red",) * 6, RGB_ONLY[:-1], (*RGB_ONLY, "unused")):
            for operation in (
                lambda: compact.mix_rgb((0, 0, 0), 0, roles),
                lambda: compact.rgb_from_channels((0,) * 6, roles),
            ):
                with self.subTest(roles=roles), self.assertRaises(ValueError):
                    operation()
        with self.assertRaises(ValueError):
            compact.mix_rgb((True, 0, 0), 0, RGB_ONLY)
        with self.assertRaises(ValueError):
            compact.mix_rgb((0, 0, 0), 1.0, RGB_ONLY)
        with self.assertRaises(ValueError):
            compact.scale_channels((0,) * 6, False)


class MixingTests(unittest.TestCase):
    def test_primary_secondary_and_neutral_golden_vectors(self):
        for rgb, expected in (
            ((255, 0, 0), (100, 0, 0, 0, 100, 0)),
            ((0, 255, 0), (0, 100, 0, 0, 0, 0)),
            ((0, 0, 255), (0, 0, 100, 0, 0, 0)),
            ((255, 255, 0), (100, 100, 0, 0, 100, 0)),
            ((255, 255, 255), (0, 0, 0, 100, 0, 100)),
        ):
            with self.subTest(rgb=rgb):
                self.assertEqual(compact.mix_rgb(rgb, 100, DUPLICATES), expected)

    def test_white_extraction_is_optional_and_normalizes_recipe_peak(self):
        self.assertEqual(compact.mix_rgb((255, 128, 128), 100, RGB_WHITE), (99, 0, 0, 100, 0, 0))
        self.assertEqual(compact.mix_rgb((255, 128, 128), 100, RGB_ONLY), (100, 50, 50, 0, 0, 0))
        self.assertEqual(compact.mix_rgb((255, 255, 255), 7, RGB_ONLY), (7, 7, 7, 0, 0, 0))

    def test_non_normalized_rgb_amplitude_applies_once(self):
        self.assertEqual(compact.mix_rgb((128, 0, 0), 50, DUPLICATES), (25, 0, 0, 0, 25, 0))
        self.assertEqual(compact.mix_rgb((128, 128, 128), 50, DUPLICATES), (0, 0, 0, 25, 0, 25))
        self.assertEqual(compact.mix_rgb((64, 32, 0), 100, RGB_ONLY), (25, 13, 0, 0, 0, 0))

    def test_quantization_is_half_up_not_bankers_rounding(self):
        # Extracting white leaves a residual 2:1:0 primary ratio.
        self.assertEqual(compact.mix_rgb((255, 191, 127), 1, RGB_WHITE), (1, 1, 0, 1, 0, 0))
        self.assertEqual(compact.scale_channels((100, 50, 25, 0, 0, 0), 1), (1, 1, 0, 0, 0, 0))
        self.assertEqual(compact.scale_channels((100, 50, 25, 0, 0, 0), 3), (3, 2, 1, 0, 0, 0))

    def test_positive_below_resolution_preserves_every_tied_peak(self):
        self.assertEqual(compact.mix_rgb((1, 0, 0), 1, DUPLICATES), (1, 0, 0, 0, 1, 0))
        self.assertEqual(compact.mix_rgb((1, 1, 1), 1, DUPLICATES), (0, 0, 0, 1, 0, 1))
        self.assertEqual(compact.mix_rgb((1, 1, 1), 1, RGB_ONLY), (1, 1, 1, 0, 0, 0))
        self.assertEqual(compact.mix_rgb((2, 1, 0), 1, RGB_ONLY), (1, 0, 0, 0, 0, 0))

    def test_black_or_zero_intensity_produces_only_zero(self):
        for roles in (RGB_ONLY, RGB_WHITE, DUPLICATES):
            for level in range(101):
                self.assertEqual(compact.mix_rgb((0, 0, 0), level, roles), (0,) * 6)
            for rgb in itertools.product((0, 1, 127, 255), repeat=3):
                self.assertEqual(compact.mix_rgb(rgb, 0, roles), (0,) * 6)

    def test_sampled_cube_has_valid_bounds_duplicate_symmetry_and_no_lost_positive_intent(self):
        for rgb in itertools.product((0, 1, 63, 127, 128, 254, 255), repeat=3):
            for level in (1, 2, 5, 49, 50, 99, 100):
                mixed = compact.mix_rgb(rgb, level, DUPLICATES)
                self.assertIsInstance(mixed, tuple)
                self.assertEqual(len(mixed), 6)
                self.assertTrue(all(type(value) is int and 0 <= value <= level for value in mixed))
                self.assertEqual(mixed[0], mixed[4])
                self.assertEqual(mixed[3], mixed[5])
                self.assertEqual(bool(max(mixed)), bool(max(rgb)))

    def test_channel_permutation_does_not_change_recipe_or_minimum_ties(self):
        permutation = (5, 2, 4, 0, 3, 1)
        swapped = tuple(DUPLICATES[index] for index in permutation)
        for rgb in ((1, 0, 0), (1, 1, 1), (31, 127, 255), (255, 191, 127)):
            for level in (1, 5, 100):
                original = compact.mix_rgb(rgb, level, DUPLICATES)
                self.assertEqual(
                    compact.mix_rgb(rgb, level, swapped),
                    tuple(original[index] for index in permutation),
                )

    def test_unused_channels_never_receive_a_colour_recipe(self):
        for rgb in itertools.product((0, 1, 128, 255), repeat=3):
            self.assertEqual(compact.mix_rgb(rgb, 100, RGB_ONLY)[3:], (0, 0, 0))


class ScalingTests(unittest.TestCase):
    def test_peak_uses_all_six_fresh_channels(self):
        self.assertEqual(compact.peak_intensity((0, 0, 0, 0, 0, 0)), 0)
        self.assertEqual(compact.peak_intensity([1, 5, 3, 7, 2, 100]), 100)
        self.assertEqual(
            compact.scale_channels((10, 20, 30, 40, 50, 100), 20), (2, 4, 6, 8, 10, 20)
        )

    def test_positive_zero_basis_never_invents_a_mix(self):
        self.assertEqual(compact.scale_channels((0,) * 6, 0), (0,) * 6)
        for level in range(1, 101):
            with (
                self.subTest(level=level),
                self.assertRaisesRegex(ValueError, "choose a colour first"),
            ):
                compact.scale_channels((0,) * 6, level)

    def test_zero_intensity_zeroes_a_nonzero_basis(self):
        self.assertEqual(compact.scale_channels((3, 17, 100, 7, 0, 19), 0), (0,) * 6)

    def test_scale_does_not_modify_input_or_drop_detailed_channel_mix(self):
        basis = [0, 5, 20, 35, 50, 100]
        before = list(basis)
        self.assertEqual(compact.scale_channels(basis, 100), tuple(basis))
        self.assertEqual(compact.scale_channels(basis, 20), (0, 1, 4, 7, 10, 20))
        self.assertEqual(basis, before)

    def test_every_intensity_has_exact_peak_and_half_percent_ratio_error_bound(self):
        for basis in ((1, 1, 0, 0, 0, 0), (3, 17, 29, 46, 73, 100), (2, 4, 6, 8, 10, 12)):
            for level in range(101):
                scaled = compact.scale_channels(basis, level)
                self.assertEqual(max(scaled), level)
                for original, actual in zip(basis, scaled):
                    exact = Fraction(original * level, max(basis))
                    self.assertLessEqual(abs(actual - exact), Fraction(1, 2))
                    if original == 0:
                        self.assertEqual(actual, 0)


class DisplayColourTests(unittest.TestCase):
    def test_zero_and_unused_only_have_no_inferred_colour(self):
        self.assertIsNone(compact.rgb_from_channels((0,) * 6, RGB_ONLY))
        self.assertIsNone(compact.rgb_from_channels((0, 0, 0, 5, 80, 100), RGB_ONLY))

    def test_primaries_whites_and_half_up_display(self):
        for channels, roles, expected in (
            ((40, 0, 0, 0, 0, 0), RGB_ONLY, (255, 0, 0)),
            ((0, 0, 0, 20, 0, 0), RGB_WHITE, (255, 255, 255)),
            ((80, 40, 0, 0, 0, 0), RGB_ONLY, (255, 128, 0)),
            ((50, 25, 0, 50, 0, 0), RGB_WHITE, (255, 191, 128)),
        ):
            with self.subTest(channels=channels):
                self.assertEqual(compact.rgb_from_channels(channels, roles), expected)

    def test_duplicates_use_max_not_sum_for_primary_and_white(self):
        self.assertEqual(
            compact.rgb_from_channels((20, 60, 0, 20, 40, 40), DUPLICATES),
            (204, 255, 102),
        )
        self.assertEqual(
            compact.rgb_from_channels((40, 60, 0, 40, 40, 40), DUPLICATES),
            (204, 255, 102),
        )

    def test_display_is_invariant_to_common_scale_before_quantization(self):
        basis = (10, 20, 30, 5, 10, 5)
        self.assertEqual(
            compact.rgb_from_channels(basis, DUPLICATES),
            compact.rgb_from_channels(tuple(value * 3 for value in basis), DUPLICATES),
        )

    def test_representable_recipe_roundtrip_and_role_permutation(self):
        for rgb in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 255, 255)):
            for roles in (RGB_ONLY, RGB_WHITE, DUPLICATES):
                mixed = compact.mix_rgb(rgb, 20, roles)
                self.assertEqual(compact.rgb_from_channels(mixed, roles), rgb)
                self.assertEqual(compact.rgb_from_channels(mixed[::-1], roles[::-1]), rgb)

    def test_sampled_display_is_normalized_and_bounded(self):
        for values in itertools.product((0, 1, 100), repeat=6):
            rgb = compact.rgb_from_channels(values, DUPLICATES)
            if any(values):
                self.assertEqual(max(rgb), 255)
                self.assertTrue(all(type(value) is int and 0 <= value <= 255 for value in rgb))
            else:
                self.assertIsNone(rgb)


if __name__ == "__main__":
    unittest.main()
