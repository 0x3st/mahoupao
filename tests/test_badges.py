import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import sync_and_report as report


class BadgeTests(unittest.TestCase):
    def test_badge_shows_index_level_colored_by_daily_change(self):
        cases = [
            ("positive_falling", [25.0, 24.87], "#2ea44f", "+24.87"),
            ("negative_rising", [-12.0, -10.0], "#e04f4f", "-10.00"),
            ("positive_rising", [24.0, 25.0], "#e04f4f", "+25.00"),
            ("negative_falling", [-10.0, -12.0], "#2ea44f", "-12.00"),
            ("unchanged", [25.0, 25.0], "#6b7280", "+25.00"),
            ("first_observation", [25.0], "#6b7280", "+25.00"),
            ("falls_to_zero", [1.0, 0.0], "#2ea44f", "+0.00"),
            ("rises_to_zero", [-1.0, 0.0], "#e04f4f", "+0.00"),
            ("latest_csi300", [17.7092, 18.1298], "#e04f4f", "+18.13"),
            ("latest_spx", [65.8470, 65.7024], "#2ea44f", "+65.70"),
            ("latest_gold", [146.4520, 149.7015], "#e04f4f", "+149.70"),
        ]
        ns = {"svg": "http://www.w3.org/2000/svg"}
        with tempfile.TemporaryDirectory() as tmp:
            paths = {key: Path(tmp) / f"{key}.svg" for key in report.market.ASSETS}
            with patch.object(report, "BADGE_SVG", paths):
                for name, values, expected_color, expected_text in cases:
                    with self.subTest(name=name):
                        curves = {
                            key: [{"return_pct": value} for value in values]
                            for key in paths
                        }
                        report.render_badges(curves)
                        for path in paths.values():
                            svg = ET.parse(path).getroot()
                            self.assertEqual(svg.findall("svg:path", ns)[1].get("fill"), expected_color)
                            self.assertEqual(svg.findall("svg:text", ns)[1].text, expected_text)


if __name__ == "__main__":
    unittest.main()
