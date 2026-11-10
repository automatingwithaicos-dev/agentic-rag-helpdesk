# Multi-Factor Authentication (MFA)

## Setting up MFA for a new user
1. Have the user sign in at https://aka.ms/mysecurityinfo with their temporary password.
2. Choose "Add sign-in method" and select Microsoft Authenticator.
3. Install Microsoft Authenticator on their phone and scan the QR code shown on screen.
4. Approve the test notification to finish setup.

## User got a new phone
If the user still has the old phone, they can add the new phone from https://aka.ms/mysecurityinfo. If the old phone is lost or wiped, the help desk must verify the user's identity by callback, then go to Entra ID > Users > the user > Authentication methods and choose "Require re-register multifactor authentication." The user will be prompted to set up MFA again at their next sign-in.

## Unexpected MFA prompts
If a user reports MFA approval requests they did not start, tell them to deny the request and treat it as a possible compromised password. Reset the password immediately, revoke all sessions in Entra ID, and escalate to security.
