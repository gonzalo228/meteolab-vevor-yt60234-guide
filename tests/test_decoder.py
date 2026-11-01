import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "decoder" / "decode_weathercloud.py"
spec = importlib.util.spec_from_file_location("decoder", SCRIPT)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

class DecoderTests(unittest.TestCase):
    def test_all_conversions(self):
        result = d.parse_upload("/v01/set/temp/-35/tempin/205/hum/90/humin/40/bar/10135/wspd/125/wspdavg/20/wspdhi/160/wdir/359/wdiravg/180/wdirhi/90/rain/350/rainrate/200/solarrad/10500/uvi/80")
        expected = [-3.5, 20.5, 90, 40, 1013.5, 12.5, 2, 16, 359, 180, 90, 35, 20, 1050, 8]
        names = "temp tempin hum humin bar wspd wspdavg wspdhi wdir wdiravg wdirhi rain rainrate solarrad uvi".split()
        self.assertEqual({k: v["value"] for k, v in result["measurements"].items()}, dict(zip(names, expected)))
        self.assertEqual(result["issues"], [])

    def test_synthetic_sample(self):
        result = d.parse_upload("/v01/set/bar/10180/temp/123/hum/65/wdir/220/wspd/15/rainrate/2/rain/10/uvi/10/solarrad/250")
        self.assertEqual(result["measurements"]["solarrad"]["value"], 25.0)
        self.assertEqual(result["measurements"]["temp"]["value"], 12.3)
        self.assertEqual(result["measurements"]["bar"]["sensor_origin"], "unverified")

    def test_query_credentials_removed(self):
        result = d.parse_upload("/v01/set?wid=PRIVATE_ID&key=PRIVATE_SECRET&softwareid=PRIVATE_SOFTWARE&temp=71&hum=86&unknown=PRIVATE_OTHER")
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("wid", json.dumps(result))
        self.assertEqual(set(result["measurements"]), {"temp", "hum"})

    def test_zero_and_missing(self):
        result = d.parse_upload("/v01/set/wspd/0/rain/0/uvi/0")
        self.assertEqual(result["measurements"]["wspd"]["value"], 0)
        self.assertNotIn("wspdhi", result["measurements"])
        self.assertNotIn("bar", result["measurements"])

    def test_duplicate_identical(self):
        result = d.parse_upload("/v01/set/temp/71?temp=71")
        self.assertEqual(result["measurements"]["temp"]["value"], 7.1)
        self.assertEqual(result["issues"][0]["code"], "identical_duplicates")

    def test_duplicate_conflict(self):
        result = d.parse_upload("/v01/set?temp=71&temp=72&hum=86")
        self.assertNotIn("temp", result["measurements"])
        self.assertEqual(result["issues"][0]["code"], "conflicting_duplicates")

    def test_invalid_numbers_do_not_leak(self):
        for value in ["", "nan", "inf", "1e2", "7.1", "PRIVATE_SECRET", "9" * 100]:
            result = d.parse_upload("/v01/set?temp=" + value)
            self.assertEqual(result["measurements"], {})
            self.assertEqual(result["issues"][0]["code"], "invalid_integer")
            self.assertNotIn("PRIVATE", json.dumps(result))

    def test_documented_ranges(self):
        for field, (_, lower, upper, _, _) in d.FIELDS.items():
            for raw in (lower, upper):
                self.assertIn(field, d.parse_upload(f"/v01/set/{field}/{raw}")["measurements"])
            for raw in (lower - 1, upper + 1):
                self.assertNotIn(field, d.parse_upload(f"/v01/set/{field}/{raw}")["measurements"])

    def test_malformed_and_unrelated(self):
        self.assertIsNone(d.parse_upload("/unrelated/temp/71"))
        self.assertIsNone(d.parse_upload("/v01/set/wid/PRIVATE_ID/key/PRIVATE_SECRET"))
        for uri in ["/v01/set/temp", "/v01/set/temp/71/key", "http://[invalid", "/v01/set/temp/71#PRIVATE_SECRET"]:
            with self.assertRaises(d.SafeError) as context:
                d.parse_upload(uri)
            self.assertEqual(str(context.exception), "malformed_upload")

    def test_encoded_values_and_absolute_uri(self):
        result = d.parse_upload("http://api.weathercloud.net/v01/set/temp/%37%31/")
        self.assertEqual(result["measurements"]["temp"]["value"], 7.1)

    def test_timestamp_and_repeated_requests(self):
        rows = [
            "18\t1704067205.314275\tGET\tapi.weathercloud.net\t/v01/set/temp/71",
            "7\t1704067200.000000\tGET\tapi.weathercloud.net\t/v01/set/temp/71",
        ]
        records, rejected = d.decode_rows(rows)
        self.assertEqual(rejected, {})
        self.assertEqual(records[0]["timestamp_utc"], "2024-01-01T00:00:00.000000Z")
        self.assertEqual(records[0]["timestamp_epoch"], "1704067200.000000")
        self.assertEqual(len(records), 2)
        self.assertAlmostEqual(d.summarize(records)["interval_min_seconds"], 5.314275)

    def test_untrusted_rows(self):
        rows = [
            "1\tnan\tGET\tapi.weathercloud.net\t/v01/set/temp/71",
            "2\t1\tGET\tevil.invalid\t/v01/set/temp/71",
            "3\t1\tPOST\tapi.weathercloud.net\t/v01/set/temp/71",
            "PRIVATE_ROW",
        ]
        records, rejected = d.decode_rows(rows)
        self.assertEqual(records, [])
        self.assertEqual(sum(rejected.values()), 4)
        self.assertNotIn("PRIVATE", json.dumps(rejected))

    def test_tshark_error_suppressed(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "test.pcapng"
            capture.write_bytes(b"untouched")
            with patch.object(d.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "PRIVATE", "PRIVATE")):
                with self.assertRaises(d.SafeError) as context:
                    d.decode_capture(capture)
            self.assertNotIn("PRIVATE", str(context.exception))
            self.assertEqual(capture.read_bytes(), b"untouched")

    def test_mock_pipeline_no_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "test.pcapng"
            capture.write_bytes(b"untouched")
            row = "7\t1704067200.000000\tGET\tapi.weathercloud.net\t/v01/set/wid/PRIVATE_ID/key/PRIVATE_SECRET/temp/71"
            with patch.object(d.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, row, "")):
                result = d.decode_capture(capture)
            self.assertEqual(result["summary"]["decoded_requests"], 1)
            self.assertNotIn("PRIVATE", json.dumps(result))
            self.assertEqual(capture.read_bytes(), b"untouched")

    def test_modified_capture_rejected(self):
        with patch.object(d, "sha256_file", side_effect=["before", "after"]):
            with patch.object(d.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
                with self.assertRaises(d.SafeError):
                    d.decode_capture(Path("unused"))

    def test_existing_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing.json"
            output.write_text("keep", encoding="utf-8")
            with patch.object(d.sys, "argv", ["decoder", "unused.pcapng", "--output", str(output)]):
                with patch("sys.stderr"):
                    self.assertEqual(d.main(), 1)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep")

    @unittest.skipIf(__import__("os").name == "nt", "POSIX permission bits are not Windows ACLs")
    def test_output_permissions_private(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "private.json"
            with patch.object(d, "decode_capture", return_value={"summary": {"decoded_requests": 1}}):
                with patch.object(d.sys, "argv", ["decoder", "unused.pcapng", "--output", str(output)]):
                    with patch("sys.stdout"):
                        self.assertEqual(d.main(), 0)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

if __name__ == "__main__":
    unittest.main()
