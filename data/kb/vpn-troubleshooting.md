# VPN Troubleshooting

## Before you start
Confirm the user has a working internet connection by asking them to open a public website. The VPN cannot connect if the home network or hotel Wi-Fi is down or requires a captive portal login.

## Common fixes
1. Have the user fully quit and reopen the VPN client, then try again.
2. Check that their account is in the VPN-Users security group in Active Directory. New hires are sometimes missed during onboarding.
3. If the error mentions authentication, confirm the user can sign in to Microsoft 365. An expired password will also block the VPN.
4. If the client says the server is unreachable, ask the user to try a phone hotspot. Some public networks block VPN ports.
5. Reinstall the VPN client from the Company Portal app if the steps above do not work.

## When to escalate
Escalate to Tier 2 with the exact error message, the time of the failed attempt, and the user's public IP address if several users report the same problem at once, since that points to a server or firewall issue rather than a single device.
