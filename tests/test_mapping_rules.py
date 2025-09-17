import unittest

from pipeline.mapping_rules import (
    categorize_from_comment,
    categorize_from_ocr,
    categorize_from_filename,
    categorize_record,
    allow_unclear_label,
)


class TestMappingRules(unittest.TestCase):
    def test_comment_feature_requests(self):
        self.assertEqual(categorize_from_comment("Feature request: please add dark mode"), 'feature_requests')

    def test_comment_connectivity(self):
        self.assertEqual(categorize_from_comment("Unable to connect. Network error and API failed"), 'connectivity_problems')

    def test_comment_authentication(self):
        self.assertEqual(categorize_from_comment("Login fails after OTP. Access denied"), 'authentication_access')

    def test_comment_performance(self):
        self.assertEqual(categorize_from_comment("App is very slow and keeps loading forever"), 'performance_issues')

    def test_comment_crash(self):
        self.assertEqual(categorize_from_comment("The app crashes and force closes"), 'crash_stability')

    def test_comment_data_integrity(self):
        self.assertEqual(categorize_from_comment("Wrong total amount and duplicate entries"), 'data_integrity_issues')

    def test_comment_ui_ux(self):
        self.assertEqual(categorize_from_comment("Text is cut off and alignment is broken"), 'ui_ux_issues')

    def test_comment_functional(self):
        self.assertEqual(categorize_from_comment("Add sale does not work, button does nothing"), 'functional_errors')

    def test_comment_configuration(self):
        self.assertEqual(categorize_from_comment("Settings not saved, default value wrong"), 'configuration_settings')

    def test_comment_integration(self):
        self.assertEqual(categorize_from_comment("Bluetooth printer pairing fails"), 'integration_failures')

    def test_comment_compatibility(self):
        self.assertEqual(categorize_from_comment("Only on Android 14 with tablet resolution"), 'compatibility_issues')

    def test_ocr_auth(self):
        self.assertEqual(categorize_from_ocr("Sign in with password"), 'authentication_access')

    def test_ocr_connectivity(self):
        self.assertEqual(categorize_from_ocr("Unable to connect. API request failed"), 'connectivity_problems')

    def test_ocr_performance(self):
        self.assertEqual(categorize_from_ocr("Loading... please wait"), 'performance_issues')

    def test_ocr_configuration(self):
        self.assertEqual(categorize_from_ocr("Settings and Preferences"), 'configuration_settings')

    def test_ocr_integration(self):
        self.assertEqual(categorize_from_ocr("Payment gateway UPI"), 'integration_failures')

    def test_filename_error(self):
        self.assertEqual(categorize_from_filename("Screenshot_123_error.png"), 'functional_errors')

    def test_filename_login(self):
        self.assertEqual(categorize_from_filename("login_Screenshot.png"), 'authentication_access')

    def test_filename_timeout(self):
        self.assertEqual(categorize_from_filename("Screenshot_timeout_network.jpg"), 'connectivity_problems')

    def test_record_priority_comment_overrides(self):
        record = {"comment": "Feature request: add barcode scanner"}
        self.assertEqual(categorize_record(record, ocr_texts=["Loading"], filenames=["login.png"]), 'feature_requests')

    def test_record_ocr_when_no_comment(self):
        record = {"comment": ""}
        self.assertEqual(categorize_record(record, ocr_texts=["Unable to connect"], filenames=[]), 'connectivity_problems')

    def test_record_filename_when_no_ocr_or_comment(self):
        record = {"comment": ""}
        self.assertEqual(categorize_record(record, ocr_texts=[], filenames=["Screenshot_error.jpg"]), 'functional_errors')

    def test_record_fallback_unclear(self):
        record = {"comment": ""}
        self.assertEqual(categorize_record(record, ocr_texts=[], filenames=["image.jpg"]), 'unclear_insufficient_info')

    def test_allow_unclear_true_when_no_content(self):
        record = {"comment": ""}
        self.assertTrue(allow_unclear_label(record, ocr_texts=[], filenames=["image.jpg"]))

    def test_prevent_unclear_when_digits_present(self):
        # Even weak content like digits suggests usable content for best-effort
        record = {"comment": ""}
        cat = categorize_record(record, ocr_texts=["12345"], filenames=["image.jpg"])
        self.assertNotEqual(cat, 'unclear_insufficient_info')

    def test_prevent_unclear_when_header_like_fields(self):
        record = {"comment": "Total: 120"}
        cat = categorize_record(record, ocr_texts=[], filenames=[])
        self.assertNotEqual(cat, 'unclear_insufficient_info')

    def test_prevent_unclear_when_filename_hint(self):
        record = {"comment": ""}
        cat = categorize_record(record, ocr_texts=[], filenames=["login_screen.png"])
        self.assertEqual(cat, 'authentication_access')


if __name__ == '__main__':
    unittest.main()
