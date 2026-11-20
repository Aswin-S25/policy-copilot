# Information Security Standard

**Document Owner:** Information Security Team
**Policy Code:** ISS
**Version:** 2.1
**Effective Date:** 1 March 2026

This standard sets the technical security controls that apply to every company laptop, server and cloud account. It supplements the security section of the Employee Policy Handbook.

# 1. Endpoint Controls

## ISS-01 Screen Lock

All company laptops must lock automatically after **5 minutes** of inactivity. Employees must lock their screen manually (Windows+L or Ctrl+Cmd+Q) whenever they leave their device unattended, including in the office.

## ISS-02 Disk Encryption

Full-disk encryption (BitLocker on Windows, FileVault on macOS) is mandatory on every company laptop. Devices that report encryption as disabled are automatically blocked from the corporate network until encryption is restored by IT.

## ISS-03 Removable Media

USB storage devices are blocked by default. Employees who need to use removable media for a business reason must raise an exception request with the Information Security Team. Approved exceptions are valid for a maximum of **30 days**.

# 2. Patching and Vulnerabilities

## ISS-04 Patching Deadlines

Security updates must be installed within the following deadlines after release:

- Critical vulnerabilities: within **48 hours**
- High vulnerabilities: within **7 days**
- Medium and low vulnerabilities: within **30 days**

Laptops that miss a critical patch deadline are quarantined until the update is installed.

## ISS-05 Vulnerability Disclosure

Employees who discover a vulnerability in a company system must report it to security@company.example and must not test or exploit it further. Public disclosure of a vulnerability requires written approval from the Chief Information Security Officer (CISO).

# 3. Network Security

## ISS-06 VPN Usage

The company VPN must be used whenever accessing internal systems from outside the office network, including from home. Split tunnelling may not be enabled by employees.

## ISS-07 Public Wi-Fi

Public Wi-Fi networks in airports, hotels and cafés may be used only while connected to the company VPN. Employees should prefer a personal mobile hotspot over open public networks where available.

# 4. Clean Desk

## ISS-08 Clean Desk Rule

At the end of each working day, printed documents classified Confidential or Restricted must be locked away or shredded. Whiteboards must be wiped after meetings that discussed Confidential information.
