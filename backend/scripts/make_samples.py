"""Regenerate the sample PDF in ../samples (run: python -m scripts.make_samples)."""

from pathlib import Path

from tests.pdf_factory import build_pdf

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"

SECURITY_POLICY_PAGES = [
    """Northwind Labs Information Security Policy (fictional sample document)
Page 1 - Accounts and passwords

All company accounts must use a password of at least 14 characters.
Passwords must be changed immediately if a compromise is suspected,
but routine periodic password changes are not required.
Multi-factor authentication is mandatory for email, source code hosting
and the cloud console. Hardware security keys are issued to administrators.""",
    """Page 2 - Devices and data

Company laptops must use full-disk encryption and lock after 5 minutes
of inactivity. Customer data may only be stored in approved systems;
copying customer data to personal devices or USB drives is prohibited.
Lost or stolen devices must be reported to it-security@northwind.example
within 1 hour of discovering the loss.""",
    """Page 3 - Incident response

Security incidents are classified as P1 (critical), P2 (high) or P3 (low).
P1 incidents require the on-call security engineer to respond within
15 minutes and a written incident report within 48 hours.
Phishing emails should be reported with the Report Phishing button
and must not be forwarded to colleagues.""",
]


def main() -> None:
    SAMPLES_DIR.mkdir(exist_ok=True)
    path = SAMPLES_DIR / "northwind_security_policy.pdf"
    path.write_bytes(build_pdf(SECURITY_POLICY_PAGES))
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
