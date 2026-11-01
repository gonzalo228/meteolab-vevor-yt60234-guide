#!/usr/bin/env python3
"""Offline allowlist-only Weathercloud decoder; standard library only."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
from urllib.parse import parse_qsl, unquote, urlsplit

DOCUMENTATION = "https://weathercloud.net/en/api"
# divisor, raw minimum, raw maximum, unit, sensor origin
FIELDS = {
    "temp": (10, -400, 600, "degC", "outdoor"),
    "tempin": (10, -400, 600, "degC", "indoor"),
    "hum": (1, 0, 100, "%", "outdoor"),
    "humin": (1, 0, 100, "%", "indoor"),
    "bar": (10, 9000, 11000, "hPa", "unverified"),
    "wspd": (10, 0, 600, "m/s", "outdoor"),
    "wspdavg": (10, 0, 600, "m/s", "outdoor"),
    "wspdhi": (10, 0, 600, "m/s", "outdoor"),
    "wdir": (1, 0, 359, "degree", "outdoor"),
    "wdiravg": (1, 0, 359, "degree", "outdoor"),
    "wdirhi": (1, 0, 359, "degree", "outdoor"),
    "rain": (10, 0, 10000, "mm", "outdoor"),
    "rainrate": (10, 0, 1000, "mm/h", "outdoor"),
    "solarrad": (10, 0, 20000, "W/m2", "outdoor"),
    "uvi": (10, 0, 160, "UV_index", "outdoor"),
}

class SafeError(Exception):
    """Only fixed credential-free messages may reach the caller."""

def parse_upload(uri):
    try:
        parts = urlsplit(uri)
        if parts.fragment:
            raise ValueError
        if parts.netloc and (parts.hostname or "").lower() != "api.weathercloud.net":
            raise ValueError
        segments = parts.path.rstrip("/").split("/")
        if segments[:3] != ["", "v01", "set"]:
            return None
        tail = segments[3:]
        if len(tail) % 2:
            raise ValueError
        pairs = [(unquote(tail[i]), unquote(tail[i + 1])) for i in range(0, len(tail), 2)]
        pairs += parse_qsl(parts.query, keep_blank_values=True, max_num_fields=256)
    except ValueError:
        raise SafeError("malformed_upload") from None
    selected = defaultdict(list)
    for name, value in pairs:
        if name in FIELDS:
            selected[name].append(value)
    if not selected:
        return None
    measurements, issues = {}, []
    for name, values in sorted(selected.items()):
        if len(values) > 1:
            if len(set(values)) != 1:
                issues.append({"field": name, "code": "conflicting_duplicates"})
                continue
            issues.append({"field": name, "code": "identical_duplicates"})
        value = values[0]
        if not re.fullmatch(r"-?[0-9]{1,8}", value):
            issues.append({"field": name, "code": "invalid_integer"})
            continue
        raw = int(value)
        divisor, lower, upper, unit, origin = FIELDS[name]
        if not lower <= raw <= upper:
            issues.append({"field": name, "code": "outside_documented_range"})
            continue
        measurements[name] = {
            "value": raw / divisor if divisor != 1 else raw,
            "raw": raw, "unit": unit, "sensor_origin": origin,
        }
    return {"measurements": measurements, "issues": issues}

def decode_rows(lines):
    records, rejected = [], Counter()
    for line in lines:
        columns = line.rstrip("\r\n").split("\t")
        if len(columns) != 5:
            rejected["invalid_row"] += 1
            continue
        frame, epoch_text, method, host, uri = columns
        if host.lower() not in {"api.weathercloud.net", "api.weathercloud.net:80"}:
            rejected["unexpected_host"] += 1
            continue
        if method != "GET":
            rejected["unsupported_method"] += 1
            continue
        try:
            if not re.fullmatch(r"[0-9]{1,12}", frame) or int(frame) < 1:
                raise ValueError
            if not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,9})?", epoch_text):
                raise ValueError
            timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
                microseconds=int(Decimal(epoch_text) * 1000000))
            decoded = parse_upload(uri)
        except SafeError:
            rejected["malformed_upload"] += 1
            continue
        except (ValueError, OverflowError):
            rejected["invalid_timestamp_or_frame"] += 1
            continue
        if decoded is None:
            rejected["not_weather_upload"] += 1
            continue
        records.append({
            "timestamp_epoch": epoch_text,
            "timestamp_utc": timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "timestamp_basis": "packet_capture_time_not_sensor_measurement_time",
            "provenance": {"source": "capture_1", "frame": int(frame), "transport": "captured_http_request"},
            **decoded,
        })
    records.sort(key=lambda r: (r["timestamp_utc"], r["provenance"]["frame"]))
    return records, dict(rejected)

def summarize(records):
    timestamps = [datetime.fromisoformat(r["timestamp_utc"].replace("Z", "+00:00")) for r in records]
    intervals = [(b - a).total_seconds() for a, b in zip(timestamps, timestamps[1:])]
    return {
        "decoded_requests": len(records),
        "measurement_counts": dict(Counter(k for r in records for k in r["measurements"])),
        "issue_counts": dict(Counter(i["code"] for r in records for i in r["issues"])),
        "first_timestamp_utc": records[0]["timestamp_utc"] if records else None,
        "last_timestamp_utc": records[-1]["timestamp_utc"] if records else None,
        "request_intervals_seconds": intervals,
        "interval_min_seconds": min(intervals) if intervals else None,
        "interval_median_seconds": statistics.median(intervals) if intervals else None,
        "interval_max_seconds": max(intervals) if intervals else None,
    }

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def decode_capture(path):
    before = sha256_file(path)
    command = [
        "tshark", "-n", "-r", str(path), "-Y", "http.request", "-T", "fields", "-E", "occurrence=f",
        "-e", "frame.number", "-e", "frame.time_epoch", "-e", "http.request.method",
        "-e", "http.host", "-e", "http.request.uri",
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise SafeError("TShark failed; raw diagnostic output suppressed.")
    if sha256_file(path) != before:
        raise SafeError("Capture changed during analysis; use a completed capture.")
    records, rejected = decode_rows(result.stdout.splitlines())
    return {
        "schema_version": 1, "decoder_version": "1.0.0", "documentation": DOCUMENTATION,
        "validation_status": "not_yet_compared_with_console_and_weathercloud",
        "sources": [{"id": "capture_1", "sha256": before}],
        "semantics": {
            "rain": "daily_total; day_boundary_defined_by_station_not_verified",
            "bar": "sensor_origin_and_sea_level_correction_unverified",
            "wspd": "reported_speed; averaging_window_unverified",
            "duplicates": "all_requests_retained; no_retry_assumption",
            "server_acceptance": "not_evaluated", "missing_fields": "omitted; never_assumed_zero",
        },
        "summary": summarize(records), "skipped_requests": rejected, "records": records,
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New JSON; never overwrite existing files.")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise SafeError("Output exists; choose a new output file.")
        document = decode_capture(args.capture)
        payload = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
        print(json.dumps(document["summary"], ensure_ascii=False, indent=2))
    except SafeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("Cannot read capture, run TShark, or create JSON; raw details suppressed.", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
