# Password Reset and Account Lockout

## Self-service password reset
Users can reset their own password at https://aka.ms/sspr. They must have registered a phone number or the Microsoft Authenticator app first. If the user has not registered, the help desk must reset the password for them.

## Help desk password reset
1. Verify the caller's identity by calling them back at the phone number listed in the HR directory. Never reset a password based only on an inbound call or email.
2. In the Microsoft 365 admin center, open Users > Active users, select the user, and choose Reset password.
3. Set a temporary password and check "Require this user to change their password when they first sign in."
4. Give the temporary password to the user over the phone, never by email.
5. Note the verification method in the ticket.

## Account lockout
An account locks after 10 failed sign-in attempts and unlocks automatically after 30 minutes. If the user cannot wait, unlock the account in Active Directory Users and Computers by opening the user's properties, going to the Account tab, and checking "Unlock account." Repeated lockouts usually come from an old password saved on a phone or in Windows Credential Manager. Ask the user to update the password on every device that syncs email.
