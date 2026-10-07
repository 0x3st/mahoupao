import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import sync_and_report as report


class BadgeTests(unittest.TestCase):
    def test_color_tracks_change_not_cumulative_return_sign(self):
        cases = [
            ("positive_falling", [25.0, 24.87], "#2ea44f"),
            ("negative_rising", [-12.0, -10.0], "#e04f4f"),
            ("positive_rising", [24.0, 25.0], "#e04f4f"),
            ("negative_falling", [-10.0, -12.0], "#2ea44f"),
            ("unchanged", [25.0, 25.0], "#6b7280"),
            ("first_observation", [25.0], "#6b7280"),
            ("falls_to_zero", [1.0, 0.0], "#2ea44f"),
            ("rises_to_zero", [-1.0, 0.0], "#e04f4f"),
        ]
        ns = {"svg": "http://www.w3.org/2000/svg"}
        with tempfile.TemporaryDirectory() as tmp:
            paths = {key: Path(tmp) / f"{key}.svg" for key in report.market.ASSETS}
            with patch.object(report, "BADGE_SVG", paths):
                for name, values, expected_color in cases:
                    with self.subTest(name=name):
                        curves = {
                            key: [{"return_pct": value} for value in values]
                            for key in paths
                        }
                        report.render_badges(curves)
                        for path in paths.values():
                            svg = ET.parse(path).getroot()
                            self.assertEqual(svg.findall("svg:path", ns)[1].get("fill"), expected_color)
                            self.assertEqual(svg.findall("svg:text", ns)[1].text, f"{values[-1]:+.2f}%")


if __name__ == "__main__":
    unittest.main()
