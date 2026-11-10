# Intune Device Enrollment

## New Windows laptop (Autopilot)
Company laptops are registered with Windows Autopilot. When the user turns the laptop on and connects to Wi-Fi, they sign in with their work email and the device enrolls in Intune automatically. Apps and policies install during setup, which can take 30 to 60 minutes. Tell the user to stay connected to power and Wi-Fi until the desktop appears.

## Device shows as not compliant
1. Open the Intune admin center, go to Devices, and find the device.
2. Check which compliance policy is failing. The most common causes are BitLocker not enabled, Windows updates missing, or the device not checking in for more than 7 days.
3. Ask the user to open Company Portal and choose "Check status" to force a sync.
4. If BitLocker is the issue, have the user restart so encryption can begin.

A noncompliant device is blocked from email and Teams by Conditional Access until it is fixed.

## Personal phones
Users can access email on personal phones through the Outlook app. App protection policies keep company data inside Outlook and Teams without enrolling the whole phone.
