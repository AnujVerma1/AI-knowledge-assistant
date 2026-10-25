"""Regenerate the sample PDFs in ../samples (run: python -m scripts.make_samples)."""

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


# The following documents overlap in topic with the handbook and the security policy on purpose
# (leave, laptops, "P1" response times), so retrieval has to pick the right passage among similar ones.
BENEFITS_GUIDE_PAGES = [
    """Northwind Labs Benefits Guide (fictional sample document)
Page 1 - Health insurance

Group health insurance covers the employee, their spouse and up to two children.
The sum insured is INR 5,00,000 per family per year.
Parents can be added to the policy, but the premium for parents is paid by the employee.
New employees must enrol within 30 days of joining; later enrolment waits
for the next annual renewal in April.""",
    """Page 2 - Parental leave

Primary caregivers receive 26 weeks of fully paid parental leave.
Secondary caregivers receive 4 weeks of paid leave, which must be taken
within 6 months of the birth or adoption.
Adoptive parents receive the same parental leave as birth parents.
Employees can work part-time for up to 8 weeks after returning from parental leave.""",
    """Page 3 - Wellness and retirement

Each employee can claim up to INR 12,000 per year for wellness expenses such as
gym memberships, yoga classes and sports equipment.
Northwind contributes 12% of basic salary to the provident fund.
Gratuity is paid after 5 years of continuous service.""",
]

IT_HANDBOOK_PAGES = [
    """Northwind Labs IT Handbook (fictional sample document)
Page 1 - Laptops and software

New employees receive their laptop on their first working day.
Engineers can choose a 14-inch laptop with either Linux or macOS.
Laptops are replaced every 3 years.
Software with a paid licence must be requested through an IT ticket;
free open-source tools may be installed without approval.""",
    """Page 2 - Network and VPN

The VPN must be used on any public or hotel Wi-Fi network.
The company VPN client is called NorthGate.
The staff Wi-Fi network in all offices is NW-Staff.
The guest Wi-Fi password changes every Monday and is shown at reception.""",
    """Page 3 - Support and backups

IT support tickets are raised at helpdesk.northwind.example.
A complete IT outage is treated as an IT P1 and gets a response within 30 minutes.
Standard tickets are answered within 1 business day.
Laptops are backed up every night at 01:00 IST to the company cloud,
and backups are kept for 90 days.""",
]

TRAVEL_POLICY_PAGES = [
    """Northwind Labs Travel Policy (fictional sample document)
Page 1 - Booking

All flights and hotels are booked through the TravelDesk portal.
Flights must be booked at least 14 days before departure.
Economy class is used for flights shorter than 8 hours;
business class is allowed only for flights longer than 8 hours.""",
    """Page 2 - Allowances

The daily allowance for domestic travel is INR 2,500.
The daily allowance for international travel is USD 75.
Hotel costs are capped at INR 7,000 per night in metro cities.
Airport taxis are reimbursed with a receipt; personal car rentals are not.""",
    """Page 3 - International travel

International trips need manager approval at least 21 days before departure.
Visa fees are reimbursed in full.
Travel insurance is mandatory and is arranged by the HR team.
Employees must carry a printed copy of the travel insurance certificate.""",
]

PDFS = {
    "northwind_security_policy.pdf": SECURITY_POLICY_PAGES,
    "northwind_benefits_guide.pdf": BENEFITS_GUIDE_PAGES,
    "northwind_it_handbook.pdf": IT_HANDBOOK_PAGES,
    "northwind_travel_policy.pdf": TRAVEL_POLICY_PAGES,
}


def main() -> None:
    SAMPLES_DIR.mkdir(exist_ok=True)
    for filename, pages in PDFS.items():
        path = SAMPLES_DIR / filename
        path.write_bytes(build_pdf(pages))
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
