# Security Policy

## Supported Versions

| Version | Support |
|---------|---------|
| 5.x     | Active support |
| 4.x     | Security patches |
| < 4.0   | Not supported |

## Reporting a Vulnerability

Found a security issue? Please **DO NOT open a public issue**.

### How to Report

1. Describe the vulnerability in detail
2. Include reproduction steps if possible
3. Specify affected versions
4. Report via [GitHub Security Advisories](https://github.com/KadirHarmanc/nazar/security/advisories)

### Response Timeline

- Initial response within 48 hours
- Fix plan within 7 days
- Credit given when fix is published

### In Scope

- Security vulnerabilities in Nazar itself
- Information disclosure during scanning
- Dependency chain vulnerabilities

### Out of Scope

- Vulnerabilities in scanned projects (that's Nazar's job to find)
- Social engineering
- DoS attacks

## Security Measures

- Nazar never modifies any files during scanning
- Network requests only during API testing phase
- All file operations are read-only
- Secret patterns are masked in reports
- Path traversal protection on file reads
- SSRF protection on API endpoint testing
- Plugin directories restricted to project root
