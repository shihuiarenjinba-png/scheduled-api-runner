# Scheduled API Runner — runFullTrust justification draft

The package contains a packaged Win32 desktop application. `runFullTrust` is required so the desktop executable can run with the normal interactive user's medium-integrity permissions, read and write user-selected local configuration/export files, maintain local execution state, and optionally register or remove this application's own non-elevated interactive Windows scheduled task after explicit user approval.

The application does not require administrator elevation, does not install a Windows service, and does not use this capability to bypass Windows security controls.
