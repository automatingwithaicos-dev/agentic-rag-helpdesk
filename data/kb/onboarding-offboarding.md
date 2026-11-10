# User Onboarding and Offboarding

## Onboarding checklist
1. Create the account in Active Directory from the HR ticket, using the standard naming format first.last.
2. Add the user to their department security groups and to VPN-Users if they work remotely.
3. Assign a Microsoft 365 Business Premium license once the account syncs to Entra ID.
4. Assign an Autopilot laptop and record its serial number in the asset tracker.
5. Send the manager the temporary password by phone and schedule a 15 minute first-day setup call for MFA.

## Offboarding checklist
1. On the user's last day, disable the account in Active Directory and revoke all sessions in Entra ID.
2. Convert the mailbox to a shared mailbox and give the manager access if requested in the ticket.
3. Remove the Microsoft 365 license after the mailbox is converted, so the data is kept.
4. Wipe or retire their devices in Intune and collect the laptop, updating the asset tracker.
5. Remove the user from all security groups and document every step in the ticket.

## Disabled accounts
A disabled account with no license and no group memberships almost always means the user was offboarded on purpose. Do not ask for the account to be re-enabled just because the user can't sign in. Confirm with the user's manager or HR first. If HR confirms the user is returning (a rehire or the end of a leave), open a Tier 2 ticket that names who approved it, so the account, license, and groups can be restored together.
