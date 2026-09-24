import os
import tempfile
import unittest
from unittest import mock

from labgate_action_util import (
    DEFAULT_ENCODING,
    FileStabilityTracker,
    build_gdt_line,
    build_gdt_request_text,
    clean_lab_number,
    extract_return_record,
    extract_return_lab_number,
    first_free_lab_slot,
    format_dob_for_gdt,
    format_gender_for_gdt,
    extract_return_lab_numbers,
    extract_return_records,
    matches_filename_filter,
    parse_gdt_text,
    write_gdt_request_file,
)


class LabGateActionUtilTests(unittest.TestCase):
    def test_build_gdt_line_prefix_matches_encoded_length(self):
        line = build_gdt_line("3101", "Müller")
        self.assertEqual(int(line[:3]), len(line.encode(DEFAULT_ENCODING)))
        self.assertTrue(line.endswith("\r\n"))

    def test_build_gdt_request_text_sets_8100_total_length(self):
        text = build_gdt_request_text(
            {
                "id": 15,
                "firstname": "Max",
                "secondname": "Müller",
                "dob": "22.04.1980",
                "gender": "M",
            }
        )
        parsed = parse_gdt_text(text)
        self.assertEqual(parsed["8000"][-1], "6302")
        self.assertEqual(parsed["9218"][-1], "02.10")
        self.assertEqual(parsed["3000"][-1], "15")
        self.assertEqual(parsed["3103"][-1], "22041980")
        self.assertEqual(parsed["3110"][-1], "1")
        self.assertEqual(parsed["8100"][-1], f"{len(text.encode(DEFAULT_ENCODING)):05d}")

    def test_format_dob_for_gdt_uses_day_month_year(self):
        self.assertEqual(format_dob_for_gdt("20.11.1992"), "20111992")
        self.assertEqual(format_dob_for_gdt("1992-11-20"), "20111992")
        self.assertEqual(format_dob_for_gdt("19921120"), "20111992")
        self.assertEqual(format_dob_for_gdt("20111992"), "20111992")

    def test_format_gender_for_gdt_matches_labgate_mapping(self):
        self.assertEqual(format_gender_for_gdt("M"), "1")
        self.assertEqual(format_gender_for_gdt("W"), "2")
        self.assertEqual(format_gender_for_gdt("F"), "2")
        self.assertEqual(format_gender_for_gdt("1"), "1")
        self.assertEqual(format_gender_for_gdt("2"), "2")

    def test_extract_return_records_reads_repeated_order_numbers(self):
        text = "".join(
            [
                build_gdt_line("3000", "7194"),
                build_gdt_line("3101", "Althaus"),
                build_gdt_line("3102", "Michael"),
                build_gdt_line("3103", "03121980"),
                build_gdt_line("6228", "Auftragsnummer: 41591365"),
                build_gdt_line("3000", "7194"),
                build_gdt_line("3101", "Althaus"),
                build_gdt_line("3102", "Michael"),
                build_gdt_line("3103", "03121980"),
                build_gdt_line("6228", "Auftragsnummer: 41591366"),
            ]
        )

        records = extract_return_records(parse_gdt_text(text), max_records=3)

        self.assertEqual([record["lab_number_raw"] for record in records], ["41591365", "41591366"])
        self.assertEqual([record["patient_id"] for record in records], ["7194", "7194"])
        self.assertEqual(records[0]["dob"], "03.12.1980")

    def test_extract_return_lab_numbers_does_not_cap_by_default(self):
        text = "".join(
            [
                build_gdt_line("6333", "41591365"),
                build_gdt_line("6333", "41591366"),
                build_gdt_line("6333", "41591367"),
                build_gdt_line("6333", "41591368"),
            ]
        )

        parsed = parse_gdt_text(text)

        self.assertEqual(
            extract_return_lab_numbers(parsed),
            ["41591365", "41591366", "41591367", "41591368"],
        )
        self.assertEqual(
            extract_return_lab_numbers(parsed, max_records=3),
            ["41591365", "41591366", "41591367"],
        )

    def test_write_gdt_request_file_creates_crlf_encoded_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_gdt_request_file(
                {
                    "id": 3,
                    "firstname": "Erika",
                    "secondname": "Mustermann",
                    "dob": "1980-04-22",
                    "gender": "W",
                },
                tmp,
                "pat.gdt",
            )
            self.assertTrue(os.path.exists(path))
            with open(path, "rb") as handle:
                payload = handle.read()
            self.assertIn(b"\r\n", payload)
            self.assertIn("3102Erika".encode(DEFAULT_ENCODING), payload)
            self.assertIn("310322041980".encode(DEFAULT_ENCODING), payload)

    def test_write_gdt_request_file_moves_from_root_tmp_with_windows_cmd(self):
        with tempfile.TemporaryDirectory() as root_tmp, tempfile.TemporaryDirectory() as export_tmp:
            with mock.patch("app_paths.get_preferred_external_path", return_value=root_tmp):
                with mock.patch("subprocess.run") as run_mock:
                    run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")

                    path = write_gdt_request_file(
                        {
                            "id": 3,
                            "firstname": "Erika",
                            "secondname": "Mustermann",
                            "dob": "1980-04-22",
                            "gender": "W",
                        },
                        export_tmp,
                        "pat.gdt",
                    )

            move_args = run_mock.call_args.args[0]
            self.assertEqual(move_args[:4], ["cmd.exe", "/c", "move", "/Y"])
            self.assertTrue(move_args[4].startswith(root_tmp))
            self.assertEqual(move_args[5], path)

    def test_clean_lab_number_strips_first_four_digits(self):
        self.assertEqual(clean_lab_number("123456789"), "56789")
        self.assertEqual(clean_lab_number("1234-56789"), "56789")

    def test_clean_lab_number_rejects_short_values(self):
        with self.assertRaises(ValueError):
            clean_lab_number("1234")

    def test_matches_filename_filter_supports_multiple_patterns(self):
        self.assertTrue(matches_filename_filter("IN123.gdt", "IN*.gdt;OUT*.gdt"))
        self.assertTrue(matches_filename_filter("OUT999.gdt", "IN*.gdt, OUT*.gdt"))
        self.assertFalse(matches_filename_filter("foo.txt", "IN*.gdt;OUT*.gdt"))

    def test_first_free_lab_slot_returns_first_empty_slot(self):
        self.assertEqual(first_free_lab_slot({"lab_code_1": "", "lab_code_2": "A", "lab_code_3": "B"}), 1)
        self.assertEqual(first_free_lab_slot({"lab_code_1": "A", "lab_code_2": "", "lab_code_3": "B"}), 2)
        self.assertEqual(first_free_lab_slot({"lab_code_1": "A", "lab_code_2": "B", "lab_code_3": ""}), 3)
        self.assertIsNone(first_free_lab_slot({"lab_code_1": "A", "lab_code_2": "B", "lab_code_3": "C"}))

    def test_extract_return_record_normalizes_dob(self):
        record = extract_return_record(
            {
                "3000": ["15"],
                "3101": ["Mustermann"],
                "3102": ["Max"],
                "3103": ["19800422"],
                "6333": ["123456789"],
            }
        )
        self.assertEqual(record["patient_id"], "15")
        self.assertEqual(record["dob"], "22.04.1980")
        self.assertEqual(record["lab_number_raw"], "123456789")

    def test_extract_return_lab_number_falls_back_to_order_text(self):
        parsed = {"6228": ["Auftragsnummer: 41591315"]}

        self.assertEqual(extract_return_lab_number(parsed), "41591315")
        self.assertEqual(clean_lab_number(extract_return_lab_number(parsed)), "1315")

    def test_file_stability_tracker_requires_two_seconds_of_stability(self):
        tracker = FileStabilityTracker(threshold_seconds=2.0)
        self.assertFalse(tracker.update("a.gdt", 100, 50, now=0.0))
        self.assertFalse(tracker.update("a.gdt", 100, 50, now=1.9))
        self.assertTrue(tracker.update("a.gdt", 100, 50, now=2.0))
        self.assertFalse(tracker.update("a.gdt", 101, 51, now=2.1))


if __name__ == "__main__":
    unittest.main()
